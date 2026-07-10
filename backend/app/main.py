from contextlib import asynccontextmanager
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.assessments import router as assessments_router
from .core.config import get_settings
from .core.database import create_tables
from .services.retention import purge_expired_attempts

settings = get_settings()
logger = logging.getLogger("pronounceai")


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    deleted = purge_expired_attempts(settings.attempt_retention_days)
    logger.info(
        "Attempt retention startup purge completed | retention_days=%d | deleted=%d",
        settings.attempt_retention_days,
        deleted,
    )
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        purge_expired_attempts,
        trigger="cron",
        hour=settings.retention_purge_hour_utc,
        kwargs={"retention_days": settings.attempt_retention_days},
        id="attempt-retention-purge",
        replace_existing=True,
    )
    scheduler.start()
    logger.warning(
        "PronounceAI startup config | mock=%s | azure_key=%s | azure_region=%s | groq_key=%s",
        settings.enable_mock_analysis,
        bool(settings.azure_speech_key),
        bool(settings.azure_speech_region),
        bool(settings.groq_api_key),
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="PronounceAI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessments_router, prefix="/api")


@app.get("/health")
def healthcheck() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "mock_mode_enabled": settings.enable_mock_analysis,
        "azure_key_configured": bool(settings.azure_speech_key),
        "azure_region_configured": bool(settings.azure_speech_region),
        "groq_key_configured": bool(settings.groq_api_key),
    }
