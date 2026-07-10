"""
API-facing schemas — the only models that leave the backend.
Every field here must have a distinct, user-visible purpose.
Internal diagnostics (phoneme arrays, ARPABET tokens, raw breakdowns) live in internal.py.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Word-level coaching  (only words scoring < 90)
# ---------------------------------------------------------------------------

class WordCoaching(BaseModel):
    word: str
    score: float = Field(ge=0, le=100)
    severity: Literal["minor", "moderate", "severe"]
    # Three distinct fields — each answers a different question
    what_happened: str      # "The final R dropped — 'engineer' sounded like 'enginee'"
    why: str                # "The R-colored vowel (ER) scored 34/100 at the end of the word"
    how_to_fix: str         # "Curl your tongue back slightly as you finish the word"
    # Progressive practice: isolated → phrase → full sentence
    practice_drills: list[str] = Field(min_length=1)
    # Readable hint, no ARPABET e.g. "EN-jih-NEER"
    native_audio_hint: str | None = None
    start_ms: int = Field(ge=0, default=0)
    end_ms: int = Field(ge=0, default=0)


# ---------------------------------------------------------------------------
# Pattern-level insight  (cross-word speaking habits)
# ---------------------------------------------------------------------------

class PatternInsight(BaseModel):
    label: str                      # "Weak final R"
    affected_words: list[str]       # ["engineer", "career", "worker"]
    explanation: str                # what this means for intelligibility
    priority: int = Field(ge=1)     # 1 = most important to fix first


# ---------------------------------------------------------------------------
# Recording-level summary
# ---------------------------------------------------------------------------

class RecordingSummary(BaseModel):
    headline: str                   # "90/100 — Strong pronunciation"
    level_label: str                # "Strong pronunciation"
    overall_habit: str              # the single most useful coach observation
    strengths: list[str]            # 1–2 items, evidence-based
    patterns: list[PatternInsight]  # cross-word habits (empty = no recurring issues)
    primary_action: str             # "Fix these 3 words and your clarity improves noticeably"
    gain_estimate: str              # qualitative — never fake numbers


# ---------------------------------------------------------------------------
# Practice session
# ---------------------------------------------------------------------------

class PracticeDrill(BaseModel):
    theme: str                  # "Final R clarity" or word name if isolated
    words: list[str]            # words in this drill group
    progression: list[str]      # ["engineer", "AI engineer", "I work as an AI engineer"]


class PracticeSession(BaseModel):
    focus: str                  # "Today: Final consonant clarity"
    drills: list[PracticeDrill]
    context_sentences: list[str]   # sentences pulled from the actual transcript


# ---------------------------------------------------------------------------
# Score metrics (kept for historical display)
# ---------------------------------------------------------------------------

class ScoreMetric(BaseModel):
    key: Literal["overall", "accuracy", "prosody", "fluency", "completeness"]
    label: str
    score: float = Field(ge=0, le=100)
    band: str           # "Excellent" | "Strong" | "Developing" | "Needs work"
    explanation: str    # one sentence, evidence-based


# ---------------------------------------------------------------------------
# Main response
# ---------------------------------------------------------------------------

class AssessmentResponse(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    accuracy_score: float = Field(ge=0, le=100)
    fluency_score: float = Field(ge=0, le=100)
    prosody_score: float = Field(ge=0, le=100)
    completeness_score: float = Field(ge=0, le=100)
    duration_seconds: float = Field(ge=0)
    transcript: str
    provider_mode: Literal["mock", "azure"] = "mock"
    summary: RecordingSummary
    metrics: list[ScoreMetric]
    word_coaching: list[WordCoaching]   # only flagged words, never the full list
    practice: PracticeSession


# ---------------------------------------------------------------------------
# History / persistence
# ---------------------------------------------------------------------------

class HistoryItem(AssessmentResponse):
    id: int
    source_type: Literal["upload", "recording"]
    reference_text: str
    created_at: datetime


class DeleteResponse(BaseModel):
    deleted: int


class RawAzurePayloadResponse(BaseModel):
    attempt_id: int
    provider_mode: Literal["mock", "azure"]
    raw_azure_json: dict | list | None


# ---------------------------------------------------------------------------
# Kept for internal storage / diagnostics endpoint
# (not included in AssessmentResponse — stored separately in DB)
# ---------------------------------------------------------------------------

class AzureDiagnosticsStore(BaseModel):
    """Stored in raw_azure_json column. Never sent to frontend."""
    reference_text_used: str
    recognized_text: str
    overall_scores: dict[str, float]
    prosody: dict[str, Any]
    flagged_word_count: int = Field(ge=0)
    issue_category_counts: dict[str, int] = {}
    segment_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    patterns: list[str] = []
    assessment_metadata: dict[str, Any] = {}
    segments: list[dict[str, Any]] = []
