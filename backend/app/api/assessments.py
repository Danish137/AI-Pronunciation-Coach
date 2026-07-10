import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..repositories.attempts import AttemptRepository
from ..schemas.assessment import DeleteResponse, HistoryItem, RawAzurePayloadResponse
from ..services.analysis import AssessmentService, ProviderInputs
from ..services.audio import persist_and_prepare_audio

router = APIRouter(prefix="/assessment", tags=["assessment"])
logger = logging.getLogger("pronounceai.api")


def require_session_id(x_session_id: Annotated[str | None, Header()] = None) -> str:
    if not x_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing anonymous session ID.")
    return x_session_id


@router.post("", response_model=HistoryItem)
async def create_assessment(
    audio: UploadFile = File(...),
    source_type: Literal["upload", "recording"] = Form(...),
    reference_text: str = Form(...),
    consent_accepted: bool = Form(...),
    session_id: str = Depends(require_session_id),
    db: Session = Depends(get_db),
):
    if not consent_accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required before processing audio.")

    prepared_audio = await persist_and_prepare_audio(audio)
    try:
        service = AssessmentService()
        assessment = await service.analyze(
            ProviderInputs(
                normalized_audio_path=str(prepared_audio.normalized_path),
                reference_text=reference_text,
                duration_seconds=prepared_audio.duration_seconds,
            )
        )
    finally:
        prepared_audio.cleanup()

    repo = AttemptRepository(db)
    history_item = repo.create(
        assessment,
        session_id=session_id,
        source_type=source_type,
        reference_text=reference_text,
        consent_accepted=consent_accepted,
    )
    logger.warning("API_RESPONSE_JSON %s", history_item.model_dump_json())
    return history_item


@router.get("/history", response_model=list[HistoryItem])
def list_history(session_id: str = Depends(require_session_id), db: Session = Depends(get_db)):
    repo = AttemptRepository(db)
    return repo.list_for_session(session_id)


@router.get("/{attempt_id}", response_model=HistoryItem)
def get_attempt(attempt_id: int, session_id: str = Depends(require_session_id), db: Session = Depends(get_db)):
    repo = AttemptRepository(db)
    attempt = repo.get_for_session(session_id, attempt_id)
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
    return attempt


@router.get("/{attempt_id}/raw-azure", response_model=RawAzurePayloadResponse)
def get_raw_azure_payload(attempt_id: int, session_id: str = Depends(require_session_id), db: Session = Depends(get_db)):
    repo = AttemptRepository(db)
    payload = repo.get_raw_azure_payload(session_id, attempt_id)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
    return payload


@router.delete("/{attempt_id}", response_model=DeleteResponse)
def delete_attempt(attempt_id: int, session_id: str = Depends(require_session_id), db: Session = Depends(get_db)):
    repo = AttemptRepository(db)
    deleted = 1 if repo.delete_for_session(session_id, attempt_id) else 0
    return DeleteResponse(deleted=deleted)


@router.delete("/history/all", response_model=DeleteResponse)
def delete_history(session_id: str = Depends(require_session_id), db: Session = Depends(get_db)):
    repo = AttemptRepository(db)
    return DeleteResponse(deleted=repo.delete_history(session_id))
