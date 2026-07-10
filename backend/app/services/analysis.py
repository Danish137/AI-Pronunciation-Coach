"""
Pronunciation assessment orchestrator.

Pipeline:
  Stage 1  Azure raw JSON preserved unchanged
  Stage 2  Normalizer  →  NormalizedWord list
  Stage 3  Diagnostics →  WordDiagnosis list + DiagnosticsBundle
  Stage 4  (inside diagnostics) deterministic severity / priority / evidence
  Stage 5  Patterns    →  SpeakingPattern list
  Stage 6  LLM coach   →  raw coaching JSON
  Stage 7  Validator   →  sanitized coaching JSON
  Stage 8  Assembler   →  AssessmentResponse
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status

from ..core.config import get_settings
from ..schemas.assessment import AssessmentResponse, AzureDiagnosticsStore
from ..schemas.internal import DiagnosticsBundle, NormalizedWord, ScoreSummary
from .assembler import assemble_response
from .coach import generate_coaching
from .diagnostics import build_diagnostics_bundle
from .normalizer import normalize_azure_segments, normalize_azure_words
from .patterns import detect_speaking_patterns
from .validator import validate_llm_output

settings = get_settings()
logger = logging.getLogger("pronounceai.analysis")


@dataclass
class ProviderInputs:
    normalized_audio_path: str
    reference_text: str
    duration_seconds: float


@dataclass
class RawAssessment:
    """Carries Azure-sourced data between Stage 1 and Stage 2."""
    scores: ScoreSummary
    transcript: str
    reference_text: str
    normalized_words: list[NormalizedWord]
    provider_mode: str
    raw_azure_json: dict | list | None = None
    azure_diagnostics_store: AzureDiagnosticsStore | None = None


class AssessmentService:
    async def analyze(self, inputs: ProviderInputs) -> AssessmentResponse:
        if settings.enable_mock_analysis or not (
            settings.azure_speech_key and settings.azure_speech_region
        ):
            raw = await self._mock_assessment(inputs)
        else:
            raw = await self._azure_assessment(inputs)

        return await self._run_pipeline(raw)

    # ------------------------------------------------------------------
    # Stage 1 — Azure
    # ------------------------------------------------------------------

    async def _azure_assessment(self, inputs: ProviderInputs) -> RawAssessment:
        try:
            import azure.cognitiveservices.speech as speechsdk  # type: ignore[import-not-found]
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Azure Speech SDK not installed.",
            ) from exc

        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key,
            region=settings.azure_speech_region,
        )
        speech_config.speech_recognition_language = "en-US"

        reference_text = inputs.reference_text.strip() or await self._transcribe_audio(
            speechsdk=speechsdk,
            speech_config=speech_config,
            audio_path=inputs.normalized_audio_path,
        )

        audio_config = speechsdk.audio.AudioConfig(filename=inputs.normalized_audio_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )
        assessment_config = speechsdk.PronunciationAssessmentConfig(
            reference_text=reference_text,
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=True,
        )
        assessment_config.enable_prosody_assessment()
        assessment_config.apply_to(recognizer)

        transcript_parts: list[str] = []
        segment_scores: list[dict[str, float]] = []
        raw_segments: list[dict[str, Any]] = []
        done = {"value": False}

        def stop_cb(_: object) -> None:
            done["value"] = True

        def recognized_cb(evt: object) -> None:
            result = evt.result
            if result.reason != speechsdk.ResultReason.RecognizedSpeech:
                return
            if result.text:
                transcript_parts.append(result.text)
            raw_json = json.loads(
                result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
            )
            raw_segments.append(raw_json)
            nbest = raw_json.get("NBest", [{}])[0]
            pa = nbest.get("PronunciationAssessment", {})
            segment_scores.append({
                "accuracy": float(pa.get("AccuracyScore", 0)),
                "fluency": float(pa.get("FluencyScore", 0)),
                "prosody": float(pa.get("ProsodyScore", 0)),
                "completeness": float(pa.get("CompletenessScore", 0)),
            })

        recognizer.recognized.connect(recognized_cb)
        recognizer.session_stopped.connect(stop_cb)
        recognizer.canceled.connect(stop_cb)
        recognizer.start_continuous_recognition()

        import asyncio
        for _ in range(600):
            if done["value"]:
                break
            await asyncio.sleep(0.1)
        recognizer.stop_continuous_recognition()

        recognized_text = " ".join(transcript_parts).strip()
        # Stage 2 normalization happens here for Azure
        normalized_words = normalize_azure_segments(raw_segments)

        if not recognized_text or not normalized_words:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Azure Speech could not analyze the audio.",
            )

        scores = self._aggregate_scores(segment_scores, normalized_words)
        scores.duration_seconds = inputs.duration_seconds

        diagnostics_store = AzureDiagnosticsStore(
            reference_text_used=reference_text,
            recognized_text=recognized_text,
            overall_scores={
                "overall": scores.overall,
                "accuracy": scores.accuracy,
                "fluency": scores.fluency,
                "prosody": scores.prosody,
                "completeness": scores.completeness,
            },
            prosody={},
            flagged_word_count=sum(
                1 for w in normalized_words if w.score < 90
            ),
            segment_count=len(raw_segments),
            word_count=len(normalized_words),
            segments=[self._normalize_segment_for_store(s) for s in raw_segments],
        )

        return RawAssessment(
            scores=scores,
            transcript=recognized_text,
            reference_text=reference_text,
            normalized_words=normalized_words[:200],
            provider_mode="azure",
            raw_azure_json={
                "reference_text_used": reference_text,
                "recognized_text": recognized_text,
                "segments": raw_segments,
            },
            azure_diagnostics_store=diagnostics_store,
        )

    async def _transcribe_audio(
        self, speechsdk: object, speech_config: object, audio_path: str
    ) -> str:
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )
        transcript_parts: list[str] = []
        done = {"value": False}

        def stop_cb(_: object) -> None:
            done["value"] = True

        def recognized_cb(evt: object) -> None:
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                transcript_parts.append(evt.result.text)

        recognizer.recognized.connect(recognized_cb)
        recognizer.session_stopped.connect(stop_cb)
        recognizer.canceled.connect(stop_cb)
        recognizer.start_continuous_recognition()

        import asyncio
        for _ in range(600):
            if done["value"]:
                break
            await asyncio.sleep(0.1)
        recognizer.stop_continuous_recognition()

        transcript = " ".join(transcript_parts).strip()
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not transcribe the uploaded audio.",
            )
        return transcript

    # ------------------------------------------------------------------
    # Stages 2–8 pipeline
    # ------------------------------------------------------------------

    async def _run_pipeline(self, raw: RawAssessment) -> AssessmentResponse:
        # Stage 3+4: deterministic diagnosis
        diagnoses = []
        from .diagnostics import _diagnose_word
        for w in raw.normalized_words:
            diagnoses.append(_diagnose_word(w))

        # Stage 5: pattern detection
        patterns = detect_speaking_patterns(raw.normalized_words, diagnoses)

        # Build full diagnostics bundle
        bundle: DiagnosticsBundle = build_diagnostics_bundle(
            scores=raw.scores,
            transcript=raw.transcript,
            reference_text=raw.reference_text,
            normalized_words=raw.normalized_words,
            speaking_patterns=patterns,
        )

        logger.warning(
            "PIPELINE words=%d coaching_words=%d patterns=%d evidence=%s",
            len(raw.normalized_words),
            len(bundle.words_needing_coaching),
            len(patterns),
            bundle.evidence_quality,
        )

        # Stage 6: LLM coaching
        raw_llm = await generate_coaching(bundle)

        # Stage 7: validation
        validated_llm = validate_llm_output(raw_llm or {}, bundle)

        # Stage 8: assemble response
        response = assemble_response(bundle, validated_llm, raw.provider_mode)

        logger.warning("PIPELINE_COMPLETE overall=%.1f word_coaching=%d",
                       response.overall_score, len(response.word_coaching))
        return response

    # ------------------------------------------------------------------
    # Stage 1 mock
    # ------------------------------------------------------------------

    async def _mock_assessment(self, inputs: ProviderInputs) -> RawAssessment:
        transcript = inputs.reference_text.strip() or (
            "I work on AI products and I want my pronunciation "
            "to sound clear, natural, and steady in conversation."
        )
        words_in_text = [t.strip(".,!?;:") for t in transcript.split() if t.strip(".,!?;:")]
        seed = int(
            hashlib.sha256(
                f"{transcript}|{inputs.duration_seconds}".encode()
            ).hexdigest()[:8], 16
        )
        normalized_words: list[NormalizedWord] = []
        total_score = 0.0

        for idx, word in enumerate(words_in_text[:80]):
            base = 61 + ((seed >> (idx % 8)) % 36)
            score = float(min(98, max(48, base - (8 if idx % 6 == 0 else 0))))
            total_score += score
            normalized_words.append(NormalizedWord(
                word=word,
                score=score,
                error_type="Mispronunciation" if score < 80 else "None",
                offset_ms=idx * 520,
                duration_ms=520,
                phonemes=[],
                syllables=[],
            ))

        n = max(len(normalized_words), 1)
        avg = round(total_score / n, 1)
        scores = ScoreSummary(
            overall=avg,
            accuracy=round(min(100.0, avg + 2.8), 1),
            fluency=round(max(55.0, avg - 2.0), 1),
            prosody=round(max(50.0, avg - 3.5), 1),
            completeness=round(min(100.0, avg + 4.0), 1),
            duration_seconds=inputs.duration_seconds,
        )
        return RawAssessment(
            scores=scores,
            transcript=transcript,
            reference_text=inputs.reference_text,
            normalized_words=normalized_words,
            provider_mode="mock",
            raw_azure_json=None,
        )

    # ------------------------------------------------------------------
    # Score aggregation
    # ------------------------------------------------------------------

    def _aggregate_scores(
        self,
        segment_scores: list[dict[str, float]],
        words: list[NormalizedWord],
    ) -> ScoreSummary:
        if segment_scores:
            accuracy = round(sum(s["accuracy"] for s in segment_scores) / len(segment_scores), 1)
            fluency = round(sum(s["fluency"] for s in segment_scores) / len(segment_scores), 1)
            prosody = round(sum(s["prosody"] for s in segment_scores) / len(segment_scores), 1)
            completeness = round(sum(s["completeness"] for s in segment_scores) / len(segment_scores), 1)
        else:
            accuracy = round(sum(w.score for w in words) / max(len(words), 1), 1)
            fluency = accuracy
            prosody = max(50.0, accuracy - 4)
            completeness = min(100.0, accuracy + 4)

        overall = round(
            (accuracy * 0.45) + (fluency * 0.2) + (prosody * 0.2) + (completeness * 0.15), 1
        )
        return ScoreSummary(
            overall=overall,
            accuracy=accuracy,
            fluency=fluency,
            prosody=prosody,
            completeness=completeness,
            duration_seconds=0.0,  # caller sets this via inputs.duration_seconds
        )

    def _normalize_segment_for_store(self, segment: dict[str, Any]) -> dict[str, Any]:
        nbest = segment.get("NBest", [{}])[0]
        pa = nbest.get("PronunciationAssessment", {})
        return {
            "text": segment.get("DisplayText") or nbest.get("Display") or nbest.get("Lexical"),
            "duration_ms": int(segment.get("Duration", 0) / 10_000),
            "offset_ms": int(segment.get("Offset", 0) / 10_000),
            "pronunciation_assessment": {
                "accuracy_score": _optional_float(pa.get("AccuracyScore")),
                "fluency_score": _optional_float(pa.get("FluencyScore")),
                "prosody_score": _optional_float(pa.get("ProsodyScore")),
                "completeness_score": _optional_float(pa.get("CompletenessScore")),
            },
        }


def _optional_float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None
