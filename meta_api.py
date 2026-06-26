# meta_api.py
# -----------------------------------------------------------------------------
# Yeh module Meta Ad Library API se data laata hai, usse frontend-friendly
# format mein normalize karta hai, aur agar token/API fail ho jaye to
# graceful demo data return karta hai.
# -----------------------------------------------------------------------------

import logging
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config

log = logging.getLogger("meta_api")

# Network timeout (seconds) — taaki ek slow call poora app na hang kare.
REQUEST_TIMEOUT = 25
RATE_LIMIT_RETRIES = 3   # #613 rate-limit pe itni baar backoff-retry karo


# =============================================================================
# 1) LOW-LEVEL: ek API call (page_ids ya search_terms ke saath)
# =============================================================================
_token_lock = threading.Lock()
_token_i = 0


def _all_tokens():
    toks = list(config.META_ACCESS_TOKENS or [])
    if config.META_ACCESS_TOKEN and config.META_ACCESS_TOKEN not in toks:
        toks.insert(0, config.META_ACCESS_TOKEN)
    return toks


def _next_token():
    """
    Round-robin token rotation. Multiple tokens (alag Meta apps se) ka matlab
    har token ka apna rate-limit budget — to 6 tokens ~ 6x data bina #613 ke.
    """
    global _token_i
    toks = _all_tokens()
    if not toks:
        return None
    with _token_lock:
        t = toks[_token_i % len(toks)]
        _token_i += 1
    return t


def _call_ads_archive(search_page_ids=None, search_terms=None, max_pages=None):
    """
    Meta ads_archive endpoint ko call karta hai, after-cursor se paginate karta
    hai, aur har request pe token rotate karta hai (rate-limit se bachne ke liye).
    Returns: (data_list, error_string). error None ho to success.
    """
    if not _all_tokens():
        return [], "META_ACCESS_TOKEN missing"

    if max_pages is None:
        max_pages = config.MAX_PAGES_PER_QUERY

    base = {
        "ad_reached_countries": config.AD_REACHED_COUNTRIES,
        "ad_active_status": config.AD_ACTIVE_STATUS,
        "ad_type": config.AD_TYPE,
        "fields": config.AD_FIELDS,
        "limit": config.RESULT_LIMIT,
    }
    if getattr(config, "AD_DELIVERY_DATE_MIN", ""):
        # Purani (last year ki) ads bhi laao, sirf recent nahi.
        base["ad_delivery_date_min"] = config.AD_DELIVERY_DATE_MIN
    if search_page_ids:
        # Meta expects a JSON-ish list string, e.g. ["123","456"]
        ids = ",".join(f'"{pid}"' for pid in search_page_ids)
        base["search_page_ids"] = f"[{ids}]"
    if search_terms:
        base["search_terms"] = search_terms

    all_data = []
    after = None
    pages = 0

    while pages < max_pages:
        params = dict(base)
        if after:
            params["after"] = after  # token-independent cursor -> har page naya token

        payload = None
        delay = 6
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            params["access_token"] = _next_token()  # har try pe agla token
            try:
                resp = requests.get(config.GRAPH_BASE_URL, params=params,
                                    timeout=REQUEST_TIMEOUT)
                payload = resp.json()
            except requests.exceptions.RequestException as e:
                log.warning("Meta API network error: %s", e)
                return all_data, f"network error: {e}"
            except ValueError as e:
                log.warning("Meta API returned non-JSON: %s", e)
                return all_data, f"bad response: {e}"

            err_obj = payload.get("error") if isinstance(payload, dict) else None
            if err_obj and attempt < RATE_LIMIT_RETRIES:
                msg = (err_obj.get("message") or "").lower()
                code = err_obj.get("code")
                if code == 613 or "rate limit" in msg:
                    time.sleep(delay)       # rate limit: ruk ke + agla token
                    delay *= 2
                    continue
                # Dead/galat token (expire/invalid/permission) -> turant AGLA
                # token try karo. Isse ek token mar jaye to baaki valid tokens se
                # kaam chalta rahe (mixed tokens safe).
                if (code in (190, 102, 10, 200, 463, 467)
                        or "access token" in msg or "expire" in msg
                        or "session has expired" in msg or "permission" in msg):
                    continue
            break  # success ya aur koi error -> aage badho

        # Meta error object aaya?
        if isinstance(payload, dict) and "error" in payload:
            msg = payload["error"].get("message", "unknown error")
            log.warning("Meta API error: %s", msg)
            return all_data, msg

        batch = payload.get("data", []) if isinstance(payload, dict) else []
        all_data.extend(batch)
        pages += 1

        # Agli page ka cursor (token ke bina) — taaki naya token use ho sake.
        after = (((payload.get("paging") or {}).get("cursors") or {}).get("after"))
        if not after or not batch:
            break

    return all_data, None


# =============================================================================
# 2) NORMALIZE helpers
# =============================================================================
def _first(lst):
    """List ka pehla element safely nikaalo, warna empty string."""
    if isinstance(lst, list) and lst:
        return lst[0]
    return ""


def _detect_theme(text):
    """Ad text mein keywords dhoondh ke theme assign karo."""
    low = (text or "").lower()
    for theme, keywords in config.THEME_KEYWORDS:
        for kw in keywords:
            if kw in low:
                return theme
    return config.DEFAULT_THEME


def _guess_party(page_name, page_id):
    """Page ID se party pata karo; warna page_name keywords se guess karo."""
    if str(page_id) in config.PAGE_TO_PARTY:
        return config.PAGE_TO_PARTY[str(page_id)]
    low = (page_name or "").lower()
    for party, hints in config.PARTY_NAME_HINTS.items():
        for h in hints:
            if h in low:
                return party
    return "OTHER"


def _fmt_range(obj, currency_prefix=""):
    """
    Meta spend/impressions ko official RANGE format mein string banao.
    obj = {"lower_bound": "100", "upper_bound": "499"}
    Returns e.g. "₹100 – ₹499" ya "≥ ₹50,000".
    """
    if not isinstance(obj, dict):
        return "N/A"
    lo = obj.get("lower_bound")
    hi = obj.get("upper_bound")

    def _num(x):
        try:
            return f"{int(float(x)):,}"
        except (TypeError, ValueError):
            return None

    lo_s = _num(lo)
    hi_s = _num(hi)
    if lo_s and hi_s:
        return f"{currency_prefix}{lo_s} – {currency_prefix}{hi_s}"
    if lo_s and not hi_s:
        return f"≥ {currency_prefix}{lo_s}"
    if hi_s and not lo_s:
        return f"≤ {currency_prefix}{hi_s}"
    return "N/A"


def _spend_midpoint(obj):
    """Spend range ka midpoint (number) — bars/top-spender ke liye."""
    if not isinstance(obj, dict):
        return 0
    try:
        lo = float(obj.get("lower_bound", 0) or 0)
    except (TypeError, ValueError):
        lo = 0
    try:
        hi = float(obj.get("upper_bound", 0) or 0)
    except (TypeError, ValueError):
        hi = 0
    if hi <= 0:
        return lo
    return (lo + hi) / 2.0


def _parse_audience(demographic_distribution):
    """
    Meta ke demographic_distribution (list of {age, gender, percentage}) se
    audience summary banao: top gender, top age, aur breakdown.
    """
    if not isinstance(demographic_distribution, list) or not demographic_distribution:
        return None
    gender = {}
    age = {}
    for r in demographic_distribution:
        try:
            p = float(r.get("percentage", 0) or 0)
        except (TypeError, ValueError):
            p = 0
        g = (r.get("gender") or "unknown").lower()
        a = r.get("age") or "?"
        gender[g] = gender.get(g, 0) + p
        age[a] = age.get(a, 0) + p

    if not gender and not age:
        return None

    g_top = max(gender, key=gender.get) if gender else None
    a_top = max(age, key=age.get) if age else None
    g_label = {"male": "Mard", "female": "Aurat", "unknown": "Other"}
    return {
        "gender_top": g_label.get(g_top, g_top) if g_top else None,
        "gender_pct": round(gender.get(g_top, 0) * 100) if g_top else 0,
        "age_top": a_top,
        "age_pct": round(age.get(a_top, 0) * 100) if a_top else 0,
        # full gender split for display
        "male_pct": round(gender.get("male", 0) * 100),
        "female_pct": round(gender.get("female", 0) * 100),
    }


def _ranked_regions(delivery_by_region):
    """delivery_by_region ko percentage ke hisaab se sort karke region names."""
    out = []
    if isinstance(delivery_by_region, list):
        try:
            ranked = sorted(
                delivery_by_region,
                key=lambda r: float(r.get("percentage", 0) or 0),
                reverse=True,
            )
        except Exception:
            ranked = delivery_by_region
        for r in ranked:
            name = r.get("region")
            if name:
                out.append(name)
    return out


def _is_punjab_region(name):
    """Region Punjab ka hai? ('Punjab'/'Punjab region' ya koi Punjab district)."""
    low = (name or "").lower().strip()
    if "punjab" in low:
        return True
    return low in config.PUNJAB_DISTRICTS


def _handle_from_name(page_name):
    """Page name se ek pseudo @handle banao display ke liye."""
    if not page_name:
        return "@unknown"
    slug = re.sub(r"[^a-z0-9]+", "", page_name.lower())[:18]
    return f"@{slug or 'page'}"


def _byline(b):
    """Meta 'bylines' (Paid for by) string ya list ho sakta hai -> clean string."""
    if isinstance(b, list):
        return ", ".join(str(x) for x in b if x)
    return str(b or "").strip()


def normalize_ad(raw):
    """Ek raw Meta ad object ko frontend format mein convert karo."""
    page_name = raw.get("page_name", "Unknown Page")
    page_id = raw.get("page_id", "")
    body = _first(raw.get("ad_creative_bodies"))
    title = _first(raw.get("ad_creative_link_titles"))
    text = body or title or "(no creative text)"

    currency = raw.get("currency", "INR")
    cur_prefix = "₹" if currency in ("INR", "") else f"{currency} "

    spend_obj = raw.get("spend", {})
    impr_obj = raw.get("impressions", {})

    # Official = ye page hamari known OPPONENT_PAGES list mein hai.
    is_official = str(page_id) in config.PAGE_TO_PARTY

    # Regions: full ranked list nikaalo, Punjab-relevance check karo.
    ranked_regions = _ranked_regions(raw.get("delivery_by_region"))
    if not ranked_regions:
        # Region data hi nahi -> unknown, drop mat karo (benefit of doubt).
        is_punjab = True
    else:
        is_punjab = any(_is_punjab_region(r) for r in ranked_regions)
    if config.PUNJAB_ONLY:
        # Sirf Punjab regions (jab explicitly PUNJAB_ONLY on ho).
        out_regions = [r for r in ranked_regions if _is_punjab_region(r)]
    else:
        # Saare delivery states rakho — taaki har state ka filter chale.
        out_regions = ranked_regions

    return {
        "id": raw.get("id", ""),
        "page_id": str(page_id),
        "party": _guess_party(page_name, page_id),
        "source": "official" if is_official else "non-official",
        "is_official": is_official,
        "page": page_name,
        "handle": _handle_from_name(page_name),
        "bylines": _byline(raw.get("bylines")),
        "text": text,
        "spend": _fmt_range(spend_obj, cur_prefix),
        "spend_mid": _spend_midpoint(spend_obj),
        "impr": _fmt_range(impr_obj),
        "impr_mid": _spend_midpoint(impr_obj),  # generic range midpoint
        "audience": _parse_audience(raw.get("demographic_distribution")),
        # damage_score base (spend + reach). damage_level baad mein AI stance
        # ke baad assign hota hai (assign_damage_levels).
        "damage_score": round(_spend_midpoint(spend_obj) + _spend_midpoint(impr_obj)),
        "regions": out_regions,
        "is_punjab": is_punjab,
        "plat": raw.get("publisher_platforms", []) or [],
        "start": raw.get("ad_delivery_start_time", ""),
        "stop": raw.get("ad_delivery_stop_time", ""),
        # PUBLIC Ad Library permalink (id se). Meta ka 'ad_snapshot_url' ek
        # render_ad URL hai jisme access_token embedded hota hai — woh browser
        # mein "content not available" deta hai AUR token leak karta hai. Isliye
        # hamesha clean public library link banao.
        "snapshot_url": ("https://www.facebook.com/ads/library/?id="
                         + str(raw.get("id", ""))),
        "theme": _detect_theme(text),
    }


def correct_proxy_party(ads):
    """
    Stance ke baad party fix: ek PRO-AAP (support) ad kabhi opponent party
    (BJP/INC/SAD) ki nahi ho sakti. Aise non-official pages (jaise "Fraud to
    be Akali") jinhe page-naam ke keyword se galat opponent guess kar liya tha,
    unhe AAP-side proxy ("OTHER") maan lo. Official opponent pages chhuo mat.
    """
    fixed = 0
    for a in ads:
        stance, party = a.get("stance"), a.get("party")
        if a.get("is_official"):
            # Official page ka PARTY pakka — par stance contradiction theek karo:
            # official opponent page AAP ko support nahi karta; AAP page khud ko
            # attack nahi karta. Aisa ho to stance neutral (galat claim na ho).
            if party in ("BJP", "INC", "SAD") and stance == "support":
                a["stance"] = "neutral"
                fixed += 1
            elif party == "AAP" and stance == "against":
                a["stance"] = "neutral"
                fixed += 1
            continue
        # Non-official: party guess theek karo (Claude ke baad bhi safety).
        # support (pro-AAP) ad opponent party ki nahi ho sakti
        if stance == "support" and party in ("BJP", "INC", "SAD"):
            a["party"] = "OTHER"
            fixed += 1
        # against (anti-AAP) ad AAP ki nahi ho sakti
        elif stance == "against" and party == "AAP":
            a["party"] = "OTHER"
            fixed += 1
    if fixed:
        log.info("reconciled %d contradictory party/stance ads", fixed)
    return fixed


# =============================================================================
# 3) AGGREGATES: party spend bars, top themes, top spender
# =============================================================================
def _build_aggregates(ads):
    """Normalized ads se sidebar ke liye summary banao."""
    party_spend = {}
    theme_count = {}
    for a in ads:
        party = a.get("party", "OTHER")
        party_spend[party] = party_spend.get(party, 0) + a.get("spend_mid", 0)
        theme = a.get("theme", config.DEFAULT_THEME)
        theme_count[theme] = theme_count.get(theme, 0) + 1

    # Party spend bars (descending).
    spend_bars = [
        {"party": p, "spend": round(v)}
        for p, v in sorted(party_spend.items(), key=lambda x: x[1], reverse=True)
        if v > 0
    ]
    top_spender = spend_bars[0]["party"] if spend_bars else "N/A"

    # Top narrative themes (descending).
    top_themes = [
        {"theme": t, "count": c}
        for t, c in sorted(theme_count.items(), key=lambda x: x[1], reverse=True)
    ][:6]

    return {
        "party_spend": spend_bars,
        "top_spender": top_spender,
        "top_themes": top_themes,
    }


# =============================================================================
# 4) PUBLIC: saare opponents ke ads fetch karo (page_ids + fallback search)
# =============================================================================
def fetch_all_ads():
    """
    Returns a dict:
      {count, ads, mode, party_spend, top_spender, top_themes, errors}
    mode = "live"  -> Meta se data aaya
    mode = "demo"  -> fallback demo data
    """
    # Token hi nahi hai -> seedha demo.
    if not config.META_ACCESS_TOKEN:
        log.info("No META_ACCESS_TOKEN — serving demo data.")
        return _demo_payload(reason="META_ACCESS_TOKEN not set")

    all_raw = []
    errors = []
    got_any = False

    # Saare fetch jobs ikattha karo:
    #  (a) OFFICIAL pages — known opponent Page IDs (is_official=True milta hai).
    #  (b) BROAD search terms — Punjab-wide political ads (news/leaders/proxy bhi).
    jobs = []  # list of (label, kwargs)
    for party, page_ids in config.OPPONENT_PAGES.items():
        clean_ids = [str(p) for p in page_ids if str(p).strip()]
        if clean_ids:
            jobs.append((f"{party} pages", {"search_page_ids": clean_ids}))
    if config.FETCH_ALL_POLITICAL:
        for term in config.SEARCH_TERMS:
            jobs.append((f"search '{term}'", {"search_terms": term}))

    # Sab jobs PARALLEL mein chalao — har job apni paginated call karti hai.
    # Sequential mein 48 terms * 10 pages bahut slow tha; threads se ~minutes me.
    workers = max(1, min(config.MAX_FETCH_WORKERS, len(jobs) or 1))
    log.info("Fetching %d queries with %d workers...", len(jobs), workers)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_call_ads_archive, **kw): label for label, kw in jobs}
        for fut in as_completed(futs):
            label = futs[fut]
            try:
                data, err = fut.result()
            except Exception as e:
                errors.append(f"{label}: {e}")
                continue
            if err:
                errors.append(f"{label}: {err}")
            if data:
                got_any = True
                all_raw.extend(data)

    # Sab fail -> demo fallback.
    if not got_any:
        reason = errors[0] if errors else "no ads returned"
        log.warning("Live fetch failed (%s) — serving demo data.", reason)
        return _demo_payload(reason=reason, errors=errors)

    # De-dup by ad id (official + broad search overlap ho sakta hai).
    seen = set()
    deduped = []
    for raw in all_raw:
        aid = raw.get("id")
        if aid and aid in seen:
            continue
        if aid:
            seen.add(aid)
        deduped.append(raw)

    ads = [normalize_ad(r) for r in deduped]

    # Punjab focus: sirf woh ads jo Punjab mein deliver ho rahi hain.
    # Official opponent pages ke ads hamesha rakho (woh Punjab parties hain).
    if config.PUNJAB_ONLY:
        before = len(ads)
        ads = [a for a in ads if a.get("is_punjab") or a.get("is_official")]
        log.info("Punjab filter: kept %d of %d ads.", len(ads), before)

    # Spend ke hisaab se sort (bade spenders upar) + total cap.
    ads.sort(key=lambda a: a.get("spend_mid", 0), reverse=True)
    if len(ads) > config.MAX_TOTAL_ADS:
        ads = ads[:config.MAX_TOTAL_ADS]

    agg = _build_aggregates(ads)
    agg["official_count"] = sum(1 for a in ads if a["is_official"])
    agg["non_official_count"] = sum(1 for a in ads if not a["is_official"])

    return {
        "mode": "live",
        "count": len(ads),
        "ads": ads,
        "errors": errors,  # partial errors bhi report karo
        **agg,
    }


# =============================================================================
# 5) DEMO DATA (graceful fallback)
# =============================================================================
_DEMO_RAW = [
    {
        "id": "demo_1", "page_name": "BJP Punjab", "page_id": "520972198086866",
        "ad_creative_bodies": ["Punjab ko nashe-mukt banane ke liye BJP ka "
                               "law & order plan. Drugs ke khilaaf zero "
                               "tolerance."],
        "spend": {"lower_bound": "40000", "upper_bound": "44999"},
        "impressions": {"lower_bound": "200000", "upper_bound": "249999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Amritsar", "percentage": "0.4"},
                               {"region": "Ludhiana", "percentage": "0.3"}],
        "publisher_platforms": ["facebook", "instagram"],
        "ad_delivery_start_time": "2026-05-28",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_1",
    },
    {
        "id": "demo_2", "page_name": "Punjab Congress", "page_id": "demo_inc",
        "ad_creative_bodies": ["Berozgari par AAP sarkar fail. Punjab ke "
                               "youth ko rozgar chahiye, jhoothe vaade nahi."],
        "spend": {"lower_bound": "25000", "upper_bound": "29999"},
        "impressions": {"lower_bound": "150000", "upper_bound": "199999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Jalandhar", "percentage": "0.5"},
                               {"region": "Patiala", "percentage": "0.2"}],
        "publisher_platforms": ["facebook"],
        "ad_delivery_start_time": "2026-06-01",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_2",
    },
    {
        "id": "demo_3", "page_name": "Shiromani Akali Dal", "page_id": "163382127013868",
        "ad_creative_bodies": ["Panthic mudde aur Sikh kaum ke haq. Bandi "
                               "Singhan di rihai layi awaaz buland karo."],
        "spend": {"lower_bound": "15000", "upper_bound": "19999"},
        "impressions": {"lower_bound": "80000", "upper_bound": "99999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Amritsar", "percentage": "0.6"},
                               {"region": "Tarn Taran", "percentage": "0.2"}],
        "publisher_platforms": ["facebook", "instagram"],
        "ad_delivery_start_time": "2026-05-20",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_3",
    },
    {
        "id": "demo_4", "page_name": "Punjab BJP", "page_id": "demo_bjp",
        "ad_creative_bodies": ["Modi ji ki central schemes — Ayushman Bharat, "
                               "Kisan Samman Nidhi — Punjab ke kisano ke saath."],
        "spend": {"lower_bound": "35000", "upper_bound": "39999"},
        "impressions": {"lower_bound": "180000", "upper_bound": "199999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Bathinda", "percentage": "0.35"},
                               {"region": "Ludhiana", "percentage": "0.3"}],
        "publisher_platforms": ["facebook", "instagram", "messenger"],
        "ad_delivery_start_time": "2026-06-03",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_4",
    },
    {
        "id": "demo_5", "page_name": "Congress Punjab", "page_id": "1136547986210410",
        "ad_creative_bodies": ["Kisan virodhi neetiyan band karo. MSP di "
                               "guarantee te mandi system bachao."],
        "spend": {"lower_bound": "20000", "upper_bound": "24999"},
        "impressions": {"lower_bound": "120000", "upper_bound": "149999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Sangrur", "percentage": "0.45"},
                               {"region": "Moga", "percentage": "0.25"}],
        "publisher_platforms": ["facebook"],
        "ad_delivery_start_time": "2026-05-30",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_5",
    },
    {
        "id": "demo_6", "page_name": "Shiromani Akali Dal", "page_id": "demo_sad",
        "ad_creative_bodies": ["Pind-pind vikas. Sadak, bijli, paani — Akali "
                               "Dal da development model wapis lao."],
        "spend": {"lower_bound": "10000", "upper_bound": "14999"},
        "impressions": {"lower_bound": "60000", "upper_bound": "79999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Ferozepur", "percentage": "0.4"},
                               {"region": "Faridkot", "percentage": "0.3"}],
        "publisher_platforms": ["facebook", "instagram"],
        "ad_delivery_start_time": "2026-05-25",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_6",
    },
    {
        "id": "demo_7", "page_name": "Punjab BJP", "page_id": "demo_bjp",
        "ad_creative_bodies": ["Youth ke liye skill development aur education "
                               "reforms. Punjab ke students ka future secure."],
        "spend": {"lower_bound": "18000", "upper_bound": "21999"},
        "impressions": {"lower_bound": "90000", "upper_bound": "119999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Mohali", "percentage": "0.5"},
                               {"region": "Chandigarh", "percentage": "0.2"}],
        "publisher_platforms": ["instagram"],
        "ad_delivery_start_time": "2026-06-04",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_7",
    },
    {
        "id": "demo_8", "page_name": "Punjab Congress", "page_id": "demo_inc",
        "ad_creative_bodies": ["Chitta aur drugs ne Punjab di jawaani barbaad "
                               "kar ditti. Law & order patri-pat ho gaya."],
        "spend": {"lower_bound": "30000", "upper_bound": "34999"},
        "impressions": {"lower_bound": "160000", "upper_bound": "199999"},
        "currency": "INR",
        "delivery_by_region": [{"region": "Jalandhar", "percentage": "0.4"},
                               {"region": "Kapurthala", "percentage": "0.25"}],
        "publisher_platforms": ["facebook", "instagram"],
        "ad_delivery_start_time": "2026-06-02",
        "ad_snapshot_url": "https://www.facebook.com/ads/library/?id=demo_8",
    },
]


def assign_damage_levels(ads):
    """
    AI stance assign hone ke BAAD call karo. Anti-AAP (against) ads ko
    damage_score (spend+reach) se rank karke high/medium/low label deta hai.
    Pro/neutral ads threat nahi (damage_level=None).
    """
    for a in ads:
        a["damage_level"] = None

    threats = sorted(
        [a for a in ads if a.get("stance") == "against"],
        key=lambda a: a.get("damage_score", 0),
        reverse=True,
    )
    n = len(threats)
    if n == 0:
        return
    hi_cut = max(1, n // 4)        # top 25% = HIGH
    md_cut = max(hi_cut + 1, n // 2)  # next ~25% = MEDIUM
    for i, a in enumerate(threats):
        if i < hi_cut:
            a["damage_level"] = "high"
        elif i < md_cut:
            a["damage_level"] = "medium"
        else:
            a["damage_level"] = "low"


def _demo_payload(reason="demo", errors=None):
    """Demo ads ko normalize karke poora payload banao."""
    ads = [normalize_ad(r) for r in _DEMO_RAW]
    agg = _build_aggregates(ads)
    agg["official_count"] = sum(1 for a in ads if a["is_official"])
    agg["non_official_count"] = sum(1 for a in ads if not a["is_official"])
    return {
        "mode": "demo",
        "count": len(ads),
        "ads": ads,
        "demo_reason": reason,
        "errors": errors or [],
        **agg,
    }
