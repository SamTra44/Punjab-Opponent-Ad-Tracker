# config.py
# -----------------------------------------------------------------------------
# Saari configuration yahan rakhi hai: opponent Page IDs, search terms,
# theme keyword mapping, aur env-based settings (token, admin login).
# Beginner note: env var pehle dekho, warna sensible default use karo.
# -----------------------------------------------------------------------------

import os

# --- Meta / Facebook Graph API settings -------------------------------------
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v21.0")
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/ads_archive"

# Sirf India ke ads (Punjab specifically API se filter nahi hota, isliye
# region-level filtering normalize step + frontend region chips se hoti hai).
AD_REACHED_COUNTRIES = '["IN"]'
# ALL = active + band ho chuki (stopped) dono. Maximum coverage ke liye default
# ALL; env se "ACTIVE" karke sirf live ads bhi le sakte ho.
AD_ACTIVE_STATUS = os.environ.get("AD_ACTIVE_STATUS", "ALL")
AD_TYPE = "POLITICAL_AND_ISSUE_ADS"
RESULT_LIMIT = int(os.environ.get("META_RESULT_LIMIT", "100"))

# Kaunse fields chahiye Meta se (spec ke according).
AD_FIELDS = ",".join([
    "id",
    "page_name",
    "page_id",
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "spend",
    "impressions",
    "currency",
    "demographic_distribution",
    "delivery_by_region",
    "publisher_platforms",
    "ad_snapshot_url",
])

# --- Opponent Pages (party-wise) --------------------------------------------
# IMPORTANT: Yeh Page IDs example/placeholder hain. Real Page IDs Graph API
# Explorer ya facebook page "About > Page transparency" se nikaal ke yahan
# daalo. Env var OPPONENT_PAGES_JSON set karke override bhi kar sakte ho.
#
# Format: { "PARTY": ["pageid1", "pageid2", ...] }
import json as _json

_DEFAULT_OPPONENT_PAGES = {
    # NOTE: Ye real, verified Page IDs hain — Meta Ad Library se confirm kiye gaye.
    # Har party ka official HQ page + 1-2 prominent leaders. Aur add karne ho to
    # Page ID dhoondh ke list mein daal do.
    "BJP": [
        "520972198086866",   # BJP Punjab (official)
        "108185348592423",   # Sadda Tarun Chugh (BJP Punjab in-charge)
        "1656810004631832",  # Youth 4 BJP
    ],
    "INC": [
        "1136547986210410",  # Congress Punjab (official)
        "467983349958631",   # Partap Singh Bajwa (LoP, Punjab Congress)
        "914745555282991",   # Jaiveer Shergill
    ],
    "SAD": [
        "163382127013868",   # Shiromani Akali Dal (official)
        "107878575961821",   # Sukhbir Singh Badal (SAD President)
        "270111243000982",   # Harsimrat Kaur Badal
    ],
    "AAP": [
        # Apni party (benchmarking ke liye optional) — official AAP Punjab /
        # Bhagwant Mann ke Page IDs yahan daal sakte ho.
    ],
}


def _load_opponent_pages():
    """Env se JSON override support karo, warna default."""
    raw = os.environ.get("OPPONENT_PAGES_JSON", "").strip()
    if raw:
        try:
            data = _json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            # Galat JSON ho to crash mat karo, default pe gir jao.
            pass
    return _DEFAULT_OPPONENT_PAGES


OPPONENT_PAGES = _load_opponent_pages()

# Page ID -> Party reverse lookup (normalize ke time party tag karne ke liye).
PAGE_TO_PARTY = {}
for _party, _ids in OPPONENT_PAGES.items():
    for _pid in _ids:
        PAGE_TO_PARTY[str(_pid)] = _party

# --- Broad Punjab-wide political search --------------------------------------
# FETCH_ALL_POLITICAL=True hone par official pages ke ALAWA ye broad search bhi
# chalega — jisse non-official pages (news, individual leaders, proxy/support
# pages) ke political ads bhi capture hote hain. Frontend pe official vs
# non-official filter milta hai.
FETCH_ALL_POLITICAL = os.environ.get("FETCH_ALL_POLITICAL", "1") not in ("0", "false", "False")

# Punjab ke political ads pakadne ke liye broad keywords (English + Gurmukhi).
# "ਪੰਜਾਬ" (Punjab) wide net daalta hai; baaki party/leader specific.
# Broad sweep terms — maqsad: keyword pe depend kiye bina HAR Punjab political ad
# capture ho jaaye. Wide nets (Punjab/sarkar in 3 scripts) + leaders + districts +
# issues. Overlap chalega — baad mein ad-id se dedup ho jaata hai. Claude phir har
# ad ko khud padh ke stance/party classify karta hai.
SEARCH_TERMS = [
    # --- widest Punjab nets (Gurmukhi = lagbhag sirf Punjab ki ads) ---
    "ਪੰਜਾਬ", "Punjab", "पंजाब",
    "ਸਰਕਾਰ", "ਵੋਟ", "ਚੋਣ", "ਲੋਕ",            # govt / vote / election / people
    "Punjab government", "Punjab election", "Punjab politics",
    # --- parties (Punjab-qualified, taaki national noise na aaye) ---
    "ਆਮ ਆਦਮੀ ਪਾਰਟੀ", "AAP Punjab",
    "BJP Punjab", "ਭਾਜਪਾ ਪੰਜਾਬ",
    "Punjab Congress", "ਕਾਂਗਰਸ ਪੰਜਾਬ",
    "Shiromani Akali Dal", "ਅਕਾਲੀ ਦਲ",      # SAD khud Punjab-specific party hai
    # --- leaders (sab Punjab ke — unambiguous) ---
    "Bhagwant Mann", "ਭਗਵੰਤ ਮਾਨ", "ਕੇਜਰੀਵਾਲ",
    "Sukhbir Badal", "Sunil Jakhar", "Amarinder Singh",
    "Partap Singh Bajwa", "Ravneet Bittu", "Raja Warring", "Charanjit Channi",
    # --- districts (har ek pakka Punjab) ---
    "Amritsar", "Ludhiana", "Jalandhar", "Patiala", "Bathinda",
    "Mohali", "Hoshiarpur", "Ferozepur", "Sangrur", "Gurdaspur",
    "Firozpur", "Moga", "Kapurthala", "Faridkot",
    # --- issues / narratives (Punjab-anchored) ---
    "ਨਸ਼ਾ", "nasha drugs Punjab", "ਕਿਸਾਨ", "kisan Punjab",
    "Punjab naukri jobs", "Punjab bijli electricity",
]

# Pagination + cap. Maximum coverage ke liye deep pagination. Pehla refresh
# slow hoga (hazaaron ads + Claude classify), par classifier cache karta hai to
# baad ke refresh fast — sirf NAYI ads classify hoti hain. Sab env se tunable.
MAX_PAGES_PER_QUERY = int(os.environ.get("MAX_PAGES_PER_QUERY", "6"))   # 6*100 = ~600/term
MAX_TOTAL_ADS = int(os.environ.get("MAX_TOTAL_ADS", "4000"))           # dashboard/archive cap
# Saare search terms/pages parallel fetch karne ke liye threads (warna bahut slow).
# Zyada workers = fast par Meta rate-limit (#613) ka risk. 4 = achha balance.
MAX_FETCH_WORKERS = int(os.environ.get("MAX_FETCH_WORKERS", "4"))

# Search-term result ko party guess karne ke liye page_name keyword mapping.
PARTY_NAME_HINTS = {
    "BJP": ["bjp", "bharatiya janata", "modi", "kamal"],
    "INC": ["congress", "inc ", "rahul gandhi", "warring", "hath"],
    "SAD": ["akali", "shiromani", "badal", "panth"],
    "AAP": ["aam aadmi", "aap ", "kejriwal", "bhagwant mann", "jhadu"],
}

# --- Theme auto-detect (simple keyword mapping) -----------------------------
# Ad ke text mein in keywords ko dhoondh ke theme assign karte hain.
# Order matters: pehla match jeet jata hai.
# NOTE: Punjab ke real ads zyadatar Punjabi (Gurmukhi) script mein hote hain,
# isliye har theme mein English + Hinglish + Punjabi (Gurmukhi) keywords dono hain.
THEME_KEYWORDS = [
    ("Drugs / Law & Order", [
        "drug", "nasha", "chitta", "crime", "law and order", "gangster",
        "smuggl", "police",
        "ਨਸ਼ੇ", "ਨਸ਼ਾ", "ਨਸ਼ਿਆਂ", "ਚਿੱਟਾ", "ਗੈਂਗਸਟਰ", "ਰੰਗਦਾਰੀ", "ਪੁਲਿਸ",
        "ਕਤਲ", "ਜੁਰਮ", "ਅਪਰਾਧ", "ਡੋਪ ਟੈਸਟ"]),
    ("Unemployment / Jobs", [
        "unemploy", "berozgar", "rozgar", "job", "naukri", "employment",
        "ਨੌਕਰੀ", "ਨੌਕਰੀਆਂ", "ਰੋਜ਼ਗਾਰ", "ਬੇਰੋਜ਼ਗਾਰ", "ਮੁਲਾਜ਼ਮ", "ਮੁਲਾਜ਼ਮਾਂ"]),
    ("Kisan / Agrarian", [
        "kisan", "farmer", "agri", "fasal", "msp", "mandi", "crop", "stubble",
        "parali",
        "ਕਿਸਾਨ", "ਫਸਲ", "ਮੰਡੀ", "ਪਰਾਲੀ", "ਖੇਤੀ", "ਝੋਨਾ", "ਕਣਕ"]),
    ("Central Schemes", [
        "modi", "central scheme", "ayushman", "pm ", "ujjwala", "kisan samman",
        "yojana", "garib kalyan",
        "ਮੋਦੀ", "ਯੋਜਨਾ", "ਕੇਂਦਰ ਸਰਕਾਰ", "ਆਯੁਸ਼ਮਾਨ"]),
    ("Panthic / Identity", [
        "panth", "sikh", "bandi singh", "gurdwara", "religi", "beadbi",
        "sacrilege", "akal takht",
        "ਪੰਥ", "ਸਿੱਖ", "ਗੁਰਦੁਆਰਾ", "ਬੇਅਦਬੀ", "ਅਕਾਲ ਤਖ਼ਤ", "ਕਤਲੇਆਮ",
        "ਬੰਦੀ ਸਿੰਘ"]),
    ("Youth / Education", [
        "youth", "student", "education", "school", "college", "scholarship",
        "vidya", "padhai",
        "ਨੌਜਵਾਨ", "ਵਿਦਿਆਰਥੀ", "ਸਿੱਖਿਆ", "ਸਕੂਲ", "ਕਾਲਜ", "ਪੜ੍ਹਾਈ"]),
    ("Development / Economy", [
        "develop", "vikas", "road", "infrastructure", "smart city", "bijli",
        "electricity", "water", "sadak", "industry", "investment",
        "ਵਿਕਾਸ", "ਉਦਯੋਗ", "ਨਿਵੇਸ਼", "ਸੜਕ", "ਬਿਜਲੀ", "ਪਾਣੀ", "ਆਰਥਿਕ",
        "ਆਰਥਿਕਤਾ", "ਵਿਕਾਸ ਕਾਰਜ"]),
    ("Governance / AAP Attack", [
        "mann sarkar", "kejriwal", "broken promise", "vaada",
        "ਮਾਨ ਸਰਕਾਰ", "ਭਗਵੰਤ ਮਾਨ", "ਆਪ", "ਧਰਨਾ", "ਧਰਨੇ", "ਨਾਕਾਮੀ",
        "ਵਾਅਦਾ", "ਵਾਅਦੇ", "ਬਦਲਾਅ"]),
]
DEFAULT_THEME = "General / Other"

# --- Punjab focus (optional) ------------------------------------------------
# Meta har political ad ko Punjab ke saath aaspaas ke states (Haryana, Delhi,
# HP...) mein bhi deliver karta hai. By default hum koi ad DROP nahi karte —
# saare states region filter mein dikhte hain, aur user kisi bhi state pe click
# karke us state ki ads dekh sakta hai (Punjab default focus).
# Agar kabhi sirf Punjab-delivered ads chahiye to env mein PUNJAB_ONLY=1 kar do.
PUNJAB_ONLY = os.environ.get("PUNJAB_ONLY", "0") not in ("0", "false", "False")

# Punjab ko pehchanne ke liye: "Punjab" (Meta state-level) + major districts/
# cities (demo data aur kabhi-kabhi city-level region ke liye). Sab lowercase.
PUNJAB_DISTRICTS = {
    "amritsar", "barnala", "bathinda", "faridkot", "fatehgarh sahib",
    "fazilka", "ferozepur", "firozpur", "gurdaspur", "hoshiarpur",
    "jalandhar", "kapurthala", "ludhiana", "mansa", "moga", "mohali",
    "sas nagar", "muktsar", "sri muktsar sahib", "pathankot", "patiala",
    "rupnagar", "ropar", "sangrur", "shaheed bhagat singh nagar", "nawanshahr",
    "tarn taran", "malerkotla", "chandigarh",
}


# --- Claude AI classification (stance + narrative) --------------------------
# Client = AAP. Claude har ad ka text padh ke batata hai ki ad AAP ke against
# hai, support mein hai, ya neutral — aur konse narrative theme mein hai.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLASSIFY_MODEL = os.environ.get("CLASSIFY_MODEL", "claude-haiku-4-5")
CLASSIFY_ENABLED = os.environ.get("CLASSIFY_ENABLED", "1") not in ("0", "false", "False")
CLASSIFY_BATCH_SIZE = int(os.environ.get("CLASSIFY_BATCH_SIZE", "10"))   # ads per API call
CLASSIFY_MAX_WORKERS = int(os.environ.get("CLASSIFY_MAX_WORKERS", "6"))  # parallel calls

# Strategy brief ke liye smart model (on-demand single call — quality > cost).
STRATEGY_MODEL = os.environ.get("STRATEGY_MODEL", "claude-opus-4-8")

# Allowed narrative categories (Claude inme se ek choose karega).
NARRATIVE_CATEGORIES = [
    "Drugs / Law & Order",
    "Unemployment / Jobs",
    "Kisan / Agrarian",
    "Central Schemes",
    "Panthic / Identity",
    "Youth / Education",
    "Development / Economy",
    "Governance / AAP Attack",
    "Welfare / Freebies",
    "Corruption",
    "Women Safety",
    "Health",
    "Other",
]

# --- Auth -------------------------------------------------------------------
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-please")

# DESKTOP_MODE: desktop app (local 127.0.0.1) mein login skip — kyunki yeh
# user ke apne PC pe chalta hai, network pe expose nahi hota. desktop_app.py
# yeh NI_DESKTOP=1 set karta hai. Railway/web pe yeh OFF rehta hai (auth chalu).
DESKTOP_MODE = os.environ.get("NI_DESKTOP") == "1"

# --- Scheduler --------------------------------------------------------------
REFRESH_HOURS = int(os.environ.get("REFRESH_HOURS", "6"))

# --- Server -----------------------------------------------------------------
PORT = int(os.environ.get("PORT", "5000"))
