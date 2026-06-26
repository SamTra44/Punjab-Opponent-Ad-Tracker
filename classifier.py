# classifier.py
# -----------------------------------------------------------------------------
# Claude (Anthropic) se har ad ka text padhwa ke do cheezein nikaalta hai:
#   1. stance  -> ad AAP (hamare client) ke "against" hai, "support" mein hai,
#                 ya "neutral".
#   2. narrative -> ad konse narrative theme mein chal raha hai + ek short
#                 one-line summary (intel ke liye).
#
# Design notes (beginner-friendly):
# - Official anthropic Python SDK use hota hai (raw HTTP nahi).
# - Model: Haiku 4.5 (sasta + fast) — classification jaise task ke liye perfect.
# - Batching: ek API call mein 10 ads bhejte hain (cost + latency kam).
# - Caching: har ad apni id se cache hota hai — purane ads dobara classify nahi
#   hote, sirf naye. Isse har refresh sasta rehta hai.
# - Concurrency: kai batches parallel mein chalte hain (ThreadPoolExecutor).
# - Agar ANTHROPIC_API_KEY na ho ya API fail ho, to graceful — stance "unknown".
# -----------------------------------------------------------------------------

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import usage

log = logging.getLogger("classifier")

# anthropic SDK optional import — agar install na ho to app crash na ho.
try:
    import anthropic
    _SDK_OK = True
except Exception:  # pragma: no cover
    _SDK_OK = False

# AI tabhi chalega jab SDK ho, key ho, aur enabled ho.
AI_ENABLED = bool(_SDK_OK and config.ANTHROPIC_API_KEY and config.CLASSIFY_ENABLED)

# Client banao (ek baar). Key env se uthti hai.
_client = None
if AI_ENABLED:
    try:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    except Exception as e:  # pragma: no cover
        log.warning("Anthropic client init failed: %s", e)
        AI_ENABLED = False

# In-memory classification cache: ad_id -> {stance, narrative, narrative_summary}
_CACHE = {}

# System prompt — context Claude ko deta hai (AAP = client, Punjab politics).
_SYSTEM = (
    "You are an analyst in the Aam Aadmi Party (AAP) Punjab digital war room. "
    "AAP GOVERNS Punjab (Chief Minister Bhagwant Mann). Opponents are BJP, "
    "Congress (INC), and Shiromani Akali Dal (SAD). Ads are usually in Punjabi "
    "(Gurmukhi), sometimes Hindi/English.\n\n"
    "For each ad decide stance TOWARD AAP — first identify WHO the ad targets:\n"
    "   - 'against' = the ad attacks/criticizes AAP, Bhagwant Mann, or the AAP "
    "(Mann) government.\n"
    "   - 'support' = the ad praises/promotes AAP or Mann, OR attacks an "
    "opponent in a way that favours AAP (e.g. 'AAP better than Congress').\n"
    "   - 'neutral' = the ad attacks a NON-AAP party (Congress, BJP, or Akali "
    "Dal) WITHOUT attacking AAP, OR is general news/issue content not clearly "
    "for/against AAP.\n\n"
    "⚠️ CRITICAL: An ad attacking Congress, BJP, or Akali Dal is NOT 'against' "
    "AAP — it is 'neutral' (or 'support' if it helps AAP). But ANY attack on "
    "Bhagwant Mann or AAP personally — his decisions, arrogance, failures, OR "
    "Panthic/Sikh/Akal-Takht criticism of Mann, OR demands that Mann resign — "
    "IS 'against'. The test: WHO is being attacked? Mann/AAP -> against; some "
    "OTHER party -> neutral.\n\n"
    "Examples:\n"
    "- 'Mann sarkar fail, AAP ne Punjab barbaad kiya' -> against\n"
    "- 'Mann ne Akal Takht da niraadar kita, Sikh kaum naal dhokha' -> against\n"
    "- 'Mann istifa do, July 5 nu andolan' -> against\n"
    "- 'Congress ne Punjab loota, Captain ne kuch na kita' -> neutral\n"
    "- 'BJP ne Congress nu expose kita' -> neutral\n"
    "- 'Congress di purani misgovernance, AAP behtar' -> support\n"
    "- 'AAP ne 50000 naukri ditti' -> support\n\n"
    "⚠️ PUNJABI TONE & IDIOMS — many PRO-AAP ads PRAISE Mann's work in colloquial "
    "Punjabi that sounds negative if read literally. Read the WHOLE message: if the "
    "ad CREDITS the AAP/Mann govt with development (roads built, jobs, clinics, "
    "schools, naye kaam) it is 'support', even if slangy. These praise idioms are "
    "SUPPORT, NOT against:\n"
    "- 'ਸਿਰਾ ਲਾ ਦਿੱਤਾ / siraa laa dita' = did an EXCELLENT job (praise, NOT 'failed')\n"
    "- 'ਨਵਾਂ ਬਣਵਾ ਕੇ ਦਿੱਤਾ / nava road banva ke dita' = delivered/built it (praise)\n"
    "- 'ਜਿੰਨੇ ਕੰਮ ਗਿਣਾਈਏ ਥੋੜੇ ਪੈ ਜਾਣ' = his works are countless/too many (praise)\n"
    "- 'ਕਮਾਲ / ਝੰਡੇ ਗੱਡ ਦਿੱਤੇ / ਵਾਹ ਵਾਹ' = did wonders (praise)\n"
    "More examples:\n"
    "- 'Punjab diyan sadkan da taan siraa hi laata Mann sarkar ne' -> support\n"
    "- 'Pind da road nava banva ke dita gya' -> support\n"
    "- 'Bhagwant Mann de jinne kamm ginaaiye uhne thode pai jaan' -> support\n"
    "Mark 'against' ONLY when the ad clearly CRITICIZES/ATTACKS Mann/AAP (failures, "
    "scams, jhooth, broken promises, resign demands, Akal-Takht criticism of Mann). "
    "If a work/development-credit ad is ambiguous, lean 'support', not against.\n\n"
    "Also identify party = which side is BEHIND the ad (who sponsors/benefits) "
    "by READING the ad message AND page name — never from a name keyword alone:\n"
    "   - 'BJP' = Bharatiya Janata Party or its proxies.\n"
    "   - 'INC' = Congress.\n"
    "   - 'SAD' = Shiromani Akali Dal (Badal).\n"
    "   - 'AAP' = Aam Aadmi Party or PRO-AAP proxy pages.\n"
    "   - 'OTHER' = independent / news / farmer-union / unclear.\n"
    "Judge by who the ad PROMOTES or DEFENDS, not who it merely names.\n"
    "⚠️ IRON RULE: an ad that ATTACKS/mocks a party is NEVER sponsored by that "
    "same party. A page bashing Congress (e.g. 'Pappu Congress') is NOT 'INC'. "
    "A page mocking Akalis (e.g. 'Fraud to be Akali') is NOT 'SAD'. A page "
    "attacking BJP is NOT 'BJP'. For such a page, pick the side it actually "
    "PROMOTES — if it praises AAP, party='AAP'; if it pushes BJP, party='BJP'; "
    "if no party is clearly promoted, party='OTHER'. Never label a page with "
    "the party it is attacking.\n"
    "Party examples:\n"
    "- ad bashes Congress over 1984, promotes nobody -> OTHER (NOT INC)\n"
    "- 'Fraud to be Akali' praises AAP -> AAP\n"
    "- 'BJP Punjab' attacks Mann -> BJP\n"
    "- 'Sukhbir Badal' defends Panth, slams Mann -> SAD\n"
    "- official AAP page praising Mann -> AAP\n\n"
    "Then give: narrative = best-fitting theme from the allowed list; "
    "narrative_summary = punchy <=12 word English summary of the ad's core "
    "message (e.g. 'Blames Mann govt for rising drug crisis'). "
    "Getting the stance TARGET and the sponsoring party right is most important."
)

# Structured output schema (JSON) — Claude isi format mein jawab dega.
_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "stance": {"type": "string",
                               "enum": ["against", "support", "neutral"]},
                    "party": {"type": "string",
                              "enum": ["BJP", "INC", "SAD", "AAP", "OTHER"]},
                    "narrative": {"type": "string",
                                  "enum": config.NARRATIVE_CATEGORIES},
                    "narrative_summary": {"type": "string"},
                },
                "required": ["index", "stance", "party", "narrative",
                             "narrative_summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

_UNKNOWN = {"stance": "unknown", "party": "OTHER", "narrative": "Other",
            "narrative_summary": ""}


def _classify_batch(batch):
    """
    batch = list of (ad_id, page_name, text).
    Returns dict: ad_id -> {stance, narrative, narrative_summary}.
    """
    # Numbered list banao taaki Claude index ke saath jawab de.
    lines = []
    for i, (_aid, page, text) in enumerate(batch, start=1):
        snippet = (text or "").strip().replace("\n", " ")[:500]
        lines.append(f"{i}. [Page: {page}] {snippet}")
    user_msg = (
        "Classify each ad below. Allowed narratives: "
        + ", ".join(config.NARRATIVE_CATEGORIES)
        + ".\n\n" + "\n".join(lines)
    )

    try:
        resp = _client.messages.create(
            model=config.CLASSIFY_MODEL,
            max_tokens=2200,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        usage.record_resp(config.CLASSIFY_MODEL, resp, "classification")
        # output_config format guarantee karta hai ki pehla text block valid JSON ho.
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
    except Exception as e:
        log.warning("classify batch failed: %s", e)
        return {aid: dict(_UNKNOWN) for aid, _p, _t in batch}

    out = {}
    for item in data.get("results", []):
        idx = item.get("index", 0) - 1  # 1-based -> 0-based
        if 0 <= idx < len(batch):
            aid = batch[idx][0]
            out[aid] = {
                "stance": item.get("stance", "unknown"),
                "party": item.get("party", "OTHER"),
                "narrative": item.get("narrative", "Other"),
                "narrative_summary": (item.get("narrative_summary", "") or "")[:120],
            }
    # Jo ads response mein nahi aaye, unhe unknown do.
    for aid, _p, _t in batch:
        out.setdefault(aid, dict(_UNKNOWN))
    return out


def enrich_ads(ads):
    """
    Har ad mein stance/narrative/narrative_summary fields add karta hai.
    Sirf naye (uncached) ads classify hote hain. Returns True agar AI use hua.
    """
    if not AI_ENABLED or not ads:
        # AI off — sabko unknown markers do taaki frontend consistent rahe.
        for a in ads:
            a.update(_CACHE.get(a.get("id"), _UNKNOWN))
            a.setdefault("stance", "unknown")
        return False

    # 1) Konse ads cache mein nahi hain?
    todo = []
    for a in ads:
        aid = a.get("id")
        if aid and aid not in _CACHE:
            todo.append((aid, a.get("page", ""), a.get("text", "")))

    # 2) Batches banao aur parallel mein classify karo.
    if todo:
        batches = [todo[i:i + config.CLASSIFY_BATCH_SIZE]
                   for i in range(0, len(todo), config.CLASSIFY_BATCH_SIZE)]
        log.info("Classifying %d new ads in %d batches...", len(todo), len(batches))
        with ThreadPoolExecutor(max_workers=config.CLASSIFY_MAX_WORKERS) as ex:
            futures = [ex.submit(_classify_batch, b) for b in batches]
            for fut in as_completed(futures):
                try:
                    _CACHE.update(fut.result())
                except Exception as e:
                    log.warning("batch result error: %s", e)

    # 3) Sab ads pe cache se values attach karo.
    for a in ads:
        res = _CACHE.get(a.get("id"), _UNKNOWN)
        a["stance"] = res.get("stance", "unknown")
        a["narrative"] = res.get("narrative", "Other")
        a["narrative_summary"] = res.get("narrative_summary", "")
        # Party: official page = pakka ground-truth; warna Claude ka padha hua
        # jawab (keyword guess ki jagah). AI ne na diya to purana value rehne do.
        official = config.PAGE_TO_PARTY.get(str(a.get("page_id")))
        if official:
            a["party"] = official
        elif res.get("party"):
            a["party"] = res["party"]
    return True


# =============================================================================
# Translation — ad text ko Hindi mein translate karo (on-demand, cached)
# =============================================================================
_TRANSLATE_CACHE = {}  # ad_id -> hindi text

_TRANSLATE_SYSTEM = (
    "You are a translator. Translate the user's political ad text into natural, "
    "simple Hindi (Devanagari script). The source is usually Punjabi (Gurmukhi) "
    "or English. Keep proper nouns/party names readable. Output ONLY the Hindi "
    "translation — no preface, no notes, no transliteration."
)


def translate_to_hindi(ad_id, text):
    """Ek ad ka text Hindi mein translate karo. Cached by ad_id. None on failure."""
    if not AI_ENABLED or not (text or "").strip():
        return None
    if ad_id and ad_id in _TRANSLATE_CACHE:
        return _TRANSLATE_CACHE[ad_id]
    try:
        resp = _client.messages.create(
            model=config.CLASSIFY_MODEL,
            max_tokens=700,
            system=_TRANSLATE_SYSTEM,
            messages=[{"role": "user", "content": text[:1500]}],
        )
        usage.record_resp(config.CLASSIFY_MODEL, resp, "translate")
        out = next((b.text for b in resp.content if b.type == "text"), "").strip()
    except Exception as e:
        log.warning("translate failed: %s", e)
        return None
    if ad_id and out:
        _TRANSLATE_CACHE[ad_id] = out
    return out


# =============================================================================
# Per-ad COUNTER — Damage Radar ke liye, ek anti-AAP ad ka specific jawaab
# =============================================================================
_COUNTER_CACHE = {}  # ad_id -> counter text

_COUNTER_SYSTEM = (
    "You are the chief strategist for Aam Aadmi Party (AAP) Punjab. AAP governs "
    "Punjab (CM Bhagwant Mann). You are given ONE opponent ad that attacks AAP, "
    "with its narrative and target audience. Write a sharp, specific COUNTER for "
    "AAP to run targeting the SAME audience.\n"
    "Output 2 short lines:\n"
    "1) Counter-message (the actual punchy line AAP should say)\n"
    "2) Why it works (1 line, mention the audience/angle)\n"
    "Write ONLY in clean Hindi/Hinglish using DEVANAGARI or Roman script — "
    "do NOT use Punjabi/Gurmukhi script. Be concrete to Punjab (jobs, drugs, "
    "schools, development). No preamble, no markdown headers."
)


def generate_counter(ad_id, text, narrative="", audience_str=""):
    """Ek anti-AAP ad ka counter banao (cached by ad_id). None on failure."""
    if not AI_ENABLED or not (text or "").strip():
        return None
    if ad_id and ad_id in _COUNTER_CACHE:
        return _COUNTER_CACHE[ad_id]
    user = (
        f"OPPONENT AD (attacks AAP):\n{text[:800]}\n\n"
        f"Narrative: {narrative}\nAudience: {audience_str}\n\n"
        "AAP ke liye counter do."
    )
    try:
        resp = _client.messages.create(
            model=config.CLASSIFY_MODEL,
            max_tokens=400,
            system=_COUNTER_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        usage.record_resp(config.CLASSIFY_MODEL, resp, "counter")
        out = next((b.text for b in resp.content if b.type == "text"), "").strip()
    except Exception as e:
        log.warning("counter gen failed: %s", e)
        return None
    if ad_id and out:
        _COUNTER_CACHE[ad_id] = out
    return out


# =============================================================================
# Counter-Ad CREATIVE — poora ready-to-post ad (copy + poster ke liye fields)
# =============================================================================
_CREATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "caption": {"type": "string"},
        "cta": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "visual_idea": {"type": "string"},
    },
    "required": ["headline", "body", "caption", "cta", "hashtags", "visual_idea"],
    "additionalProperties": False,
}

_CREATIVE_SYSTEM = (
    "You are AAP Punjab's ad creative director. AAP governs Punjab (CM Bhagwant "
    "Mann). Opponents are attacking AAP on a narrative. Create a punchy, "
    "ready-to-post COUNTER ad for AAP aimed at the given audience.\n"
    "Fields:\n"
    "- headline: short bold hook (<=8 words)\n"
    "- body: 2-3 line persuasive message (AAP ke kaam highlight karo: jobs, "
    "drugs action, schools, health, development)\n"
    "- caption: social media caption\n"
    "- cta: call to action (e.g. 'Aage badho, Punjab')\n"
    "- hashtags: 4-6 relevant hashtags\n"
    "- visual_idea: 1 line — poster mein kya dikhe\n"
    "Clean Hindi/Hinglish (Devanagari ok), Punjab-specific. No markdown."
)


def generate_creative(narrative, audience_str="", attack_text=""):
    """Ek narrative ke liye counter-ad creative banao. Returns dict or None."""
    if not AI_ENABLED or not _client:
        return None
    user = (
        f"Narrative jis par opponent attack kar raha: {narrative}\n"
        f"Target audience: {audience_str or 'Punjab voters'}\n"
        + (f"Sample attack ad: {attack_text[:400]}\n" if attack_text else "")
        + "\nAAP ke liye is narrative ka counter ad banao."
    )
    try:
        resp = _client.messages.create(
            model=config.STRATEGY_MODEL,
            max_tokens=1200,
            system=_CREATIVE_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema",
                                      "schema": _CREATIVE_SCHEMA}},
        )
        usage.record_resp(config.STRATEGY_MODEL, resp, "creative")
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        return json.loads(text)
    except Exception as e:
        log.warning("creative gen failed: %s", e)
        return None


# =============================================================================
# Aggregates — frontend ke "Stance Breakdown" + "Narrative Battlefield" ke liye
# =============================================================================
def build_ai_aggregates(ads):
    """Stance counts + narrative-wise battlefield breakdown."""
    stance_counts = {"against": 0, "support": 0, "neutral": 0, "unknown": 0}
    narr = {}  # narrative -> {against, support, neutral, count, summaries:set}

    for a in ads:
        s = a.get("stance", "unknown")
        stance_counts[s] = stance_counts.get(s, 0) + 1

        n = a.get("narrative", "Other")
        slot = narr.setdefault(n, {"narrative": n, "count": 0, "against": 0,
                                   "support": 0, "neutral": 0, "summaries": []})
        slot["count"] += 1
        if s in ("against", "support", "neutral"):
            slot[s] += 1
        summ = a.get("narrative_summary")
        if summ and len(slot["summaries"]) < 3 and summ not in slot["summaries"]:
            slot["summaries"].append(summ)

    battlefield = sorted(narr.values(), key=lambda x: x["count"], reverse=True)
    return {
        "ai_enabled": AI_ENABLED,
        "stance_counts": stance_counts,
        "battlefield": battlefield,
    }
