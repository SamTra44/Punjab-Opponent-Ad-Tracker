# usage.py
# -----------------------------------------------------------------------------
# Har Claude (Anthropic) API call ka token usage + estimated cost record karta
# hai, aur super-admin billing dashboard ke liye aggregate deta hai.
# Cost = tokens x model price (Anthropic public pricing). INR me convert.
# -----------------------------------------------------------------------------
import os
import sqlite3
import threading
import logging
from datetime import datetime, timezone, date

log = logging.getLogger("usage")

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB = os.environ.get("USAGE_DB", os.path.join(_DIR, "usage.db"))
_LOCK = threading.Lock()
USD_INR = float(os.environ.get("USD_INR", "85"))

# Price per 1,000,000 tokens (USD): (input, output) — Anthropic public pricing.
PRICES = {
    "claude-fable-5":   (10.0, 50.0),
    "claude-opus-4-8":  (5.0, 25.0),
    "claude-opus-4-7":  (5.0, 25.0),
    "claude-opus-4-6":  (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _price(model):
    for k, v in PRICES.items():
        if model and str(model).startswith(k):
            return v
    return (5.0, 25.0)


def _conn():
    os.makedirs(_DIR, exist_ok=True)
    return sqlite3.connect(DB, timeout=15)


def _init():
    c = _conn()
    try:
        c.execute("CREATE TABLE IF NOT EXISTS usage (t TEXT, model TEXT, "
                  "feature TEXT, in_tok INTEGER, out_tok INTEGER, cost_usd REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_usage_t ON usage(t)")
        c.commit()
    finally:
        c.close()


try:
    _init()
except Exception as e:  # pragma: no cover
    log.warning("usage init failed: %s", e)


def record(model, in_tok, out_tok, feature="ai", cache_read=0, cache_write=0):
    """Ek Claude call ka usage + cost save karo."""
    try:
        pi, po = _price(model)
        # cached input ~0.1x, cache-write ~1.25x (approx)
        cost = ((int(in_tok or 0) / 1e6) * pi
                + (int(out_tok or 0) / 1e6) * po
                + (int(cache_read or 0) / 1e6) * pi * 0.1
                + (int(cache_write or 0) / 1e6) * pi * 1.25)
        with _LOCK:
            c = _conn()
            try:
                c.execute("INSERT INTO usage VALUES (?,?,?,?,?,?)",
                          (datetime.now(timezone.utc).isoformat(), str(model or "?"),
                           feature, int(in_tok or 0) + int(cache_read or 0),
                           int(out_tok or 0), cost))
                c.commit()
            finally:
                c.close()
    except Exception as e:
        log.warning("usage record failed: %s", e)


def record_resp(model, resp, feature="ai"):
    """Anthropic response object se usage nikaal ke record karo (safe)."""
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return
        record(model, getattr(u, "input_tokens", 0) or 0,
               getattr(u, "output_tokens", 0) or 0, feature,
               cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
               cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0)
    except Exception as e:
        log.warning("usage record_resp failed: %s", e)


def summary():
    """Billing dashboard ke liye aggregate: total/today/month + model/feature wise."""
    try:
        c = _conn()
        try:
            def q(sql, p=()):
                return c.execute(sql, p).fetchall()
            today = date.today().isoformat()
            month = date.today().replace(day=1).isoformat()
            r = USD_INR
            tot = q("SELECT COALESCE(SUM(in_tok),0), COALESCE(SUM(out_tok),0), "
                    "COALESCE(SUM(cost_usd),0), COUNT(*) FROM usage")[0]
            tday = q("SELECT COALESCE(SUM(cost_usd),0) FROM usage WHERE "
                     "substr(t,1,10)=?", (today,))[0][0]
            tmon = q("SELECT COALESCE(SUM(cost_usd),0) FROM usage WHERE "
                     "substr(t,1,10)>=?", (month,))[0][0]
            bm = q("SELECT model, SUM(in_tok), SUM(out_tok), SUM(cost_usd), "
                   "COUNT(*) FROM usage GROUP BY model ORDER BY SUM(cost_usd) DESC")
            bf = q("SELECT feature, SUM(cost_usd), COUNT(*) FROM usage "
                   "GROUP BY feature ORDER BY SUM(cost_usd) DESC")
            daily = q("SELECT substr(t,1,10) d, SUM(cost_usd) FROM usage "
                      "GROUP BY substr(t,1,10) ORDER BY d DESC LIMIT 14")
            return {
                "available": True, "usd_inr": r,
                "total": {"in_tok": tot[0], "out_tok": tot[1],
                          "cost_usd": round(tot[2], 4),
                          "cost_inr": round(tot[2] * r), "calls": tot[3]},
                "today_inr": round(tday * r), "month_inr": round(tmon * r),
                "by_model": [{"model": m or "?", "in_tok": i, "out_tok": o,
                              "cost_inr": round((cu or 0) * r), "calls": n}
                             for m, i, o, cu, n in bm],
                "by_feature": [{"feature": f or "ai", "cost_inr": round((cu or 0) * r),
                                "calls": n} for f, cu, n in bf],
                "daily": [{"day": d2, "cost_inr": round((cu or 0) * r)}
                          for d2, cu in reversed(daily)],
            }
        finally:
            c.close()
    except Exception as e:
        log.warning("usage summary failed: %s", e)
        return {"available": False}
