"""
Stage 7 – Coaching validation.

Deterministic checks that run against LLM output before it reaches the assembler.
Rejects coaching that contradicts Azure evidence, references non-existent words,
coaches excellent words, or duplicates explanations.
"""
from __future__ import annotations

import logging
from typing import Any

from ..schemas.internal import DiagnosticsBundle

logger = logging.getLogger("pronounceai.validator")

# Azure or internal terms that should never appear in user-facing text
_FORBIDDEN_TERMS = {
    "azure", "arpabet", "nbest", "phoneme score", "accuracy score",
    "pronunciation assessment", "speechsdk", "api",
}

# Maximum allowed character overlap between two coaching explanations
# (simple deduplication heuristic)
_DUPLICATE_THRESHOLD = 0.7


def validate_llm_output(
    raw_llm: dict[str, Any],
    bundle: DiagnosticsBundle,
) -> dict[str, Any]:
    """
    Validate and sanitize LLM output.
    - Removes word_coaching items that fail validation.
    - Returns the validated dict with only safe items kept.
    - If the recording_summary fails, it is removed (assembler uses fallback).
    """
    if not raw_llm:
        return {}

    if not isinstance(raw_llm, dict):
        logger.warning("VALIDATOR: LLM output is not a dict")
        return {}

    validated: dict[str, Any] = {}

    # Validate recording summary
    rs = raw_llm.get("recording_summary")
    if isinstance(rs, dict) and _validate_recording_summary(rs):
        validated["recording_summary"] = rs
    else:
        logger.warning("VALIDATOR: recording_summary failed validation")

    # Validate word coaching
    raw_word_coaching = raw_llm.get("word_coaching", [])
    if isinstance(raw_word_coaching, list):
        validated["word_coaching"] = _validate_word_coaching(raw_word_coaching, bundle)
    else:
        validated["word_coaching"] = []

    return validated


def _validate_recording_summary(rs: dict[str, Any]) -> bool:
    if not isinstance(rs.get("overall_habit"), str) or not rs["overall_habit"].strip():
        return False
    if not isinstance(rs.get("primary_action"), str) or not rs["primary_action"].strip():
        return False
    if _contains_forbidden_terms(rs.get("overall_habit", "")):
        logger.warning("VALIDATOR: recording_summary contains forbidden terms")
        return False
    return True


def _validate_word_coaching(
    items: list[Any],
    bundle: DiagnosticsBundle,
) -> list[dict[str, Any]]:
    coaching_words = {d.word.lower() for d in bundle.words_needing_coaching}
    seen_explanations: list[str] = []
    valid: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        word = (item.get("word") or "").strip().lower()
        if not word:
            logger.warning("VALIDATOR: word_coaching item missing word")
            continue

        # Must be a word that actually needs coaching
        if word not in coaching_words:
            logger.warning("VALIDATOR: coaching generated for '%s' which is above threshold", word)
            continue

        # Required fields present and non-empty
        what_happened = str(item.get("what_happened") or "").strip()
        why = str(item.get("why") or "").strip()
        how_to_fix = str(item.get("how_to_fix") or "").strip()
        drills = item.get("practice_drills")

        if not what_happened or not why or not how_to_fix:
            logger.warning("VALIDATOR: word '%s' missing required coaching fields", word)
            continue

        if not isinstance(drills, list) or len(drills) == 0:
            logger.warning("VALIDATOR: word '%s' has no practice_drills", word)
            continue

        # Check for forbidden internal terms
        all_text = f"{what_happened} {why} {how_to_fix}"
        if _contains_forbidden_terms(all_text):
            logger.warning("VALIDATOR: word '%s' contains forbidden internal terms", word)
            continue

        # Check for duplicate explanations
        if _is_duplicate(what_happened, seen_explanations):
            logger.warning("VALIDATOR: word '%s' what_happened is a duplicate", word)
            continue

        seen_explanations.append(what_happened)

        # Ensure practice_drills contain the target word
        target_word = (item.get("word") or "").strip().lower()
        cleaned_drills = [str(d).strip() for d in drills if str(d).strip()]
        if cleaned_drills and target_word and target_word not in cleaned_drills[0].lower():
            # Force the first drill to at least start with the word
            cleaned_drills = [target_word] + cleaned_drills[:3]

        # Clamp to 3 drills
        cleaned_drills = cleaned_drills[:3]
        # Pad to 3 if LLM returned fewer
        while len(cleaned_drills) < 3:
            cleaned_drills.append(cleaned_drills[-1] if cleaned_drills else target_word)

        valid.append({
            **item,
            "word": item.get("word", "").strip(),  # preserve original casing
            "practice_drills": cleaned_drills,
            "what_happened": what_happened,
            "why": why,
            "how_to_fix": how_to_fix,
            "native_audio_hint": str(item.get("native_audio_hint") or "").strip() or None,
        })

    return valid


def _contains_forbidden_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in _FORBIDDEN_TERMS)


def _is_duplicate(candidate: str, seen: list[str]) -> bool:
    """Simple overlap check — if candidate shares too much with a seen explanation."""
    if not seen:
        return False
    candidate_words = set(candidate.lower().split())
    for seen_text in seen:
        seen_words = set(seen_text.lower().split())
        if not seen_words:
            continue
        overlap = len(candidate_words & seen_words) / max(len(seen_words), 1)
        if overlap >= _DUPLICATE_THRESHOLD:
            return True
    return False
