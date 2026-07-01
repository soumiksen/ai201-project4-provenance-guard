"""
Detection Signal 2: stylometric heuristics.

Two concrete, computable metrics per planning.md:

  1. Sentence-length variance (coefficient of variation of sentence lengths,
     in words) - AI-generated text tends toward uniform sentence length;
     human writing tends to be "bursty" (mixing short and long sentences).

  2. Type-token ratio (TTR = unique words / total words) - a lexical
     diversity measure. AI-generated text tends to repeat vocabulary more
     than human writing does over the same length.

Both metrics are normalized to [0, 1] where 1.0 = AI-like and 0.0 =
human-like, then averaged into a single `stylometric_score`, mirroring how
Signal 1 is normalized. This keeps the two signals on the same scale before
they're combined in confidence scoring (see combine.py).
"""

import re
import statistics

# Empirical normalization bounds. These are rough, hand-picked ranges (not
# derived from a calibration corpus) - documented here so they're easy to
# retune once real test data is available, per planning.md Section 1.
CV_MIN = 0.15    # very uniform sentence lengths -> fully AI-like on this metric
CV_MAX = 0.90    # highly bursty sentence lengths -> fully human-like on this metric

TTR_MIN = 0.30   # highly repetitive vocabulary -> fully AI-like on this metric
TTR_MAX = 0.90   # highly diverse vocabulary -> fully human-like on this metric


def _sentences(text: str):
    # Simple sentence splitter: splits on ., !, ? followed by whitespace.
    # Not linguistically perfect, but sufficient for this heuristic.
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in raw if s.strip()]


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def sentence_length_uniformity(text: str) -> dict:
    """
    Returns the coefficient of variation of sentence lengths (in words),
    plus a normalized 0-1 score where 1.0 = uniform/AI-like.
    """
    sents = _sentences(text)
    lengths = [len(re.findall(r"[a-zA-Z']+", s)) for s in sents]
    lengths = [l for l in lengths if l > 0]

    if len(lengths) < 2:
        # Not enough sentences to measure variance meaningfully.
        return {"cv": None, "score": 0.5, "note": "insufficient sentences (<2)"}

    mean_len = statistics.mean(lengths)
    stdev_len = statistics.stdev(lengths)
    cv = stdev_len / mean_len if mean_len > 0 else 0.0

    normalized_cv = _clamp((cv - CV_MIN) / (CV_MAX - CV_MIN))
    score = 1 - normalized_cv  # low CV (uniform) -> high score (AI-like)

    return {"cv": round(cv, 3), "score": round(score, 3), "note": None}


def type_token_ratio(text: str) -> dict:
    """
    Returns the type-token ratio (unique words / total words), plus a
    normalized 0-1 score where 1.0 = repetitive/AI-like.
    """
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return {"ttr": None, "score": 0.5, "note": "empty text"}

    ttr = len(set(words)) / len(words)
    normalized_ttr = _clamp((ttr - TTR_MIN) / (TTR_MAX - TTR_MIN))
    score = 1 - normalized_ttr  # low TTR (repetitive) -> high score (AI-like)

    return {"ttr": round(ttr, 3), "score": round(score, 3), "note": None}


def signal_2_stylometric(text: str) -> dict:
    """
    Returns {"stylometric_score": float, "sentence_length_cv": float|None,
    "type_token_ratio": float|None}.

    Sub-metrics are NOT weighted equally. Debugging against the milestone's
    test set showed raw type-token ratio barely varies across short
    (~40-70 word) paragraphs regardless of AI/human origin (it clustered at
    0.86-0.90 for every sample tested, AI and human alike) - a known
    property of TTR at short text lengths, since repeated words become
    statistically unlikely once you're only using ~50-70 words no matter who
    wrote it. Sentence-length uniformity separated the same samples cleanly
    and tracked expectations, so it carries more of the combined score.
    """
    uniformity = sentence_length_uniformity(text)
    diversity = type_token_ratio(text)

    UNIFORMITY_WEIGHT = 0.7
    TTR_WEIGHT = 0.3

    stylometric_score = round(
        UNIFORMITY_WEIGHT * uniformity["score"] + TTR_WEIGHT * diversity["score"], 3
    )

    return {
        "stylometric_score": stylometric_score,
        "sentence_length_cv": uniformity["cv"],
        "type_token_ratio": diversity["ttr"],
    }
