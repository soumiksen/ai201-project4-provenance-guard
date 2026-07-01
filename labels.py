"""
Transparency label generation.

Maps a confidence score to one of three label variants, using the exact
text designed in planning.md Section 3. The label word is never returned
without its numeric confidence and explanatory subtext - a bare "Likely AI"
overstates certainty; the full package communicates it honestly.
"""

from confidence import LIKELY_HUMAN_MAX, UNCERTAIN_MAX, label_from_score


_LABEL_TEXT = {
    "likely_ai": {
        "headline": "⚠️ Likely AI-Generated (confidence: {score})",
        "subtext": (
            "This text shows patterns consistent with AI generation: "
            "predictable word choices and uniform sentence structure."
        ),
    },
    "uncertain": {
        "headline": "❓ Uncertain (confidence: {score})",
        "subtext": (
            "Signals are mixed. This text has some characteristics of both "
            "AI-generated and human-written content."
        ),
    },
    "likely_human": {
        "headline": "✅ Likely Human-Written (confidence: {score})",
        "subtext": (
            "This text shows patterns typical of human writing: varied "
            "sentence structure and less predictable word choices."
        ),
    },
}


def generate_label(confidence: float) -> dict:
    """
    Returns {"code": str, "headline": str, "subtext": str} for a given
    confidence score. `code` is the short attribution key used elsewhere
    (audit log, thresholds); `headline`/`subtext` are the exact user-facing
    text from planning.md Section 3.
    """
    code = label_from_score(confidence)
    variant = _LABEL_TEXT[code]
    return {
        "code": code,
        "headline": variant["headline"].format(score=confidence),
        "subtext": variant["subtext"],
    }
