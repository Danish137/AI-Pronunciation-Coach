import json
import logging
from datetime import datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from ..models.attempt import Attempt
from ..schemas.assessment import (
    AssessmentResponse,
    DeleteResponse,
    HistoryItem,
    PatternInsight,
    PracticeDrill,
    PracticeSession,
    RawAzurePayloadResponse,
    RecordingSummary,
    ScoreMetric,
    WordCoaching,
)

logger = logging.getLogger("pronounceai.repository")


class AttemptRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        assessment: AssessmentResponse,
        session_id: str,
        source_type: str,
        reference_text: str,
        consent_accepted: bool,
    ) -> HistoryItem:
        now = datetime.utcnow()
        attempt = Attempt(
            session_id=session_id,
            source_type=source_type,
            reference_text=reference_text,
            transcript=assessment.transcript,
            overall_score=assessment.overall_score,
            accuracy_score=assessment.accuracy_score,
            fluency_score=assessment.fluency_score,
            prosody_score=assessment.prosody_score,
            completeness_score=assessment.completeness_score,
            duration_seconds=assessment.duration_seconds,
            # summary/coaching kept as flat strings for legacy column compat
            summary=assessment.summary.overall_habit,
            coaching=assessment.summary.primary_action,
            provider_mode=assessment.provider_mode,
            # word_feedback_json stores only the coached words (minimal)
            word_feedback_json=json.dumps(
                [item.model_dump() for item in assessment.word_coaching]
            ),
            result_payload_json=assessment.model_dump_json(),
            raw_azure_json="",  # raw Azure stored separately via /raw-azure endpoint
            consent_accepted=consent_accepted,
            consent_recorded_at=now if consent_accepted else None,
        )
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        return HistoryItem(
            **assessment.model_dump(),
            id=attempt.id,
            source_type=source_type,
            reference_text=reference_text,
            created_at=attempt.created_at,
        )

    def list_for_session(self, session_id: str) -> list[HistoryItem]:
        stmt = (
            select(Attempt)
            .where(Attempt.session_id == session_id)
            .order_by(desc(Attempt.created_at))
        )
        return [self._to_history_item(row) for row in self.db.scalars(stmt).all()]

    def get_for_session(self, session_id: str, attempt_id: int) -> HistoryItem | None:
        stmt = select(Attempt).where(
            Attempt.session_id == session_id, Attempt.id == attempt_id
        )
        attempt = self.db.scalars(stmt).first()
        return self._to_history_item(attempt) if attempt else None

    def delete_for_session(self, session_id: str, attempt_id: int) -> bool:
        return self._delete_where(Attempt.session_id == session_id, Attempt.id == attempt_id) > 0

    def delete_history(self, session_id: str) -> int:
        return self._delete_where(Attempt.session_id == session_id)

    def delete_expired_before(self, cutoff: datetime) -> int:
        return self._delete_where(Attempt.created_at < cutoff)

    def get_raw_azure_payload(
        self, session_id: str, attempt_id: int
    ) -> RawAzurePayloadResponse | None:
        stmt = select(Attempt).where(
            Attempt.session_id == session_id, Attempt.id == attempt_id
        )
        attempt = self.db.scalars(stmt).first()
        if not attempt:
            return None
        payload = json.loads(attempt.raw_azure_json) if attempt.raw_azure_json else None
        return RawAzurePayloadResponse(
            attempt_id=attempt.id,
            provider_mode=attempt.provider_mode or "mock",
            raw_azure_json=payload,
        )

    def _delete_where(self, *conditions) -> int:
        stmt = delete(Attempt).where(*conditions)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount or 0

    def _to_history_item(self, attempt: Attempt) -> HistoryItem:
        # Fast path: full payload stored and matches the current schema
        if attempt.result_payload_json:
            try:
                payload = json.loads(attempt.result_payload_json)
                # Quick schema version check before attempting full Pydantic validation.
                # Old rows have summary as a plain string; new rows have it as a dict.
                # Avoid the noisy validation error by detecting this upfront.
                if not _is_current_schema(payload):
                    return self._legacy_history_item(attempt)
                return HistoryItem(
                    **payload,
                    id=attempt.id,
                    source_type=attempt.source_type,
                    reference_text=attempt.reference_text,
                    created_at=attempt.created_at,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to deserialize result_payload_json for attempt %d: %s",
                    attempt.id, exc,
                )

        # Legacy fallback for old DB rows
        return self._legacy_history_item(attempt)

    def _legacy_history_item(self, attempt: Attempt) -> HistoryItem:
        """
        Reconstruct a HistoryItem from the flat DB columns when result_payload_json
        is absent or incompatible (old rows stored before the schema redesign).
        """
        coached_words: list[WordCoaching] = []
        try:
            raw_words = json.loads(attempt.word_feedback_json or "[]")
            for item in raw_words:
                # Old rows stored WordFeedback; new rows store WordCoaching.
                # Try new shape first, then adapt old shape.
                if "what_happened" in item:
                    coached_words.append(WordCoaching(**item))
                elif "word" in item and "score" in item:
                    # Adapt legacy WordFeedback → minimal WordCoaching
                    coached_words.append(WordCoaching(
                        word=item["word"],
                        score=item.get("score", 0),
                        severity=_score_to_severity(item.get("score", 100)),
                        what_happened=item.get("issue") or item.get("evidence_summary") or f"'{item['word']}' was flagged.",
                        why=item.get("evidence_summary") or "See score details.",
                        how_to_fix=item.get("suggestion") or f"Practice '{item['word']}' in isolation.",
                        practice_drills=[item["word"], f"the {item['word']}", f"I said {item['word']} clearly."],
                        start_ms=item.get("start_ms", 0),
                        end_ms=item.get("end_ms", 0),
                    ))
        except Exception as exc:
            logger.warning("Legacy word deserialization failed for attempt %d: %s", attempt.id, exc)

        summary = RecordingSummary(
            headline=f"{round(attempt.overall_score)}/100",
            level_label=_score_to_level(attempt.overall_score),
            overall_habit=attempt.summary or "See score details above.",
            strengths=["Stored result — re-record for full coaching detail."],
            patterns=[],
            primary_action=attempt.coaching or "Review the words above.",
            gain_estimate="Re-record to get a fresh gain estimate.",
        )

        practice = PracticeSession(
            focus="Re-record for an updated practice plan.",
            drills=[
                PracticeDrill(theme=wc.word, words=[wc.word], progression=wc.practice_drills)
                for wc in coached_words[:3]
            ],
            context_sentences=[],
        )

        metrics = [
            ScoreMetric(key="overall", label="Overall", score=attempt.overall_score,
                        band=_score_to_band(attempt.overall_score), explanation=attempt.summary or ""),
            ScoreMetric(key="accuracy", label="Accuracy", score=attempt.accuracy_score,
                        band=_score_to_band(attempt.accuracy_score), explanation=""),
            ScoreMetric(key="fluency", label="Fluency", score=attempt.fluency_score,
                        band=_score_to_band(attempt.fluency_score), explanation=""),
            ScoreMetric(key="prosody", label="Prosody", score=attempt.prosody_score,
                        band=_score_to_band(attempt.prosody_score), explanation=""),
            ScoreMetric(key="completeness", label="Completeness", score=attempt.completeness_score,
                        band=_score_to_band(attempt.completeness_score), explanation=""),
        ]

        return HistoryItem(
            id=attempt.id,
            source_type=attempt.source_type,
            reference_text=attempt.reference_text,
            transcript=attempt.transcript,
            overall_score=attempt.overall_score,
            accuracy_score=attempt.accuracy_score,
            fluency_score=attempt.fluency_score,
            prosody_score=attempt.prosody_score,
            completeness_score=attempt.completeness_score,
            duration_seconds=attempt.duration_seconds,
            provider_mode=attempt.provider_mode or "mock",
            summary=summary,
            metrics=metrics,
            word_coaching=coached_words,
            practice=practice,
            created_at=attempt.created_at,
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _is_current_schema(payload: dict) -> bool:
    """
    Returns True if the stored payload matches the current AssessmentResponse schema.
    Old rows have summary as a plain string and lack word_coaching / practice.
    New rows have summary as a dict with headline/overall_habit/etc.
    """
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("summary"), dict):
        return False
    if "word_coaching" not in payload:
        return False
    if "practice" not in payload:
        return False
    return True


def _score_to_severity(score: float) -> str:
    if score < 65:
        return "severe"
    if score < 80:
        return "moderate"
    return "minor"


def _score_to_band(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 82:
        return "Strong"
    if score >= 72:
        return "Developing"
    return "Needs work"


def _score_to_level(score: float) -> str:
    if score >= 92:
        return "Excellent pronunciation"
    if score >= 84:
        return "Strong pronunciation"
    if score >= 74:
        return "Good foundation"
    return "Needs focused practice"
