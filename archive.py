# archive.py
# -----------------------------------------------------------------------------
# Har pool ki gayi ad ka PERMANENT record (SQLite). Active ho ya band ho gayi —
# sab save rehta hai with first_seen / last_seen / active / stopped_at.
# Isse "last week/month konsi ads thi, konsi band ho gayi" analyze hota hai.
#
# Storage: data/archive.db (SQLite). Local/desktop pe permanent. Railway pe
# permanent rakhne ke liye ek Volume attach karna (warna redeploy pe reset).
# -----------------------------------------------------------------------------

import os
import json
import sqlite3
import threading
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("archive")

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.environ.get("ARCHIVE_DB", os.path.join(_DIR, "archive.db"))
_WLOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _conn():
    os.makedirs(_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.execute("""
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
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_active ON ads_archive(active)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lastseen ON ads_archive(last_seen)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_firstseen ON ads_archive(first_seen)")


try:
    _init()
except Exception as e:  # pragma: no cover
    log.warning("archive init failed: %s", e)


def _row_from_ad(a, seen):
    return (
        a.get("id", ""), a.get("page", ""), a.get("page_id", ""), a.get("handle", ""),
        a.get("party", ""), a.get("source", ""), a.get("stance", ""),
        a.get("narrative", "") or a.get("theme", ""), a.get("narrative_summary", ""),
        a.get("theme", ""), a.get("spend", ""), a.get("impr", ""),
        a.get("spend_mid", 0) or 0, a.get("impr_mid", 0) or 0,
        ", ".join(a.get("regions", []) or []), ", ".join(a.get("plat", []) or []),
        json.dumps(a.get("audience")) if a.get("audience") else "",
        a.get("damage_level") or "", a.get("start", ""), a.get("snapshot_url", ""),
        a.get("text", ""), seen, seen,
    )


def record_ads(ads, mode="live"):
    """
    Current pool ki ads ko archive mein upsert karo, aur jo ads pehle active
    thi par ab nahi aayi unhe STOPPED mark karo. (Demo mode mein skip — taaki
    real archive corrupt na ho.)
    """
    if mode != "live" or not ads:
        return
    seen = _now()
    cols = ("id,page,page_id,handle,party,source,stance,narrative,"
            "narrative_summary,theme,spend,impr,spend_mid,impr_mid,regions,"
            "platforms,audience,damage_level,started,snapshot_url,text,"
            "first_seen,last_seen")
    try:
        with _WLOCK, _conn() as c:
            for a in ads:
                if not a.get("id"):
                    continue
                row = _row_from_ad(a, seen)
                # naye ad insert; mojooda update (last_seen + reactivate + refresh)
                c.execute(
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
                    % (cols, ",".join("?" * 23)),
                    row,
                )
            # Jo active thi par is pool mein nahi aayi -> STOPPED
            c.execute(
                "UPDATE ads_archive SET active=0, stopped_at=? "
                "WHERE active=1 AND last_seen<>?",
                (seen, seen),
            )
        log.info("archive updated (%d ads pooled)", len(ads))
    except Exception as e:
        log.warning("record_ads failed: %s", e)


def _ad_dict(r):
    d = dict(r)
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
    """Archive se ads nikaalo with filters."""
    where = []
    params = []
    if status == "active":
        where.append("active=1")
    elif status == "stopped":
        where.append("active=0")
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
        where.append("last_seen>=?")
        params.append(cutoff)
    if party and party != "ALL":
        where.append("party=?")
        params.append(party)
    if stance and stance != "ALL":
        where.append("stance=?")
        params.append(stance)
    q = "SELECT * FROM ads_archive"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY last_seen DESC LIMIT ?"
    params.append(int(limit))
    try:
        with _conn() as c:
            rows = c.execute(q, params).fetchall()
        return [_ad_dict(r) for r in rows]
    except Exception as e:
        log.warning("get_archive failed: %s", e)
        return []


def stats():
    """Archive summary — total, active, stopped, new/stopped today, etc."""
    today = datetime.now(timezone.utc).date().isoformat()
    d7 = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    d30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    try:
        with _conn() as c:
            def one(q, p=()):
                return c.execute(q, p).fetchone()[0]
            total = one("SELECT COUNT(*) FROM ads_archive")
            active = one("SELECT COUNT(*) FROM ads_archive WHERE active=1")
            stopped = one("SELECT COUNT(*) FROM ads_archive WHERE active=0")
            new_today = one("SELECT COUNT(*) FROM ads_archive WHERE substr(first_seen,1,10)=?", (today,))
            stopped_today = one("SELECT COUNT(*) FROM ads_archive WHERE substr(stopped_at,1,10)=?", (today,))
            act7 = one("SELECT COUNT(*) FROM ads_archive WHERE last_seen>=?", (d7,))
            act30 = one("SELECT COUNT(*) FROM ads_archive WHERE last_seen>=?", (d30,))
        return {
            "available": True, "total": total, "active": active,
            "stopped": stopped, "new_today": new_today,
            "stopped_today": stopped_today, "active_7d": act7, "active_30d": act30,
        }
    except Exception as e:
        log.warning("stats failed: %s", e)
        return {"available": False}
