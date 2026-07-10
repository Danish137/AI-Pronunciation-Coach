from datetime import datetime, timedelta
import logging

from ..core.database import SessionLocal
from ..repositories.attempts import AttemptRepository

logger = logging.getLogger("pronounceai.retention")


def purge_expired_attempts(retention_days: int) -> int:
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    with SessionLocal() as db:
        repo = AttemptRepository(db)
        deleted = repo.delete_expired_before(cutoff)
    logger.info(
        "Attempt retention purge completed | retention_days=%d | deleted=%d",
        retention_days,
        deleted,
    )
    return deleted
