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

from io import BytesIO

from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for, send_file)
from apscheduler.schedulers.background import BackgroundScheduler

import config
import meta_api
import classifier
import strategy
import history
import intelligence

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


@app.route("/api/audience")
@login_required
def api_audience():
    """Audience Vulnerability — opponents kis segment ko target kar rahe."""
    with _CACHE_LOCK:
        ads = list(CACHE.get("ads", []))
    return jsonify(intelligence.audience_vulnerability(ads))


@app.route("/api/forecast", methods=["POST"])
@login_required
def api_forecast():
    """Narrative Forecast — Claude predict kare konsa narrative chadega."""
    with _CACHE_LOCK:
        ads = list(CACHE.get("ads", []))
    hist = history.load_history()
    return jsonify(intelligence.generate_forecast(hist, ads))


@app.route("/api/creative", methods=["POST"])
@login_required
def api_creative():
    """Counter-Ad Creative — ek narrative ka ready-to-post ad."""
    data = request.get_json(silent=True) or {}
    narrative = data.get("narrative", "")
    audience = data.get("audience", "")
    attack = data.get("attack_text", "")
    if not narrative:
        return jsonify({"ok": False, "error": "narrative chahiye"}), 400
    creative = classifier.generate_creative(narrative, audience, attack)
    if creative is None:
        return jsonify({"ok": False, "error": "AI off ya fail"})
    return jsonify({"ok": True, "creative": creative})


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


@app.route("/api/export")
@login_required
def api_export():
    """Saari ads ka data Excel (.xlsx) mein export karo (download)."""
    with _CACHE_LOCK:
        ads = list(CACHE.get("ads", []))
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except Exception:
        return jsonify({"ok": False, "error": "openpyxl not installed"}), 500

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Opponent Ads"

    headers = [
        "Facebook Page", "Handle", "Party", "Source", "Stance", "Damage Level",
        "Narrative", "AI Summary", "Spend (range)", "Impressions (range)",
        "Audience", "Regions", "Platforms", "Started", "Theme (keyword)",
        "Ad Text", "View on Meta (link)", "Ad ID",
    ]
    ws.append(headers)

    stance_word = {"against": "Against AAP", "support": "Pro-AAP",
                   "neutral": "Neutral", "unknown": ""}
    for a in ads:
        aud = a.get("audience") or {}
        aud_str = (f"{aud.get('gender_pct','')}% {aud.get('gender_top','')}, "
                   f"{aud.get('age_top','')}") if aud else ""
        ws.append([
            a.get("page", ""), a.get("handle", ""), a.get("party", ""),
            a.get("source", ""), stance_word.get(a.get("stance", ""), a.get("stance", "")),
            (a.get("damage_level") or "").upper(),
            a.get("narrative", "") or a.get("theme", ""),
            a.get("narrative_summary", ""), a.get("spend", ""), a.get("impr", ""),
            aud_str, ", ".join(a.get("regions", []) or []),
            ", ".join(a.get("plat", []) or []), a.get("start", ""),
            a.get("theme", ""), a.get("text", ""), a.get("snapshot_url", ""),
            a.get("id", ""),
        ])

    # Header styling
    hdr_font = Font(bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="1F2A37")
    for cell in ws[1]:
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"

    # Column widths (rough but readable)
    widths = [26, 16, 8, 14, 12, 12, 22, 34, 20, 20, 22, 26, 18, 12, 18, 60, 40, 18]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = "narrative_intelligence_ads.xlsx"
    return send_file(
        bio, as_attachment=True, download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


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
