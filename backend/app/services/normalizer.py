"""
Stage 2 – Normalizer
Converts raw Azure JSON into clean NormalizedWord objects.

Rules:
- Never produces coaching text
- Never applies thresholds
- Translates ARPABET syllable tokens to graphemes using Azure's own Grapheme field
- Converts Azure 100ns ticks to milliseconds
"""
from __future__ import annotations

import logging
from typing import Any

from ..schemas.internal import NormalizedPhoneme, NormalizedSyllable, NormalizedWord

logger = logging.getLogger("pronounceai.normalizer")

# Phonemes that count as final consonants for drop-detection
FINAL_CONSONANT_SYMBOLS = {
    "P", "T", "K", "B", "D", "G",
    "F", "V", "S", "Z", "SH", "ZH", "TH", "DH",
    "M", "N", "NG",
    "L", "R", "ER", "ER0", "ER1", "ER2",
    "CH", "JH",
}


def normalize_azure_words(raw_words: list[dict[str, Any]]) -> list[NormalizedWord]:
    """
    Convert the Words array from an Azure NBest result into NormalizedWord objects.
    Each word exposes clean phoneme and syllable data with no coaching logic.
    """
    result: list[NormalizedWord] = []
    for raw_word in raw_words:
        word_text = (raw_word.get("Word") or "").strip()
        if not word_text:
            continue

        pa = raw_word.get("PronunciationAssessment", {})
        score = _float(pa.get("AccuracyScore"), default=0.0)
        error_type = pa.get("ErrorType") or "None"
        offset_ms = _ticks_to_ms(raw_word.get("Offset", 0))
        duration_ms = _ticks_to_ms(raw_word.get("Duration", 0))
        prosody_score = _float(pa.get("ProsodyScore"))
        syllable_accuracy_score = _float(pa.get("SyllableScore"))

        raw_phonemes = raw_word.get("Phonemes", [])
        raw_syllables = raw_word.get("Syllables", [])

        phonemes = _normalize_phonemes(raw_phonemes)
        syllables = _normalize_syllables(raw_syllables)

        result.append(NormalizedWord(
            word=word_text,
            score=score,
            error_type=error_type,
            offset_ms=offset_ms,
            duration_ms=duration_ms,
            phonemes=phonemes,
            syllables=syllables,
            prosody_score=prosody_score,
            syllable_accuracy_score=syllable_accuracy_score,
        ))

    return result


def normalize_azure_segments(raw_segments: list[dict[str, Any]]) -> list[NormalizedWord]:
    """
    Flatten multiple Azure segments (continuous recognition chunks) into a
    single ordered list of NormalizedWord objects.
    """
    all_words: list[NormalizedWord] = []
    for segment in raw_segments:
        nbest = segment.get("NBest", [{}])[0]
        words_in_segment = normalize_azure_words(nbest.get("Words", []))
        all_words.extend(words_in_segment)
    return all_words


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalize_phonemes(raw_phonemes: list[dict[str, Any]]) -> list[NormalizedPhoneme]:
    items: list[NormalizedPhoneme] = []
    total = len(raw_phonemes)
    for idx, raw in enumerate(raw_phonemes):
        pa = raw.get("PronunciationAssessment", {})
        symbol = (raw.get("Phoneme") or "").upper().strip()
        if not symbol:
            continue
        items.append(NormalizedPhoneme(
            symbol=symbol,
            score=_float(pa.get("AccuracyScore"), default=0.0),
            position=idx,
            is_final=(idx == total - 1),
            error_type=pa.get("ErrorType") or "None",
            offset_ms=_ticks_to_ms(raw.get("Offset", 0)),
            duration_ms=_ticks_to_ms(raw.get("Duration", 0)),
        ))
    return items


def _normalize_syllables(raw_syllables: list[dict[str, Any]]) -> list[NormalizedSyllable]:
    items: list[NormalizedSyllable] = []
    for raw in raw_syllables:
        pa = raw.get("PronunciationAssessment", {})
        # Always prefer the human-readable Grapheme over the ARPABET Syllable token
        grapheme = (
            raw.get("Grapheme")
            or raw.get("SyllableText")
            or raw.get("Syllable")
            or ""
        ).strip()
        if not grapheme:
            continue
        items.append(NormalizedSyllable(
            grapheme=grapheme,
            score=_float(pa.get("AccuracyScore"), default=0.0),
            stress_level=pa.get("Stress") or None,
            offset_ms=_ticks_to_ms(raw.get("Offset", 0)),
            duration_ms=_ticks_to_ms(raw.get("Duration", 0)),
        ))
    return items


def _ticks_to_ms(ticks: Any) -> int:
    """Azure uses 100-nanosecond ticks. Convert to milliseconds."""
    try:
        return int(int(ticks) / 10_000)
    except (TypeError, ValueError):
        return 0


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
