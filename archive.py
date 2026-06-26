# archive.py
# -----------------------------------------------------------------------------
# Har pool ki gayi ad ka PERMANENT record. Dual-backend:
#   - DATABASE_URL set hai (Railway)  -> PostgreSQL (permanent, redeploy-proof)
#   - warna (local/desktop)           -> SQLite file (data/archive.db)
#
# Active ho ya band ho gayi — sab save rehta hai with first_seen / last_seen /
# active / stopped_at. Isse "last week/month konsi ads thi, konsi band ho gayi"
# analyze hota hai.
# -----------------------------------------------------------------------------

import os
import json
import threading
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("archive")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_PG = bool(DATABASE_URL)
PH = "%s" if USE_PG else "?"   # placeholder style

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.environ.get("ARCHIVE_DB", os.path.join(_DIR, "archive.db"))
_WLOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect():
    """Backend ke hisaab se connection do."""
    if USE_PG:
        import psycopg2  # lazy — sirf Railway pe chahiye
        return psycopg2.connect(DATABASE_URL)
    import sqlite3
    os.makedirs(_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def _write(statements):
    """List of (query, params) ek transaction mein chalao."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for q, p in statements:
            cur.execute(q, p)
        conn.commit()
    finally:
        conn.close()


def _query(q, params=()):
    """SELECT chalao, list of dict-rows do (dono backends)."""
    conn = _connect()
    try:
        if USE_PG:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(q, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


_DDL = """
CREATE TABLE IF NOT EXISTS ads_archive (
    id TEXT PRIMARY KEY,
    page TEXT, page_id TEXT, handle TEXT, bylines TEXT,
    party TEXT, source TEXT, stance TEXT,
    narrative TEXT, narrative_summary TEXT, theme TEXT,
    spend TEXT, impr TEXT, spend_mid REAL, impr_mid REAL,
    regions TEXT, platforms TEXT, audience TEXT,
    damage_level TEXT, started TEXT, stop TEXT, snapshot_url TEXT, text TEXT,
    first_seen TEXT, last_seen TEXT,
    active INTEGER DEFAULT 1, stopped_at TEXT
)
"""


def _migrate():
    """Purane archive ke liye naye columns add karo (jo na hon)."""
    for col in ("stop TEXT", "bylines TEXT"):
        try:
            _write([("ALTER TABLE ads_archive ADD COLUMN " + col, ())])
            log.info("archive: added column %s", col)
        except Exception:
            pass  # column already hai — sab theek


def _init():
    _write([
        (_DDL, ()),
        ("CREATE INDEX IF NOT EXISTS idx_active ON ads_archive(active)", ()),
        ("CREATE INDEX IF NOT EXISTS idx_lastseen ON ads_archive(last_seen)", ()),
        ("CREATE INDEX IF NOT EXISTS idx_firstseen ON ads_archive(first_seen)", ()),
    ])
    _migrate()


try:
    _init()
    log.info("archive backend: %s", "PostgreSQL" if USE_PG else "SQLite")
except Exception as e:  # pragma: no cover
    log.warning("archive init failed: %s", e)


_COLS = ("id,page,page_id,handle,bylines,party,source,stance,narrative,"
         "narrative_summary,theme,spend,impr,spend_mid,impr_mid,regions,"
         "platforms,audience,damage_level,started,stop,snapshot_url,text,"
         "first_seen,last_seen")


def _row_from_ad(a, seen):
    return (
        a.get("id", ""), a.get("page", ""), a.get("page_id", ""), a.get("handle", ""),
        a.get("bylines", ""),
        a.get("party", ""), a.get("source", ""), a.get("stance", ""),
        a.get("narrative", "") or a.get("theme", ""), a.get("narrative_summary", ""),
        a.get("theme", ""), a.get("spend", ""), a.get("impr", ""),
        float(a.get("spend_mid", 0) or 0), float(a.get("impr_mid", 0) or 0),
        ", ".join(a.get("regions", []) or []), ", ".join(a.get("plat", []) or []),
        json.dumps(a.get("audience")) if a.get("audience") else "",
        a.get("damage_level") or "", a.get("start", ""), a.get("stop", ""),
        a.get("snapshot_url", ""), a.get("text", ""), seen, seen,
    )


def record_ads(ads, mode="live"):
    """
    Current pool ki ads upsert karo, aur jo pehle active thi par ab nahi aayi
    unhe STOPPED mark karo. Demo mode mein skip (archive clean rahe).
    """
    if mode != "live" or not ads:
        return
    seen = _now()
    placeholders = ",".join([PH] * 25)
    insert_q = (
        "INSERT INTO ads_archive (%s, active, stopped_at) "
        "VALUES (%s, 1, NULL) "
        "ON CONFLICT(id) DO UPDATE SET "
        "last_seen=excluded.last_seen, active=1, stopped_at=NULL, "
        "party=excluded.party, "
        # NON-DESTRUCTIVE: agar naya classify fail ho (unknown/empty) to purana
        # accha stance/narrative WIPE na ho — sirf valid value se update karo.
        "stance=CASE WHEN excluded.stance IN ('against','support','neutral') "
        "THEN excluded.stance ELSE ads_archive.stance END, "
        "narrative=CASE WHEN COALESCE(excluded.narrative,'')<>'' "
        "THEN excluded.narrative ELSE ads_archive.narrative END, "
        "narrative_summary=CASE WHEN COALESCE(excluded.narrative_summary,'')<>'' "
        "THEN excluded.narrative_summary ELSE ads_archive.narrative_summary END, "
        "spend=excluded.spend, impr=excluded.impr, "
        "spend_mid=excluded.spend_mid, impr_mid=excluded.impr_mid, "
        "damage_level=excluded.damage_level, audience=excluded.audience, "
        "regions=excluded.regions, platforms=excluded.platforms, "
        "started=excluded.started, stop=excluded.stop, "
        "bylines=excluded.bylines"
        % (_COLS, placeholders)
    )
    stop_q = ("UPDATE ads_archive SET active=0, stopped_at=%s "
              "WHERE active=1 AND last_seen<>%s" % (PH, PH))
    try:
        stmts = [(insert_q, _row_from_ad(a, seen)) for a in ads if a.get("id")]
        stmts.append((stop_q, (seen, seen)))
        with _WLOCK:
            _write(stmts)
        log.info("archive updated (%d ads pooled, backend=%s)",
                 len(ads), "PG" if USE_PG else "SQLite")
    except Exception as e:
        log.warning("record_ads failed: %s", e)


def _ad_dict(d):
    if d.get("audience"):
        try:
            d["audience"] = json.loads(d["audience"])
        except Exception:
            d["audience"] = None
    d["regions"] = [x for x in (d.get("regions") or "").split(", ") if x]
    d["plat"] = [x for x in (d.get("platforms") or "").split(", ") if x]
    d["active"] = bool(d.get("active"))
    return d


def get_archive(status="all", days=None, party=None, stance=None, limit=800):
    where, params = [], []
    if status == "active":
        where.append("active=1")
    elif status == "stopped":
        where.append("active=0")
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
        where.append("last_seen>=" + PH)
        params.append(cutoff)
    if party and party != "ALL":
        where.append("party=" + PH)
        params.append(party)
    if stance and stance != "ALL":
        where.append("stance=" + PH)
        params.append(stance)
    q = "SELECT * FROM ads_archive"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY last_seen DESC LIMIT " + PH
    params.append(int(limit))
    try:
        return [_ad_dict(r) for r in _query(q, tuple(params))]
    except Exception as e:
        log.warning("get_archive failed: %s", e)
        return []


def dashboard_ads(limit=None):
    """
    Archive se ads ko dashboard/aggregate ke shape mein lao — taaki jab live
    Meta fetch fail/throttle ho (ya warm-up chal raha ho), demo ki jagah ye
    REAL (pehle se classified) ads dikhaye ja saken. War-room hamesha asli data.
    """
    import config as _cfg
    rows = get_archive(status="all", limit=limit or 5000)
    for r in rows:
        r["start"] = r.get("started", "") or ""
        r["is_official"] = str(r.get("page_id") or "") in _cfg.PAGE_TO_PARTY
        r["is_punjab"] = True
        r.setdefault("plat", r.get("plat", []) or [])
    return rows


def purge_old():
    """
    Lean tracking: sirf is month shuru hui (started >= mahine ka 1st) YA abhi chal
    rahi (active=1) ads rakho. Baaki purani band ho chuki ads PERMANENTLY delete.
    Har refresh ke baad chalta hai taaki database fresh + chhota rahe.
    Deleted count return karta hai.
    """
    month_start = datetime.now(timezone.utc).date().replace(day=1).isoformat()
    try:
        before = _query("SELECT COUNT(*) AS n FROM ads_archive")[0]["n"]
        _write([("DELETE FROM ads_archive WHERE active=0 AND "
                 "COALESCE(NULLIF(started,''),'0000-00-00') < " + PH,
                 (month_start,))])
        after = _query("SELECT COUNT(*) AS n FROM ads_archive")[0]["n"]
        n = before - after
        if n:
            log.info("purge_old: %d purani ads delete ki (kept active + "
                     "started>=%s); ab %d ads.", n, month_start, after)
        return n
    except Exception as e:
        log.warning("purge_old failed: %s", e)
        return 0


def directory(limit=400):
    """
    Disclaimer ("Paid for by") directory: har funding entity / agency ki kitni
    ads, kitna spend, against/support breakdown, party + Meta link (jahan
    address/phone publicly dikhta hai). Record-keeping ke liye.
    """
    try:
        rows = _query(
            "SELECT bylines, COUNT(*) AS ads, "
            "COALESCE(SUM(spend_mid),0) AS spend, "
            "SUM(CASE WHEN stance='against' THEN 1 ELSE 0 END) AS ag, "
            "SUM(CASE WHEN stance='support' THEN 1 ELSE 0 END) AS su, "
            "SUM(CASE WHEN active=1 THEN 1 ELSE 0 END) AS act, "
            "MAX(party) AS party, MAX(page_id) AS page_id "
            "FROM ads_archive WHERE bylines IS NOT NULL AND bylines<>'' "
            "GROUP BY bylines ORDER BY spend DESC LIMIT " + PH, (int(limit),))
        adv = [{
            "byline": r["bylines"], "ads": r["ads"],
            "spend": round(float(r["spend"] or 0)),
            "against": r["ag"] or 0, "support": r["su"] or 0,
            "active": r["act"] or 0,
            "party": r["party"] or "OTHER",
            "page_id": r["page_id"] or "",
        } for r in rows]
        return {"available": True, "advertisers": adv,
                "count": len(adv), "ads_total": sum(a["ads"] for a in adv)}
    except Exception as e:
        log.warning("directory failed: %s", e)
        return {"available": False}


def spend_tracker():
    """
    Dono side ki estimated spend (archive se — permanent):
    - against: AAP ke KHILAF kitna (party-wise + daily)
    - support: AAP ke SUPPORT mein kitna (pro-AAP ads)
    """
    def num(x):
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    def side(stance):
        total = num(_query("SELECT COALESCE(SUM(spend_mid),0) AS s FROM "
                           "ads_archive WHERE stance=" + PH, (stance,))[0]["s"])
        active = num(_query("SELECT COALESCE(SUM(spend_mid),0) AS s FROM "
                            "ads_archive WHERE stance=" + PH + " AND active=1",
                            (stance,))[0]["s"])
        n = _query("SELECT COUNT(*) AS c FROM ads_archive WHERE stance=" + PH,
                   (stance,))[0]["c"]
        bp = _query("SELECT party, COALESCE(SUM(spend_mid),0) AS s, COUNT(*) AS c "
                    "FROM ads_archive WHERE stance=" + PH + " GROUP BY party "
                    "ORDER BY s DESC", (stance,))
        daily = _query("SELECT substr(first_seen,1,10) AS day, "
                       "COALESCE(SUM(spend_mid),0) AS s, COUNT(*) AS c "
                       "FROM ads_archive WHERE stance=" + PH + " "
                       "GROUP BY substr(first_seen,1,10) ORDER BY day", (stance,))
        # Top 10 spender PAGES is side pe (kis page ne sabse zyada lagaya).
        tp = _query("SELECT page, MIN(handle) AS handle, MIN(party) AS party, "
                    "COALESCE(SUM(spend_mid),0) AS s, COUNT(*) AS c "
                    "FROM ads_archive WHERE stance=" + PH + " AND page<>'' "
                    "GROUP BY page ORDER BY s DESC LIMIT 10", (stance,))
        # Period-wise spend: ads jo us period mein SHURU hui unka total spend.
        today = datetime.now(timezone.utc).date()

        def period(since):
            r = _query("SELECT COALESCE(SUM(spend_mid),0) AS s, COUNT(*) AS c "
                       "FROM ads_archive WHERE stance=" + PH +
                       " AND substr(started,1,10)>=" + PH, (stance, since))[0]
            return {"spend": round(num(r["s"])), "count": r["c"]}
        periods = {
            "today": period(today.isoformat()),
            "week": period((today - timedelta(days=7)).isoformat()),
            "month": period((today - timedelta(days=30)).isoformat()),
            "year": period((today - timedelta(days=365)).isoformat()),
        }
        return {
            "total": round(total), "active_spend": round(active), "ads": n,
            "by_party": [{"party": r["party"] or "OTHER", "spend": round(num(r["s"])),
                          "count": r["c"]} for r in bp],
            "daily": [{"day": r["day"], "spend": round(num(r["s"])),
                       "count": r["c"]} for r in daily if r["day"]],
            "top_pages": [{"page": r["page"], "handle": r["handle"] or "",
                           "party": r["party"] or "OTHER",
                           "spend": round(num(r["s"])), "count": r["c"]}
                          for r in tp],
            "periods": periods,
        }

    try:
        return {"available": True, "against": side("against"),
                "support": side("support")}
    except Exception as e:
        log.warning("spend_tracker failed: %s", e)
        return {"available": False}


def stats():
    today = datetime.now(timezone.utc).date().isoformat()
    d7 = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    d30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    try:
        def one(q, p=()):
            r = _query(q, p)
            return list(r[0].values())[0] if r else 0
        total = one("SELECT COUNT(*) AS c FROM ads_archive")
        active = one("SELECT COUNT(*) AS c FROM ads_archive WHERE active=1")
        stopped = one("SELECT COUNT(*) AS c FROM ads_archive WHERE active=0")
        new_today = one("SELECT COUNT(*) AS c FROM ads_archive WHERE substr(first_seen,1,10)=" + PH, (today,))
        stopped_today = one("SELECT COUNT(*) AS c FROM ads_archive WHERE substr(stopped_at,1,10)=" + PH, (today,))
        act7 = one("SELECT COUNT(*) AS c FROM ads_archive WHERE last_seen>=" + PH, (d7,))
        act30 = one("SELECT COUNT(*) AS c FROM ads_archive WHERE last_seen>=" + PH, (d30,))
        return {"available": True, "total": total, "active": active,
                "stopped": stopped, "new_today": new_today,
                "stopped_today": stopped_today, "active_7d": act7, "active_30d": act30}
    except Exception as e:
        log.warning("stats failed: %s", e)
        return {"available": False}
