"""
Internal-only data models.
These never leave the backend — they are the source of truth between pipeline stages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Stage 2 – Normalized Azure output
# ---------------------------------------------------------------------------

@dataclass
class NormalizedPhoneme:
    symbol: str          # ARPABET e.g. "R", "ER1"
    score: float         # 0–100 from Azure
    position: int        # 0-indexed within word
    is_final: bool       # last phoneme in the word
    error_type: str      # "None" | "Mispronunciation" | "Omission" | "Insertion"
    offset_ms: int = 0
    duration_ms: int = 0


@dataclass
class NormalizedSyllable:
    grapheme: str        # readable text e.g. "neer" — never ARPABET tokens
    score: float         # 0–100 from Azure
    stress_level: str | None = None  # "Primary" | "Secondary" | "None"
    offset_ms: int = 0
    duration_ms: int = 0


@dataclass
class NormalizedWord:
    word: str
    score: float
    error_type: str      # "None" | "Mispronunciation" | "Omission" | "Insertion"
    offset_ms: int
    duration_ms: int
    phonemes: list[NormalizedPhoneme] = field(default_factory=list)
    syllables: list[NormalizedSyllable] = field(default_factory=list)
    prosody_score: float | None = None
    syllable_accuracy_score: float | None = None


# ---------------------------------------------------------------------------
# Stage 4 – Deterministic diagnosis
# ---------------------------------------------------------------------------

@dataclass
class WordDiagnosis:
    word: str
    score: float
    severity: Literal["none", "minor", "moderate", "severe"]
    practice_priority: Literal["high", "medium", "low", "skip"]
    # weakest phoneme — ARPABET symbol kept internally, translated before reaching LLM/frontend
    weakest_phoneme_symbol: str | None
    weakest_phoneme_score: float | None
    weakest_phoneme_is_final: bool
    # weakest syllable — always the readable grapheme, never ARPABET token
    weakest_syllable_grapheme: str | None
    weakest_syllable_score: float | None
    error_type: str
    issue_categories: list[str]
    has_final_consonant_drop: bool   # final stop/fricative/r scored < 65
    has_vowel_reduction: bool        # unstressed vowel scored < 60
    has_stress_error: bool           # prosody_score < 72
    evidence_strength: Literal["strong", "moderate", "weak"]
    offset_ms: int = 0
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Stage 5 – Speaking patterns
# ---------------------------------------------------------------------------

@dataclass
class SpeakingPattern:
    pattern_id: str                 # e.g. "final_r_drop"
    label: str                      # "Weak final R"
    description: str                # learner-friendly, no ARPABET
    affected_words: list[str]       # words that triggered this pattern
    phoneme_symbol: str | None      # which ARPABET symbol (internal use)
    frequency: int                  # number of affected words
    severity: Literal["high", "medium", "low"]
    coaching_priority: int          # 1 = fix first


# ---------------------------------------------------------------------------
# Stage 3+4 – Full diagnostics bundle passed between stages
# ---------------------------------------------------------------------------

@dataclass
class ScoreSummary:
    overall: float
    accuracy: float
    fluency: float
    prosody: float
    completeness: float
    duration_seconds: float


@dataclass
class DiagnosticsBundle:
    scores: ScoreSummary
    transcript: str
    reference_text: str
    normalized_words: list[NormalizedWord]
    word_diagnoses: list[WordDiagnosis]
    speaking_patterns: list[SpeakingPattern]
    # pre-sorted list of words actually needing coaching (score < threshold)
    words_needing_coaching: list[WordDiagnosis]
    # top failing phoneme symbols with their occurrence count
    top_phoneme_failures: list[tuple[str, int]]
    has_prosody_issue: bool
    speech_rate_wpm: float | None
    evidence_quality: Literal["high", "medium", "low"]
    # gain estimate — qualitative, never fake numbers
    gain_estimate: str
