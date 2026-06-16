# history.py
# -----------------------------------------------------------------------------
# Har refresh ka SNAPSHOT (spend, stance, narratives) save karta hai — "Trend
# Over Time" charts + auto-insights ke liye. Dual-backend:
#   - DATABASE_URL set (Railway) -> PostgreSQL table (permanent)
#   - warna (local)              -> data/history.json file
# -----------------------------------------------------------------------------

import os
import json
import threading
import logging
from datetime import datetime, timezone

log = logging.getLogger("history")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_PG = bool(DATABASE_URL)

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_FILE = os.path.join(_DIR, "history.json")
HISTORY_MAX = int(os.environ.get("HISTORY_MAX", "2000"))
_LOCK = threading.Lock()


# ----- Postgres helpers (lazy) ----------------------------------------------
def _pg_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def _pg_init():
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS history_snapshots ("
                    "id SERIAL PRIMARY KEY, t TEXT, data TEXT)")
        conn.commit()
    finally:
        conn.close()


if USE_PG:
    try:
        _pg_init()
        log.info("history backend: PostgreSQL")
    except Exception as e:  # pragma: no cover
        log.warning("history PG init failed: %s", e)
else:
    log.info("history backend: JSON file")


# ----- File helpers ---------------------------------------------------------
def _load_file():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []


def _save_file(items):
    os.makedirs(_DIR, exist_ok=True)
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    os.replace(tmp, HISTORY_FILE)


# ----- Snapshot building ----------------------------------------------------
def _snapshot_from_payload(payload):
    party_spend = {p.get("party", "?"): round(p.get("spend", 0))
                   for p in (payload.get("party_spend", []) or [])}
    sc = payload.get("stance_counts", {}) or {}
    stance = {"against": sc.get("against", 0), "support": sc.get("support", 0),
              "neutral": sc.get("neutral", 0)}
    narratives = {}
    for b in (payload.get("battlefield", []) or []):
        narratives[b.get("narrative", "?")] = b.get("count", 0)
    if not narratives:
        for t in (payload.get("top_themes", []) or []):
            narratives[t.get("theme", "?")] = t.get("count", 0)
    return {
        "t": datetime.now(timezone.utc).isoformat(),
        "mode": payload.get("mode", "demo"),
        "count": payload.get("count", 0),
        "top_spender": payload.get("top_spender", "N/A"),
        "party_spend": party_spend, "stance": stance, "narratives": narratives,
    }


def record_snapshot(payload):
    try:
        snap = _snapshot_from_payload(payload)
        if USE_PG:
            conn = _pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO history_snapshots (t, data) VALUES (%s, %s)",
                            (snap["t"], json.dumps(snap)))
                # purane snapshots trim (HISTORY_MAX se zyada)
                cur.execute(
                    "DELETE FROM history_snapshots WHERE id NOT IN "
                    "(SELECT id FROM history_snapshots ORDER BY id DESC LIMIT %s)",
                    (HISTORY_MAX,))
                conn.commit()
            finally:
                conn.close()
        else:
            with _LOCK:
                items = _load_file()
                items.append(snap)
                if len(items) > HISTORY_MAX:
                    items = items[-HISTORY_MAX:]
                _save_file(items)
        log.info("history snapshot saved (backend=%s)", "PG" if USE_PG else "file")
    except Exception as e:
        log.warning("record_snapshot failed: %s", e)


def load_history():
    if USE_PG:
        try:
            conn = _pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT data FROM history_snapshots ORDER BY id ASC")
                return [json.loads(r[0]) for r in cur.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            log.warning("load_history (PG) failed: %s", e)
            return []
    with _LOCK:
        return _load_file()


# ----- Insights (backend-agnostic) ------------------------------------------
def _pct_change(old, new):
    if old <= 0:
        return None if new <= 0 else 100.0
    return round((new - old) / old * 100)


def compute_insights(items):
    if len(items) < 2:
        return []
    latest = items[-1]
    baseline = items[max(0, len(items) - 8)]
    out = []
    for party, new_v in latest.get("party_spend", {}).items():
        old_v = baseline.get("party_spend", {}).get(party, 0)
        ch = _pct_change(old_v, new_v)
        if ch is not None and abs(ch) >= 25 and new_v >= 1000:
            arrow = "📈 +" if ch > 0 else "📉 "
            out.append(f"{arrow}{ch}% — {party} ka spend {'badha' if ch>0 else 'ghata'} "
                       f"(₹{old_v:,} → ₹{new_v:,})")
    for narr, new_v in latest.get("narratives", {}).items():
        old_v = baseline.get("narratives", {}).get(narr, 0)
        if new_v - old_v >= 3:
            mult = f"{round(new_v/old_v,1)}x" if old_v > 0 else "naya"
            out.append(f"🎯 '{narr}' narrative upar — {old_v} → {new_v} ads ({mult})")
    a_old = baseline.get("stance", {}).get("against", 0)
    a_new = latest.get("stance", {}).get("against", 0)
    if a_new - a_old >= 3:
        out.append(f"⚔️ AAP ke against ads badhe — {a_old} → {a_new}")
    elif a_old - a_new >= 3:
        out.append(f"🛡️ AAP ke against ads ghate — {a_old} → {a_new}")
    return out[:8]
