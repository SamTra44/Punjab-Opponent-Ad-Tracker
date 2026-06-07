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
    "AAP currently GOVERNS Punjab (Chief Minister Bhagwant Mann). You analyze "
    "political ads run by opponents and others. Ads are usually in Punjabi "
    "(Gurmukhi script), sometimes Hindi/English.\n\n"
    "For each ad decide:\n"
    "1) stance toward AAP (our client):\n"
    "   - 'against'  = ad attacks/criticizes AAP, the Mann government, or pushes "
    "an opponent against AAP.\n"
    "   - 'support'  = ad praises/promotes AAP, Bhagwant Mann, or AAP's work.\n"
    "   - 'neutral'  = general issue ad, news, or not clearly for/against AAP.\n"
    "2) narrative = the single best-fitting theme from the allowed list.\n"
    "3) narrative_summary = a punchy <=12 word English summary of the ad's "
    "core message/attack angle (e.g. 'Blames Mann govt for rising drug crisis').\n\n"
    "Be objective. Opposition ads attacking the government are 'against'."
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
                    "narrative": {"type": "string",
                                  "enum": config.NARRATIVE_CATEGORIES},
                    "narrative_summary": {"type": "string"},
                },
                "required": ["index", "stance", "narrative", "narrative_summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

_UNKNOWN = {"stance": "unknown", "narrative": "Other", "narrative_summary": ""}


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
            max_tokens=1500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
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
    return True


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
