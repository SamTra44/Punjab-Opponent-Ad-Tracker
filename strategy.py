# strategy.py
# -----------------------------------------------------------------------------
# AAP War Room Strategy Brief — Claude (Opus) se ek strategic analysis generate
# karta hai jo classified ads ke data par based hota hai:
#   1. Attack narratives  -> opponents AAP ke khilaf kya chala rahe hain
#   2. AAP counters        -> AAP ki apni ads sahi/weak/off-target hain ya nahi
#   3. Gaps                -> kaunse attacks ka koi jawaab nahi
#   4. Recommendations     -> counter-narrative kya hona chahiye (priority ke saath)
#
# Yeh ek ON-DEMAND single call hai (har refresh pe nahi), isliye Opus afford
# hota hai. Result cache hota hai; user "refresh" daba ke naya generate kar sakta.
# -----------------------------------------------------------------------------

import json
import logging

import config

log = logging.getLogger("strategy")

# classifier ka hi anthropic client + AI flag reuse karte hain (ek hi key).
import classifier

# Last generated brief ka cache.
_BRIEF_CACHE = {"generated": False, "brief": None, "generated_at": None}

_SYSTEM = (
    "You are the chief strategist for the Aam Aadmi Party (AAP) Punjab digital "
    "war room. AAP GOVERNS Punjab (CM Bhagwant Mann). You are given a summary of "
    "currently-running political ads in Punjab, grouped by narrative and by "
    "stance (attacks AGAINST AAP, vs AAP's OWN pro-AAP ads).\n\n"
    "Produce a sharp, honest, actionable strategy brief for the AAP team:\n"
    "- Identify the strongest attack narratives against AAP and what opponents "
    "are claiming.\n"
    "- Evaluate AAP's CURRENT counter-ads: are they strong, weak, off-target, "
    "or missing for each major attack? Be brutally honest — don't flatter.\n"
    "- Flag gaps: attacks with no AAP response.\n"
    "- Recommend specific counter-narratives AAP SHOULD run, with the actual "
    "message angle and why it works, prioritized.\n\n"
    "Write all text in simple Hindi/Hinglish (Devanagari is fine) so the Punjab "
    "team can use it directly. Be concrete and specific to Punjab issues "
    "(drugs, jobs, farmers, governance, development). Avoid generic advice.\n\n"
    "Keep it focused: at most 5 attack_narratives, 5 aap_counters, 5 gaps, "
    "and 6 recommendations. Keep each text field tight (1-2 sentences)."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string"},
        "attack_narratives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narrative": {"type": "string"},
                    "claim": {"type": "string"},
                    "intensity": {"type": "string",
                                  "enum": ["high", "medium", "low"]},
                },
                "required": ["narrative", "claim", "intensity"],
                "additionalProperties": False,
            },
        },
        "aap_counters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narrative": {"type": "string"},
                    "current_message": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["strong", "weak", "off-target", "missing"]},
                    "note": {"type": "string"},
                },
                "required": ["narrative", "current_message", "verdict", "note"],
                "additionalProperties": False,
            },
        },
        "gaps": {"type": "array", "items": {"type": "string"}},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "counter_message": {"type": "string"},
                    "rationale": {"type": "string"},
                    "priority": {"type": "string",
                                 "enum": ["high", "medium", "low"]},
                },
                "required": ["title", "counter_message", "rationale", "priority"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall", "attack_narratives", "aap_counters", "gaps",
                 "recommendations"],
    "additionalProperties": False,
}


def _group_by_narrative(group):
    """Ads ko narrative se group karke summaries/pages collect karo."""
    by = {}
    for a in group:
        n = a.get("narrative", "Other")
        slot = by.setdefault(n, {"count": 0, "summaries": [], "pages": set()})
        slot["count"] += 1
        s = a.get("narrative_summary")
        if s and s not in slot["summaries"]:
            slot["summaries"].append(s)
        if a.get("page"):
            slot["pages"].add(a["page"])
    return by


def _build_data_text(ads):
    """Claude ko bhejne ke liye compact data summary banao."""
    against = [a for a in ads if a.get("stance") == "against"]
    support = [a for a in ads if a.get("stance") == "support"]

    def fmt(by):
        lines = []
        for n, d in sorted(by.items(), key=lambda x: -x[1]["count"]):
            sums = "; ".join(d["summaries"][:5])
            pages = ", ".join(list(d["pages"])[:4])
            lines.append(f"- {n} ({d['count']} ads) | pages: {pages} | "
                         f"messages: {sums}")
        return "\n".join(lines) or "(none)"

    txt = (
        f"=== ATTACKS AGAINST AAP ({len(against)} ads) ===\n"
        + fmt(_group_by_narrative(against))
        + f"\n\n=== AAP's OWN PRO-AAP ADS ({len(support)} ads) ===\n"
        + fmt(_group_by_narrative(support))
    )
    return txt, len(against), len(support)


def generate_brief(ads):
    """Strategy brief generate karo. Returns dict; cache update karta hai."""
    if not classifier.AI_ENABLED or not classifier._client:
        return {"generated": False, "error": "AI off — ANTHROPIC_API_KEY set karo"}

    data_text, n_against, n_support = _build_data_text(ads)
    user_msg = (
        "Yahan Punjab mein abhi chal rahi ads ka data hai (narrative + stance "
        "wise). Iska strategic analysis aur counter-narrative recommendations do:\n\n"
        + data_text
    )

    try:
        resp = classifier._client.messages.create(
            model=config.STRATEGY_MODEL,
            max_tokens=8000,  # Devanagari token-heavy hai; JSON pura aaye
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        if resp.stop_reason == "max_tokens":
            log.warning("strategy brief hit max_tokens — output truncated")
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        brief = json.loads(text)
    except Exception as e:
        log.warning("strategy brief failed: %s", e)
        return {"generated": False, "error": str(e)[:200]}

    brief["_stats"] = {"against": n_against, "support": n_support}
    _BRIEF_CACHE.update({"generated": True, "brief": brief})
    return {"generated": True, "brief": brief}


def get_cached():
    """Last generated brief (agar koi ho)."""
    return dict(_BRIEF_CACHE)
