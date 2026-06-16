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
    page TEXT, page_id TEXT, handle TEXT,
    party TEXT, source TEXT, stance TEXT,
    narrative TEXT, narrative_summary TEXT, theme TEXT,
    spend TEXT, impr TEXT, spend_mid REAL, impr_mid REAL,
    regions TEXT, platforms TEXT, audience TEXT,
    damage_level TEXT, started TEXT, snapshot_url TEXT, text TEXT,
    first_seen TEXT, last_seen TEXT,
    active INTEGER DEFAULT 1, stopped_at TEXT
)
"""


def _init():
    _write([
        (_DDL, ()),
        ("CREATE INDEX IF NOT EXISTS idx_active ON ads_archive(active)", ()),
        ("CREATE INDEX IF NOT EXISTS idx_lastseen ON ads_archive(last_seen)", ()),
        ("CREATE INDEX IF NOT EXISTS idx_firstseen ON ads_archive(first_seen)", ()),
    ])


try:
    _init()
    log.info("archive backend: %s", "PostgreSQL" if USE_PG else "SQLite")
except Exception as e:  # pragma: no cover
    log.warning("archive init failed: %s", e)


_COLS = ("id,page,page_id,handle,party,source,stance,narrative,"
         "narrative_summary,theme,spend,impr,spend_mid,impr_mid,regions,"
         "platforms,audience,damage_level,started,snapshot_url,text,"
         "first_seen,last_seen")


def _row_from_ad(a, seen):
    return (
        a.get("id", ""), a.get("page", ""), a.get("page_id", ""), a.get("handle", ""),
        a.get("party", ""), a.get("source", ""), a.get("stance", ""),
        a.get("narrative", "") or a.get("theme", ""), a.get("narrative_summary", ""),
        a.get("theme", ""), a.get("spend", ""), a.get("impr", ""),
        float(a.get("spend_mid", 0) or 0), float(a.get("impr_mid", 0) or 0),
        ", ".join(a.get("regions", []) or []), ", ".join(a.get("plat", []) or []),
        json.dumps(a.get("audience")) if a.get("audience") else "",
        a.get("damage_level") or "", a.get("start", ""), a.get("snapshot_url", ""),
        a.get("text", ""), seen, seen,
    )


def record_ads(ads, mode="live"):
    """
    Current pool ki ads upsert karo, aur jo pehle active thi par ab nahi aayi
    unhe STOPPED mark karo. Demo mode mein skip (archive clean rahe).
    """
    if mode != "live" or not ads:
        return
    seen = _now()
    placeholders = ",".join([PH] * 23)
    insert_q = (
        "INSERT INTO ads_archive (%s, active, stopped_at) "
        "VALUES (%s, 1, NULL) "
        "ON CONFLICT(id) DO UPDATE SET "
        "last_seen=excluded.last_seen, active=1, stopped_at=NULL, "
        "stance=excluded.stance, narrative=excluded.narrative, "
        "narrative_summary=excluded.narrative_summary, "
        "spend=excluded.spend, impr=excluded.impr, "
        "spend_mid=excluded.spend_mid, impr_mid=excluded.impr_mid, "
        "damage_level=excluded.damage_level, audience=excluded.audience, "
        "regions=excluded.regions, platforms=excluded.platforms"
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
