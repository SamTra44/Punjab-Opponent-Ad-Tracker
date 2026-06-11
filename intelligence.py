# intelligence.py
# -----------------------------------------------------------------------------
# "Claude ka dimaag" features:
#   1. audience_vulnerability(ads) -> opponents kis demographic/region ko sabse
#      zyada target kar rahe (computed, instant) + ek insight line.
#   2. generate_forecast(history, ads) -> Claude predict kare konsa narrative
#      chadega/peak karega aur kab counter karna chahiye.
# (Counter-ad creative classifier.py mein hai.)
# -----------------------------------------------------------------------------

import json
import logging

import config
import classifier  # reuse anthropic client + AI flag

log = logging.getLogger("intelligence")


# =============================================================================
# 1) AUDIENCE VULNERABILITY — computed (fast), anti-AAP ads ke demographics se
# =============================================================================
def audience_vulnerability(ads):
    """Opponents (anti-AAP ads) kis audience ko target kar rahe — aggregate."""
    threats = [a for a in ads if a.get("stance") == "against"]
    if not threats:
        return {"available": False}

    total_reach = 0.0
    male_w = 0.0
    female_w = 0.0
    age_count = {}
    region_count = {}
    narr_reach = {}

    for a in threats:
        reach = a.get("impr_mid", 0) or 1
        total_reach += reach
        aud = a.get("audience") or {}
        male_w += (aud.get("male_pct", 0) or 0) * reach
        female_w += (aud.get("female_pct", 0) or 0) * reach
        at = aud.get("age_top")
        if at:
            age_count[at] = age_count.get(at, 0) + reach
        for r in (a.get("regions") or []):
            region_count[r] = region_count.get(r, 0) + 1
        n = a.get("narrative", "Other")
        narr_reach[n] = narr_reach.get(n, 0) + reach

    male_pct = round(male_w / total_reach) if total_reach else 0
    female_pct = round(female_w / total_reach) if total_reach else 0
    top_age = max(age_count, key=age_count.get) if age_count else "—"
    top_regions = [r for r, _ in sorted(region_count.items(),
                                         key=lambda x: -x[1])[:3]]
    top_narr = max(narr_reach, key=narr_reach.get) if narr_reach else "—"

    gender_word = "mard" if male_pct >= female_pct else "auratein"
    gender_pct = max(male_pct, female_pct)

    insight = (
        f"Opponents apna sabse zyada zor <b>{gender_pct}% {gender_word}</b>, "
        f"umar <b>{top_age}</b> par laga rahe hain — mukhya narrative "
        f"<b>{top_narr}</b>. Yahi tumhara weak segment hai; isi audience ko "
        f"apne achievements (jobs, schools, health) se target karo."
    )

    return {
        "available": True,
        "threat_ads": len(threats),
        "male_pct": male_pct,
        "female_pct": female_pct,
        "top_age": top_age,
        "top_regions": top_regions,
        "top_narrative": top_narr,
        "insight": insight,
    }


# =============================================================================
# 2) NARRATIVE FORECAST — Claude se prediction (history trends ke aadhar par)
# =============================================================================
_FORECAST_SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string"},
        "forecasts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narrative": {"type": "string"},
                    "trend": {"type": "string",
                              "enum": ["rising", "stable", "falling"]},
                    "prediction": {"type": "string"},
                    "action": {"type": "string"},
                    "urgency": {"type": "string",
                                "enum": ["high", "medium", "low"]},
                },
                "required": ["narrative", "trend", "prediction", "action", "urgency"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall", "forecasts"],
    "additionalProperties": False,
}

_FORECAST_SYSTEM = (
    "You are AAP Punjab's intelligence forecaster. AAP governs Punjab (CM "
    "Bhagwant Mann). You are given the recent TREND of opponent ad narratives "
    "(counts over time) and the current snapshot. Predict which narratives are "
    "RISING and will likely peak soon, which are falling, and what AAP should "
    "do and WHEN (timing matters). Be specific to Punjab. At most 5 forecasts, "
    "rank by urgency. Write in simple Hindi/Hinglish (Devanagari ok). Tight, "
    "actionable. No preamble."
)


def _trend_text(history, current_narratives):
    """History snapshots se narrative trend ka compact text banao."""
    if not history:
        return "(koi history nahi — sirf current snapshot use karo)"
    recent = history[-12:]  # last ~12 snapshots
    # narrative -> list of counts over time
    series = {}
    for snap in recent:
        for narr, cnt in (snap.get("narratives", {}) or {}).items():
            series.setdefault(narr, []).append(cnt)
    lines = []
    for narr, counts in sorted(series.items(), key=lambda x: -sum(x[1]))[:8]:
        lines.append(f"- {narr}: {counts}")
    return "Narrative counts over time (purana -> naya):\n" + "\n".join(lines)


def generate_forecast(history, ads):
    """Narrative forecast generate karo. Returns dict."""
    if not classifier.AI_ENABLED or not classifier._client:
        return {"available": False, "error": "AI off — ANTHROPIC_API_KEY set karo"}

    current = {}
    for a in ads:
        if a.get("stance") == "against":
            n = a.get("narrative", "Other")
            current[n] = current.get(n, 0) + 1
    cur_txt = ", ".join(f"{k}:{v}" for k, v in
                        sorted(current.items(), key=lambda x: -x[1])[:8]) or "—"

    user = (
        _trend_text(history, current)
        + f"\n\nCurrent anti-AAP narrative counts: {cur_txt}\n\n"
        "In trends ke aadhar par forecast do: konsa narrative chadega, kab peak "
        "karega, AAP kab aur kya counter kare."
    )

    try:
        resp = classifier._client.messages.create(
            model=config.STRATEGY_MODEL,
            max_tokens=2500,
            system=_FORECAST_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema",
                                      "schema": _FORECAST_SCHEMA}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
        data["available"] = True
        return data
    except Exception as e:
        log.warning("forecast failed: %s", e)
        return {"available": False, "error": str(e)[:200]}
