"""
Confidence scoring: combines Signal 1 (LLM-based assessment) and Signal 2
(stylometric heuristics) into a single confidence score and attribution
label, per planning.md Sections 1 and 2.
"""

# Weights from planning.md Section 1. Named constants, not magic numbers -
# tune here if real test data suggests one signal should carry more weight.
SIGNAL_1_WEIGHT = 0.5
SIGNAL_2_WEIGHT = 0.5

# Thresholds from planning.md Section 2 (Uncertainty Representation).
LIKELY_HUMAN_MAX = 0.34
UNCERTAIN_MAX = 0.65


def label_from_score(score: float) -> str:
    """Maps a 0-1 confidence score to one of three attribution bands."""
    if score <= LIKELY_HUMAN_MAX:
        return "likely_human"
    if score <= UNCERTAIN_MAX:
        return "uncertain"
    return "likely_ai"


def combine_signals(signal_1_score: float, signal_2_score: float) -> dict:
    """
    Combines two normalized (0-1) signal scores into a single confidence
    score and attribution label via a weighted average.
    """
    confidence = round(
        (SIGNAL_1_WEIGHT * signal_1_score) + (SIGNAL_2_WEIGHT * signal_2_score), 3
    )
    return {
        "confidence": confidence,
        "attribution": label_from_score(confidence),
    }
