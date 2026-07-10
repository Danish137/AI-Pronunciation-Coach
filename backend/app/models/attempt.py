from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(16))
    reference_text: Mapped[str] = mapped_column(Text)
    transcript: Mapped[str] = mapped_column(Text)
    overall_score: Mapped[float] = mapped_column(Float)
    accuracy_score: Mapped[float] = mapped_column(Float)
    fluency_score: Mapped[float] = mapped_column(Float)
    prosody_score: Mapped[float] = mapped_column(Float)
    completeness_score: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    summary: Mapped[str] = mapped_column(Text)
    coaching: Mapped[str] = mapped_column(Text)
    provider_mode: Mapped[str] = mapped_column(String(16), default="mock")
    word_feedback_json: Mapped[str] = mapped_column(Text)
    result_payload_json: Mapped[str] = mapped_column(Text, default="")
    raw_azure_json: Mapped[str] = mapped_column(Text, default="")
    consent_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
