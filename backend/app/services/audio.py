import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from ..core.config import get_settings

settings = get_settings()
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm"}


class PreparedAudio:
    def __init__(self, original_path: Path, normalized_path: Path, duration_seconds: float):
        self.original_path = original_path
        self.normalized_path = normalized_path
        self.duration_seconds = duration_seconds
        self.temp_dir = original_path.parent

    def cleanup(self) -> None:
        for path in {self.original_path, self.normalized_path}:
            if path.exists():
                path.unlink(missing_ok=True)
        if self.temp_dir.exists():
            self.temp_dir.rmdir()


async def persist_and_prepare_audio(upload: UploadFile) -> PreparedAudio:
    suffix = Path(upload.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported audio format.")

    temp_dir = Path(tempfile.mkdtemp(prefix="pronounceai-"))
    original_path = temp_dir / f"input{suffix}"
    normalized_path = temp_dir / "normalized.wav"

    size_bytes = 0
    try:
        with original_path.open("wb") as file_obj:
            while chunk := await upload.read(1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > settings.max_audio_mb * 1024 * 1024:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio exceeds file size limit.")
                file_obj.write(chunk)

        # Normalize first — this always produces a WAV with a valid duration header,
        # even for browser-recorded webm files that have no duration in their container.
        normalize_audio(original_path, normalized_path)

        # Probe the normalized WAV — guaranteed to have a real duration.
        duration_seconds = probe_duration(normalized_path)

        if duration_seconds < settings.min_audio_seconds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Recording is too short ({duration_seconds:.0f}s). Speak for at least {settings.min_audio_seconds} seconds.",
            )
        if duration_seconds > settings.max_audio_seconds + 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Recording is too long ({duration_seconds:.0f}s). Maximum is {settings.max_audio_seconds} seconds.",
            )

        return PreparedAudio(original_path=original_path, normalized_path=normalized_path, duration_seconds=duration_seconds)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def probe_duration(path: Path) -> float:
    """
    Probe audio duration via ffprobe.
    Always called on the normalized WAV output, which has a valid duration header.
    """
    ensure_binary_available(settings.ffprobe_binary)
    command = [
        settings.ffprobe_binary,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    raw = payload.get("format", {}).get("duration")
    if raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio appears to be empty or unreadable.")
    duration = float(raw)
    if duration <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio appears to be empty.")
    return duration


def normalize_audio(source: Path, destination: Path) -> None:
    ensure_binary_available(settings.ffmpeg_binary)
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        str(destination),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def ensure_binary_available(binary_name: str) -> None:
    if shutil.which(binary_name):
        return
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Required binary '{binary_name}' is not available on the server PATH.",
    )
