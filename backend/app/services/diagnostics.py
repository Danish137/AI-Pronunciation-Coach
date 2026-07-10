"""
Stage 3+4 – Evidence extraction and deterministic diagnosis.

No LLM. No coaching text.
Everything here is directly derived from Azure scores and phoneme data.
This is the single source of truth for: severity, priority, issue categories,
weakest sounds, weakest syllables, and evidence strength.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Literal

from ..schemas.internal import (
    DiagnosticsBundle,
    NormalizedWord,
    ScoreSummary,
    SpeakingPattern,
    WordDiagnosis,
)

logger = logging.getLogger("pronounceai.diagnostics")

# Words scoring at or above this threshold receive practice_priority="skip"
# and are never included in coaching output.
COACHING_THRESHOLD = 90.0

# Severity bands (only applied to words below COACHING_THRESHOLD)
SEVERE_THRESHOLD = 65.0
MODERATE_THRESHOLD = 80.0

# Phoneme quality thresholds
WEAK_PHONEME_THRESHOLD = 70.0
FINAL_DROP_THRESHOLD = 65.0
VOWEL_REDUCTION_THRESHOLD = 60.0

# Stress / prosody threshold
STRESS_ERROR_THRESHOLD = 72.0

# Common function words with no learner value to coach in isolation
# (they are coached indirectly through sentence-level prosody)
_SKIP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "so", "yet", "for", "nor",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "to", "of", "in", "on", "at", "by", "as", "up",
    "from", "with", "about", "into", "than", "then", "when", "where",
    "which", "who", "that", "this", "these", "those",
    "not", "no", "if", "all", "just", "also", "only",
    "hi", "oh", "ok", "okay",
})


def _is_skip_word(word: NormalizedWord) -> bool:
    """
    Returns True for words that should never receive coaching:
    - Single characters
    - Common function words (unless they have strong phoneme evidence)
    - Words with no phoneme data and borderline scores
    """
    clean = word.word.lower().strip(".,!?;:'\"")
    if len(clean) <= 1:
        return True
    if clean in _SKIP_WORDS and not word.phonemes:
        return True
    # Function words with phoneme data and severe error are coachable
    if clean in _SKIP_WORDS and word.error_type not in ("Omission", "Insertion"):
        return True
    return False


def build_diagnostics_bundle(
    scores: ScoreSummary,
    transcript: str,
    reference_text: str,
    normalized_words: list[NormalizedWord],
    speaking_patterns: list[SpeakingPattern],
) -> DiagnosticsBundle:
    diagnoses = [_diagnose_word(word) for word in normalized_words]

    # Deduplicate: if the same word appears multiple times, keep the worst-scoring instance
    seen: dict[str, WordDiagnosis] = {}
    for d in diagnoses:
        key = d.word.lower()
        if key not in seen or d.score < seen[key].score:
            seen[key] = d
    unique_diagnoses = list(seen.values())

    words_needing_coaching = sorted(
        [d for d in unique_diagnoses if d.practice_priority != "skip"],
        key=lambda d: (
            0 if d.practice_priority == "high" else 1 if d.practice_priority == "medium" else 2,
            d.score,
        ),
    )[:10]  # Cap at 10 — more than this overwhelms the learner

    top_phoneme_failures = _top_phoneme_failures(
        normalized_words, words_needing_coaching
    )
    has_prosody_issue = scores.prosody < 75 or any(
        d.has_stress_error for d in words_needing_coaching
    )
    speech_rate_wpm = _speech_rate_wpm(normalized_words, scores.duration_seconds)
    evidence_quality = _evidence_quality(normalized_words, words_needing_coaching)
    gain_estimate = _gain_estimate(words_needing_coaching, scores.overall)

    return DiagnosticsBundle(
        scores=scores,
        transcript=transcript,
        reference_text=reference_text,
        normalized_words=normalized_words,
        word_diagnoses=diagnoses,  # full list including skipped — for pattern detection
        speaking_patterns=speaking_patterns,
        words_needing_coaching=words_needing_coaching,
        top_phoneme_failures=top_phoneme_failures,
        has_prosody_issue=has_prosody_issue,
        speech_rate_wpm=speech_rate_wpm,
        evidence_quality=evidence_quality,
        gain_estimate=gain_estimate,
    )


# ---------------------------------------------------------------------------
# Per-word diagnosis  (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _diagnose_word(word: NormalizedWord) -> WordDiagnosis:
    """Derive all diagnostic properties from Azure evidence alone."""

    # Short function words and single characters with no phoneme evidence
    # are not coachable — skip them regardless of score.
    if _is_skip_word(word):
        return WordDiagnosis(
            word=word.word,
            score=word.score,
            severity="none",
            practice_priority="skip",
            weakest_phoneme_symbol=None,
            weakest_phoneme_score=None,
            weakest_phoneme_is_final=False,
            weakest_syllable_grapheme=None,
            weakest_syllable_score=None,
            error_type=word.error_type,
            issue_categories=[],
            has_final_consonant_drop=False,
            has_vowel_reduction=False,
            has_stress_error=False,
            evidence_strength="weak",
            offset_ms=word.offset_ms,
            duration_ms=word.duration_ms,
        )

    # Words at or above threshold never receive coaching
    if word.score >= COACHING_THRESHOLD and word.error_type in ("None", ""):
        return WordDiagnosis(
            word=word.word,
            score=word.score,
            severity="none",
            practice_priority="skip",
            weakest_phoneme_symbol=None,
            weakest_phoneme_score=None,
            weakest_phoneme_is_final=False,
            weakest_syllable_grapheme=None,
            weakest_syllable_score=None,
            error_type=word.error_type,
            issue_categories=[],
            has_final_consonant_drop=False,
            has_vowel_reduction=False,
            has_stress_error=False,
            evidence_strength="weak",
            offset_ms=word.offset_ms,
            duration_ms=word.duration_ms,
        )

    severity = _severity(word.score, word.error_type)
    practice_priority = _practice_priority(word.score, word.error_type)

    # Weakest phoneme
    scored_phonemes = [p for p in word.phonemes if p.score is not None]
    weakest_phoneme = min(scored_phonemes, key=lambda p: p.score, default=None)

    # Weakest syllable — expose grapheme only
    scored_syllables = [s for s in word.syllables if s.score is not None]
    weakest_syllable = min(scored_syllables, key=lambda s: s.score, default=None)

    has_final_drop = _has_final_consonant_drop(word.phonemes)
    has_vowel_red = _has_vowel_reduction(word.phonemes)
    has_stress_err = (
        word.prosody_score is not None and word.prosody_score < STRESS_ERROR_THRESHOLD
    )

    issue_categories = _issue_categories(
        word.error_type,
        word.phonemes,
        word.syllables,
        has_final_drop,
        has_vowel_red,
        has_stress_err,
    )
    evidence_strength = _evidence_strength(word, weakest_phoneme, weakest_syllable)

    return WordDiagnosis(
        word=word.word,
        score=word.score,
        severity=severity,
        practice_priority=practice_priority,
        weakest_phoneme_symbol=weakest_phoneme.symbol if weakest_phoneme else None,
        weakest_phoneme_score=weakest_phoneme.score if weakest_phoneme else None,
        weakest_phoneme_is_final=weakest_phoneme.is_final if weakest_phoneme else False,
        weakest_syllable_grapheme=weakest_syllable.grapheme if weakest_syllable else None,
        weakest_syllable_score=weakest_syllable.score if weakest_syllable else None,
        error_type=word.error_type,
        issue_categories=issue_categories,
        has_final_consonant_drop=has_final_drop,
        has_vowel_reduction=has_vowel_red,
        has_stress_error=has_stress_err,
        evidence_strength=evidence_strength,
        offset_ms=word.offset_ms,
        duration_ms=word.duration_ms,
    )


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def _severity(score: float, error_type: str) -> Literal["none", "minor", "moderate", "severe"]:
    if error_type == "Omission":
        return "severe"
    if score < SEVERE_THRESHOLD:
        return "severe"
    if score < MODERATE_THRESHOLD:
        return "moderate"
    return "minor"


def _practice_priority(score: float, error_type: str) -> Literal["high", "medium", "low", "skip"]:
    if score >= COACHING_THRESHOLD and error_type in ("None", ""):
        return "skip"
    if score < SEVERE_THRESHOLD or error_type == "Omission":
        return "high"
    if score < MODERATE_THRESHOLD:
        return "medium"
    return "low"


_R_SYMBOLS = {"R", "ER", "ER0", "ER1", "ER2"}
_FINAL_CONSONANT_SYMBOLS = {
    "P", "T", "K", "B", "D", "G",
    "F", "V", "S", "Z", "SH", "ZH", "TH", "DH",
    "M", "N", "NG", "L", "CH", "JH",
} | _R_SYMBOLS

_VOWEL_SYMBOLS = {
    "AA", "AA0", "AA1", "AA2",
    "AE", "AE0", "AE1", "AE2",
    "AH", "AH0", "AH1", "AH2",
    "AO", "AO0", "AO1", "AO2",
    "AW", "AW0", "AW1", "AW2",
    "AY", "AY0", "AY1", "AY2",
    "EH", "EH0", "EH1", "EH2",
    "ER", "ER0", "ER1", "ER2",
    "EY", "EY0", "EY1", "EY2",
    "IH", "IH0", "IH1", "IH2",
    "IY", "IY0", "IY1", "IY2",
    "OW", "OW0", "OW1", "OW2",
    "OY", "OY0", "OY1", "OY2",
    "UH", "UH0", "UH1", "UH2",
    "UW", "UW0", "UW1", "UW2",
}


def _has_final_consonant_drop(phonemes: list) -> bool:
    """True if the last phoneme is a consonant and scored below the drop threshold."""
    if not phonemes:
        return False
    last = phonemes[-1]
    base = last.symbol.rstrip("012")
    return base in _FINAL_CONSONANT_SYMBOLS and last.score < FINAL_DROP_THRESHOLD


def _has_vowel_reduction(phonemes: list) -> bool:
    """True if any vowel phoneme scored below the vowel reduction threshold."""
    for p in phonemes:
        base = p.symbol.rstrip("012")
        if base in _VOWEL_SYMBOLS and p.score < VOWEL_REDUCTION_THRESHOLD:
            return True
    return False


def _issue_categories(
    error_type: str,
    phonemes: list,
    syllables: list,
    has_final_drop: bool,
    has_vowel_red: bool,
    has_stress_err: bool,
) -> list[str]:
    categories: list[str] = []
    if error_type == "Omission":
        categories.append("omission")
    elif error_type == "Insertion":
        categories.append("insertion")
    elif error_type not in ("None", ""):
        categories.append(error_type.lower())

    if has_final_drop:
        categories.append("final consonant drop")
    if has_vowel_red:
        categories.append("vowel reduction")
    if has_stress_err:
        categories.append("stress error")

    weak_phonemes = [p for p in phonemes if p.score < WEAK_PHONEME_THRESHOLD]
    if weak_phonemes and "final consonant drop" not in categories:
        categories.append("phoneme clarity")

    weak_syllables = [s for s in syllables if s.score < 75.0]
    if weak_syllables:
        categories.append("syllable clarity")

    return list(dict.fromkeys(categories))  # dedup, preserve order


def _evidence_strength(word: NormalizedWord, weakest_phoneme, weakest_syllable) -> Literal["strong", "moderate", "weak"]:
    evidence_count = 0
    if word.error_type not in ("None", ""):
        evidence_count += 2
    if weakest_phoneme and weakest_phoneme.score < WEAK_PHONEME_THRESHOLD:
        evidence_count += 1
    if weakest_syllable and weakest_syllable.score < 75.0:
        evidence_count += 1
    if word.prosody_score is not None and word.prosody_score < STRESS_ERROR_THRESHOLD:
        evidence_count += 1
    weak_phoneme_count = sum(1 for p in word.phonemes if p.score < WEAK_PHONEME_THRESHOLD)
    if weak_phoneme_count >= 2:
        evidence_count += 1

    if evidence_count >= 3:
        return "strong"
    if evidence_count >= 1:
        return "moderate"
    return "weak"


def _top_phoneme_failures(
    words: list[NormalizedWord],
    diagnoses: list[WordDiagnosis],
) -> list[tuple[str, int]]:
    """Return the most frequently failing phoneme symbols, with occurrence counts."""
    counter: Counter = Counter()
    coaching_words = {d.word.lower() for d in diagnoses if d.practice_priority != "skip"}
    for word in words:
        if word.word.lower() not in coaching_words:
            continue
        for phoneme in word.phonemes:
            if phoneme.score < WEAK_PHONEME_THRESHOLD:
                base = phoneme.symbol.rstrip("012")
                counter[base] += 1
    return counter.most_common(6)


def _speech_rate_wpm(words: list[NormalizedWord], duration_seconds: float) -> float | None:
    if not words or duration_seconds <= 0:
        return None
    minutes = duration_seconds / 60.0
    return round(len(words) / minutes, 1)


def _evidence_quality(
    words: list[NormalizedWord],
    diagnoses: list[WordDiagnosis],
) -> Literal["high", "medium", "low"]:
    """How reliable is our evidence? Based on phoneme coverage."""
    words_with_phonemes = sum(1 for w in words if w.phonemes)
    total_words = len(words)
    if total_words == 0:
        return "low"
    coverage = words_with_phonemes / total_words
    if coverage >= 0.8 and total_words >= 10:
        return "high"
    if coverage >= 0.5 or total_words >= 5:
        return "medium"
    return "low"


def _gain_estimate(
    diagnoses: list[WordDiagnosis],
    overall_score: float,
) -> str:
    """
    Qualitative improvement estimate. Never a fake number.
    Based on severity distribution of words needing coaching.
    """
    if not diagnoses:
        return "Your pronunciation is already very strong."

    severe_count = sum(1 for d in diagnoses if d.severity == "severe")
    moderate_count = sum(1 for d in diagnoses if d.severity == "moderate")

    if severe_count >= 3:
        return (
            f"Fixing these {severe_count} words could produce a noticeable score improvement "
            "— they are each scoring significantly below your average."
        )
    if severe_count >= 1 and moderate_count >= 2:
        return (
            "Addressing the most flagged words should move your clarity score upward, "
            "since they are pulling the average down."
        )
    if moderate_count >= 3:
        return (
            "These are moderate refinements. Improving them will tighten your overall consistency."
        )
    if overall_score >= 88:
        return (
            "These are fine-tuning improvements on an already strong result. "
            "Small gains here add up over practice sessions."
        )
    return "Targeting these words first will have the highest impact on your next score."
