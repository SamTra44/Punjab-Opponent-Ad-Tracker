# history.py
# -----------------------------------------------------------------------------
# Har refresh ka ek SNAPSHOT save karta hai (spend, stance, narratives) ek
# JSON file mein. Isse "Trend Over Time" charts + auto-insights bante hain:
# kaun si party ka spend badh/ghat raha hai, kaun sa narrative upar aa raha hai.
#
# NOTE: file-based storage. Local/desktop pe persist hota hai. Railway pe
# filesystem ephemeral hai (redeploy pe reset) — wahan permanent history ke
# liye baad mein DB/Redis laga sakte hain. Abhi testing ke liye file theek hai.
# -----------------------------------------------------------------------------

import os
import json
import threading
import logging
from datetime import datetime, timezone

import config

log = logging.getLogger("history")

_LOCK = threading.Lock()

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.json")
HISTORY_MAX = int(os.environ.get("HISTORY_MAX", "1000"))   # kitne snapshots rakhein


def _ensure_dir():
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
    except Exception:
        pass


def _load_raw():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_raw(items):
    _ensure_dir()
    tmp = HISTORY_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        os.replace(tmp, HISTORY_FILE)
    except Exception as e:
        log.warning("history save failed: %s", e)


def _snapshot_from_payload(payload):
    """Payload se ek compact snapshot banao (chart ke liye zaroori cheezein)."""
    party_spend = {}
    for p in payload.get("party_spend", []) or []:
        party_spend[p.get("party", "?")] = round(p.get("spend", 0))

    sc = payload.get("stance_counts", {}) or {}
    stance = {
        "against": sc.get("against", 0),
        "support": sc.get("support", 0),
        "neutral": sc.get("neutral", 0),
    }

    # Narratives: AI battlefield ko prefer karo, warna keyword themes.
    narratives = {}
    bf = payload.get("battlefield", []) or []
    if bf:
        for b in bf:
            narratives[b.get("narrative", "?")] = b.get("count", 0)
    else:
        for t in payload.get("top_themes", []) or []:
            narratives[t.get("theme", "?")] = t.get("count", 0)

    return {
        "t": datetime.now(timezone.utc).isoformat(),
        "mode": payload.get("mode", "demo"),
        "count": payload.get("count", 0),
        "top_spender": payload.get("top_spender", "N/A"),
        "party_spend": party_spend,
        "stance": stance,
        "narratives": narratives,
    }


def record_snapshot(payload):
    """Ek refresh ka snapshot history mein add karo (thread-safe)."""
    try:
        snap = _snapshot_from_payload(payload)
        with _LOCK:
            items = _load_raw()
            items.append(snap)
            if len(items) > HISTORY_MAX:
                items = items[-HISTORY_MAX:]
            _save_raw(items)
        log.info("history snapshot saved (total=%d)", len(items))
    except Exception as e:
        log.warning("record_snapshot failed: %s", e)


def load_history():
    """Saari history (list of snapshots)."""
    with _LOCK:
        return _load_raw()


# =============================================================================
# Insights — latest vs purana compare karke "kya badla" nikaalo
# =============================================================================
def _pct_change(old, new):
    if old <= 0:
        return None if new <= 0 else 100.0
    return round((new - old) / old * 100)


def compute_insights(items):
    """
    Latest snapshot ko ~purane (history start ya 7+ snapshot pehle) se compare
    karke top movers nikaalo. Returns list of short insight strings.
    """
    if len(items) < 2:
        return []

    latest = items[-1]
    # Baseline: ~7 snapshots pehle (ya sabse purana available).
    baseline = items[max(0, len(items) - 8)]

    out = []

    # 1) Party spend movers
    for party, new_v in latest.get("party_spend", {}).items():
        old_v = baseline.get("party_spend", {}).get(party, 0)
        ch = _pct_change(old_v, new_v)
        if ch is not None and abs(ch) >= 25 and new_v >= 1000:
            arrow = "📈 +" if ch > 0 else "📉 "
            out.append(f"{arrow}{ch}% — {party} ka spend {'badha' if ch>0 else 'ghata'} "
                       f"(₹{old_v:,} → ₹{new_v:,})")

    # 2) Narrative movers
    for narr, new_v in latest.get("narratives", {}).items():
        old_v = baseline.get("narratives", {}).get(narr, 0)
        if new_v - old_v >= 3:
            mult = f"{round(new_v/old_v,1)}x" if old_v > 0 else "naya"
            out.append(f"🎯 '{narr}' narrative upar — {old_v} → {new_v} ads ({mult})")

    # 3) Stance shift (against AAP)
    a_old = baseline.get("stance", {}).get("against", 0)
    a_new = latest.get("stance", {}).get("against", 0)
    if a_new - a_old >= 3:
        out.append(f"⚔️ AAP ke against ads badhe — {a_old} → {a_new}")
    elif a_old - a_new >= 3:
        out.append(f"🛡️ AAP ke against ads ghate — {a_old} → {a_new}")

    return out[:8]
