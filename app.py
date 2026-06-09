# app.py
# -----------------------------------------------------------------------------
# Flask app: routes, session-based login, APScheduler (6 ghante refresh +
# in-memory cache), aur Meta Ad Library data serve karta hai.
#
# Run locally:  python app.py
# Production:   gunicorn app:app   (Railway Procfile)
# -----------------------------------------------------------------------------

import logging
import threading
from datetime import datetime, timezone
from functools import wraps

# IMPORTANT: .env ko config import se PEHLE load karo, taaki local dev mein
# env vars config.py tak pahunch jaaye. Railway pe env already set hote hain.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)
from apscheduler.schedulers.background import BackgroundScheduler

import config
import meta_api
import classifier
import strategy
import history

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


@app.after_request
def _no_cache_html(resp):
    """HTML pages ko cache mat karo — browser hamesha latest dashboard le.
    (Isse 'purana cached version atak gaya' wali dikkat khatam hoti hai.)"""
    ctype = resp.headers.get("Content-Type", "")
    if ctype.startswith("text/html"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp

# =============================================================================
# In-memory cache — scheduler isse har 6 ghante refresh karta hai.
# =============================================================================
CACHE = {
    "mode": "demo",
    "count": 0,
    "ads": [],
    "party_spend": [],
    "top_spender": "N/A",
    "top_themes": [],
    "errors": [],
    "updated_at": None,
    # ready=False -> abhi pehli fetch chal rahi hai (warm-up). Frontend isse
    # dekh ke "loading" dikhata hai aur auto-poll karta hai jab tak ready na ho.
    "ready": False,
}
_CACHE_LOCK = threading.Lock()


def refresh_cache():
    """Meta se fresh data laao aur CACHE update karo (thread-safe)."""
    log.info("Refreshing ad cache from Meta Ad Library...")
    try:
        payload = meta_api.fetch_all_ads()
    except Exception as e:
        # Kuch bhi unexpected fail ho to app crash na ho — purana cache rakho.
        log.exception("refresh_cache failed: %s", e)
        return

    # Claude se stance (against/support AAP) + narrative classify karwao.
    # Sirf naye ads classify hote hain (cached), isliye yeh fast rehta hai.
    try:
        classifier.enrich_ads(payload.get("ads", []))
        payload.update(classifier.build_ai_aggregates(payload.get("ads", [])))
        # Damage Radar: stance ke baad anti-AAP ads ko threat-rank karo.
        meta_api.assign_damage_levels(payload.get("ads", []))
    except Exception as e:
        log.warning("AI classification skipped: %s", e)

    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["ready"] = True  # pehli fetch complete -> frontend ko data dikhao
    with _CACHE_LOCK:
        CACHE.update(payload)

    # Trend Over Time: is refresh ka snapshot history mein save karo.
    try:
        history.record_snapshot(payload)
    except Exception as e:
        log.warning("history record skipped: %s", e)
    log.info("Cache updated: mode=%s count=%s top_spender=%s",
             payload.get("mode"), payload.get("count"),
             payload.get("top_spender"))


# =============================================================================
# Auth helpers
# =============================================================================
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # Desktop app (local) mein login skip; web pe normal auth.
        if config.DESKTOP_MODE or session.get("logged_in"):
            return view(*args, **kwargs)
        return redirect(url_for("login", next=request.path))
    return wrapped


# =============================================================================
# Routes
# =============================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        if user == config.ADMIN_USER and pw == config.ADMIN_PASS:
            session["logged_in"] = True
            session["user"] = user
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        error = "Galat username ya password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    return render_template("index.html",
                           refresh_hours=config.REFRESH_HOURS,
                           user=session.get("user", "admin"))


@app.route("/api/ads")
@login_required
def api_ads():
    """Cached JSON return karta hai (fast — per-request live call nahi)."""
    with _CACHE_LOCK:
        # Shallow copy taaki response ke time lock chhota rahe.
        data = dict(CACHE)
    return jsonify(data)


@app.route("/api/refresh", methods=["POST"])
@login_required
def api_refresh():
    """Manual refresh trigger — abhi Meta se data laata hai."""
    refresh_cache()
    with _CACHE_LOCK:
        data = dict(CACHE)
    return jsonify({"ok": True, "mode": data.get("mode"),
                    "count": data.get("count"),
                    "updated_at": data.get("updated_at")})


@app.route("/api/translate", methods=["POST"])
@login_required
def api_translate():
    """Ek ad ka text Hindi mein translate karke return karta hai (cached)."""
    data = request.get_json(silent=True) or {}
    ad_id = data.get("id", "")
    text = data.get("text", "")
    if not text:
        return jsonify({"ok": False, "error": "no text"}), 400
    hindi = classifier.translate_to_hindi(ad_id, text)
    if hindi is None:
        return jsonify({"ok": False, "error": "AI off ya translate fail"})
    return jsonify({"ok": True, "hindi": hindi})


@app.route("/api/strategy", methods=["GET", "POST"])
@login_required
def api_strategy():
    """
    GET  -> last cached strategy brief (agar generate ho chuki ho).
    POST -> current ads se nayi strategy brief generate karo (Claude Opus).
    """
    if request.method == "POST":
        with _CACHE_LOCK:
            ads = list(CACHE.get("ads", []))
        result = strategy.generate_brief(ads)
        if result.get("generated"):
            result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return jsonify(result)
    # GET -> cached
    return jsonify(strategy.get_cached())


@app.route("/api/counter", methods=["POST"])
@login_required
def api_counter():
    """Ek anti-AAP ad ka specific counter generate karo (Damage Radar)."""
    data = request.get_json(silent=True) or {}
    ad_id = data.get("id", "")
    text = data.get("text", "")
    narrative = data.get("narrative", "")
    audience = data.get("audience", "")
    if not text:
        return jsonify({"ok": False, "error": "no text"}), 400
    counter = classifier.generate_counter(ad_id, text, narrative, audience)
    if counter is None:
        return jsonify({"ok": False, "error": "AI off ya fail"})
    return jsonify({"ok": True, "counter": counter})


@app.route("/api/history")
@login_required
def api_history():
    """Trend Over Time data — snapshots + auto-insights."""
    items = history.load_history()
    return jsonify({
        "count": len(items),
        "snapshots": items,
        "insights": history.compute_insights(items),
    })


@app.route("/health")
def health():
    """Railway/uptime checks ke liye simple health endpoint (no auth)."""
    return jsonify({"status": "ok", "mode": CACHE.get("mode"),
                    "count": CACHE.get("count")})


# =============================================================================
# Scheduler setup — har REFRESH_HOURS ghante cache refresh.
# =============================================================================
scheduler = BackgroundScheduler(daemon=True)


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(refresh_cache, "interval",
                      hours=config.REFRESH_HOURS,
                      id="refresh_ads", replace_existing=True)
    scheduler.start()
    log.info("Scheduler started — refresh every %s hours.",
             config.REFRESH_HOURS)


# App startup pe ek baar warm-up fetch + scheduler chalao.
# gunicorn ke under bhi yeh import-time pe chalega.
def _bootstrap():
    refresh_cache()
    start_scheduler()


# Background thread se warm-up (taaki gunicorn boot block na ho).
threading.Thread(target=_bootstrap, daemon=True).start()


if __name__ == "__main__":
    # Local dev server. Railway pe gunicorn use hota hai (Procfile).
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
