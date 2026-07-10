"""
Stage 5 – Speaking pattern detection.

Detects cross-word habits from the full NormalizedWord list.
Each detector requires >= 2 words to fire — single-word anomalies are not patterns.
Returns a list of SpeakingPattern sorted by coaching_priority.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..schemas.internal import NormalizedWord, SpeakingPattern, WordDiagnosis
from .diagnostics import (
    COACHING_THRESHOLD,
    FINAL_DROP_THRESHOLD,
    STRESS_ERROR_THRESHOLD,
    WEAK_PHONEME_THRESHOLD,
    _FINAL_CONSONANT_SYMBOLS,
    _R_SYMBOLS,
    _VOWEL_SYMBOLS,
)

logger = logging.getLogger("pronounceai.patterns")

MIN_PATTERN_FREQUENCY = 2


# ---------------------------------------------------------------------------
# Base detector
# ---------------------------------------------------------------------------

class BasePatternDetector(ABC):
    @abstractmethod
    def detect(
        self,
        words: list[NormalizedWord],
        diagnoses: list[WordDiagnosis],
    ) -> SpeakingPattern | None:
        ...

    def _coaching_pairs(
        self,
        words: list[NormalizedWord],
        diagnoses: list[WordDiagnosis],
    ) -> list[tuple[NormalizedWord, WordDiagnosis]]:
        """Return only word/diagnosis pairs that need coaching."""
        diag_map = {d.word.lower(): d for d in diagnoses}
        return [
            (w, diag_map[w.word.lower()])
            for w in words
            if w.word.lower() in diag_map
            and diag_map[w.word.lower()].practice_priority != "skip"
        ]


# ---------------------------------------------------------------------------
# Detector: Final R / ER drop
# ---------------------------------------------------------------------------

class FinalRDropDetector(BasePatternDetector):
    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        affected: list[str] = []
        for word, _diag in self._coaching_pairs(words, diagnoses):
            if not word.phonemes:
                continue
            last = word.phonemes[-1]
            base = last.symbol.rstrip("012")
            if base in _R_SYMBOLS and last.score < FINAL_DROP_THRESHOLD:
                affected.append(word.word)

        if len(affected) < MIN_PATTERN_FREQUENCY:
            return None

        return SpeakingPattern(
            pattern_id="final_r_drop",
            label="Weak final R",
            description=(
                f"You consistently weaken the R sound at the end of words "
                f"({', '.join(affected[:4])}). "
                "In American English, the R-colored vowel must stay audible right through "
                "to the end of the word."
            ),
            affected_words=affected,
            phoneme_symbol="ER",
            frequency=len(affected),
            severity="high" if len(affected) >= 3 else "medium",
            coaching_priority=1,
        )


# ---------------------------------------------------------------------------
# Detector: Final consonant drop (non-R)
# ---------------------------------------------------------------------------

class FinalConsonantDropDetector(BasePatternDetector):
    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        affected: list[str] = []
        for word, _diag in self._coaching_pairs(words, diagnoses):
            if not word.phonemes:
                continue
            last = word.phonemes[-1]
            base = last.symbol.rstrip("012")
            if (
                base in (_FINAL_CONSONANT_SYMBOLS - _R_SYMBOLS)
                and last.score < FINAL_DROP_THRESHOLD
            ):
                affected.append(word.word)

        if len(affected) < MIN_PATTERN_FREQUENCY:
            return None

        return SpeakingPattern(
            pattern_id="final_consonant_drop",
            label="Dropped final consonants",
            description=(
                f"You are dropping or softening the final consonant sounds in several words "
                f"({', '.join(affected[:4])}). "
                "Listeners rely on final consonants to distinguish words — "
                "keep each word's last sound fully audible."
            ),
            affected_words=affected,
            phoneme_symbol=None,
            frequency=len(affected),
            severity="high" if len(affected) >= 4 else "medium",
            coaching_priority=2,
        )


# ---------------------------------------------------------------------------
# Detector: Vowel reduction
# ---------------------------------------------------------------------------

class VowelReductionDetector(BasePatternDetector):
    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        affected: list[str] = []
        for word, _diag in self._coaching_pairs(words, diagnoses):
            for phoneme in word.phonemes:
                base = phoneme.symbol.rstrip("012")
                if base in _VOWEL_SYMBOLS and phoneme.score < 60.0:
                    affected.append(word.word)
                    break  # one vowel problem per word is enough

        if len(affected) < MIN_PATTERN_FREQUENCY:
            return None

        return SpeakingPattern(
            pattern_id="vowel_reduction",
            label="Reduced vowels",
            description=(
                f"Vowel sounds are collapsing in several words ({', '.join(affected[:4])}). "
                "This usually happens under time pressure — the vowel rushes toward a neutral "
                "'uh' sound instead of keeping its full shape."
            ),
            affected_words=affected,
            phoneme_symbol=None,
            frequency=len(affected),
            severity="medium",
            coaching_priority=3,
        )


# ---------------------------------------------------------------------------
# Detector: Consistent stress errors
# ---------------------------------------------------------------------------

class StressErrorDetector(BasePatternDetector):
    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        affected: list[str] = []
        for word, diag in self._coaching_pairs(words, diagnoses):
            if diag.has_stress_error:
                affected.append(word.word)

        if len(affected) < MIN_PATTERN_FREQUENCY:
            return None

        return SpeakingPattern(
            pattern_id="stress_errors",
            label="Inconsistent word stress",
            description=(
                f"Stress is landing on the wrong syllable in several words "
                f"({', '.join(affected[:4])}). "
                "Misplaced stress is one of the most common causes of "
                "reduced intelligibility, even when individual sounds are correct."
            ),
            affected_words=affected,
            phoneme_symbol=None,
            frequency=len(affected),
            severity="high" if len(affected) >= 3 else "medium",
            coaching_priority=2,
        )


# ---------------------------------------------------------------------------
# Detector: Technical vocabulary instability
# ---------------------------------------------------------------------------

_TECHNICAL_SUFFIXES = (
    "tion", "sion", "ity", "ology", "ical", "ance", "ence",
    "ment", "ture", "ware", "work", "base", "ism",
)
_MIN_TECHNICAL_WORD_LENGTH = 8


class TechnicalVocabDetector(BasePatternDetector):
    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        affected: list[str] = []
        for word, diag in self._coaching_pairs(words, diagnoses):
            clean = word.word.lower().strip(".,!?;:")
            if (
                len(clean) >= _MIN_TECHNICAL_WORD_LENGTH
                and (
                    any(clean.endswith(s) for s in _TECHNICAL_SUFFIXES)
                    or len(word.syllables) >= 4
                )
                and diag.severity in ("moderate", "severe")
            ):
                affected.append(word.word)

        if len(affected) < MIN_PATTERN_FREQUENCY:
            return None

        return SpeakingPattern(
            pattern_id="technical_vocab_instability",
            label="Technical vocabulary instability",
            description=(
                f"Long technical words are scoring lower than shorter words "
                f"({', '.join(affected[:4])}). "
                "Multi-syllable professional vocabulary often needs specific stress "
                "and vowel practice before it becomes automatic."
            ),
            affected_words=affected,
            phoneme_symbol=None,
            frequency=len(affected),
            severity="medium",
            coaching_priority=4,
        )


# ---------------------------------------------------------------------------
# Detector: Monotone / flat prosody
# ---------------------------------------------------------------------------

class MonotoneDetector(BasePatternDetector):
    """Fires when recording-level prosody is low and multiple words show stress errors."""

    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        stress_error_words = [
            d.word for d in diagnoses
            if d.has_stress_error and d.practice_priority != "skip"
        ]

        # Also check for very low prosody across most words that have a prosody score
        words_with_prosody = [w for w in words if w.prosody_score is not None]
        low_prosody_words = [
            w.word for w in words_with_prosody if w.prosody_score < 70.0
        ]

        # Need evidence from both stress errors and low prosody scores
        affected = list(dict.fromkeys(stress_error_words + low_prosody_words))[:6]

        if len(affected) < 3:  # higher bar for this pattern
            return None

        return SpeakingPattern(
            pattern_id="flat_prosody",
            label="Flat intonation",
            description=(
                "Sentence rhythm and stress are relatively flat across the recording. "
                "Natural English speech rises and falls — stressed syllables are longer "
                "and slightly louder, while unstressed ones compress."
            ),
            affected_words=affected,
            phoneme_symbol=None,
            frequency=len(affected),
            severity="medium",
            coaching_priority=5,
        )


# ---------------------------------------------------------------------------
# Detector: R / L confusion
# ---------------------------------------------------------------------------

_R_PHONEMES = {"R", "ER", "ER0", "ER1", "ER2"}
_L_PHONEMES = {"L"}


class RLConfusionDetector(BasePatternDetector):
    """
    R/L confusion: fires if both R and L phonemes are scoring poorly
    across multiple words (common for some L1 backgrounds).
    """

    def detect(self, words, diagnoses) -> SpeakingPattern | None:
        r_failures: list[str] = []
        l_failures: list[str] = []

        for word, _diag in self._coaching_pairs(words, diagnoses):
            for p in word.phonemes:
                base = p.symbol.rstrip("012")
                if base in _R_PHONEMES and p.score < WEAK_PHONEME_THRESHOLD:
                    r_failures.append(word.word)
                    break
            for p in word.phonemes:
                base = p.symbol.rstrip("012")
                if base in _L_PHONEMES and p.score < WEAK_PHONEME_THRESHOLD:
                    l_failures.append(word.word)
                    break

        if len(r_failures) < 1 or len(l_failures) < 1:
            return None
        if len(r_failures) + len(l_failures) < MIN_PATTERN_FREQUENCY + 1:
            return None

        all_affected = list(dict.fromkeys(r_failures + l_failures))
        return SpeakingPattern(
            pattern_id="rl_confusion",
            label="R and L distinction",
            description=(
                f"Both R and L sounds are scoring below average "
                f"({', '.join(all_affected[:4])}). "
                "These two sounds require different tongue positions — "
                "R uses a bunched or retroflex tongue, while L touches the ridge just behind the upper teeth."
            ),
            affected_words=all_affected,
            phoneme_symbol=None,
            frequency=len(all_affected),
            severity="medium",
            coaching_priority=3,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DETECTORS: list[BasePatternDetector] = [
    FinalRDropDetector(),
    FinalConsonantDropDetector(),
    StressErrorDetector(),
    VowelReductionDetector(),
    RLConfusionDetector(),
    TechnicalVocabDetector(),
    MonotoneDetector(),
]


def detect_speaking_patterns(
    words: list[NormalizedWord],
    diagnoses: list[WordDiagnosis],
) -> list[SpeakingPattern]:
    """
    Run all pattern detectors and return patterns sorted by coaching_priority.
    Each pattern requires >= 2 affected words to be returned.
    """
    patterns: list[SpeakingPattern] = []
    for detector in _DETECTORS:
        try:
            pattern = detector.detect(words, diagnoses)
            if pattern is not None:
                patterns.append(pattern)
        except Exception as exc:
            logger.warning("Pattern detector %s failed: %s", type(detector).__name__, exc)

    # Deduplicate: if final_r_drop already covers words, don't also show final_consonant_drop
    # for the same words (only if R drop fires with high severity)
    r_drop = next((p for p in patterns if p.pattern_id == "final_r_drop"), None)
    final_drop = next((p for p in patterns if p.pattern_id == "final_consonant_drop"), None)
    if r_drop and final_drop and r_drop.severity == "high":
        # R drop is more specific — remove the generic final consonant drop if it's mostly the same words
        overlap = len(set(r_drop.affected_words) & set(final_drop.affected_words))
        if overlap >= len(final_drop.affected_words) * 0.7:
            patterns = [p for p in patterns if p.pattern_id != "final_consonant_drop"]

    return sorted(patterns, key=lambda p: p.coaching_priority)
