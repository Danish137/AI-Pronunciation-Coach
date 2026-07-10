"""
Stage 6 – LLM coaching.

The LLM receives only pre-computed diagnostics — no raw phoneme arrays,
no ARPABET tokens, no syllable token strings.
It generates natural language only: what_happened, why, how_to_fix,
practice_drills, and the recording-level summary.

All diagnostic facts (scores, severity, phoneme symbols, patterns) come
from the DiagnosticsBundle. The LLM cannot invent them.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..core.config import get_settings
from ..schemas.internal import DiagnosticsBundle, SpeakingPattern, WordDiagnosis
from .pronunciation_dict import lookup as lookup_pronunciation, phoneme_plain_english

settings = get_settings()
logger = logging.getLogger("pronounceai.coach")

# Map ARPABET symbols to plain English descriptions for LLM input
# The LLM never sees raw ARPABET — it sees "the R-colored vowel" etc.
_PHONEME_DESCRIPTIONS: dict[str, str] = {
    "R": "the R sound",
    "ER": "the R-colored vowel (as in 'her' or 'engineer')",
    "L": "the L sound",
    "TH": "the TH sound (as in 'think')",
    "DH": "the voiced TH (as in 'the')",
    "V": "the V sound",
    "W": "the W sound",
    "SH": "the SH sound",
    "ZH": "the ZH sound (as in 'measure')",
    "NG": "the NG sound (as in 'sing')",
    "AE": "the short A vowel (as in 'cat')",
    "AH": "the schwa or short U (as in 'about')",
    "EH": "the short E vowel (as in 'bed')",
    "IH": "the short I vowel (as in 'sit')",
    "AO": "the AW vowel (as in 'law')",
    "OW": "the long O vowel (as in 'go')",
    "UW": "the long U vowel (as in 'food')",
    "IY": "the long E vowel (as in 'see')",
    "EY": "the long A vowel (as in 'say')",
    "AY": "the I vowel (as in 'my')",
    "AW": "the OW vowel (as in 'cow')",
    "CH": "the CH sound (as in 'chair')",
    "JH": "the J sound (as in 'jump')",
    "S": "the S sound",
    "Z": "the Z sound",
    "T": "the T sound",
    "D": "the D sound",
    "K": "the K sound",
    "G": "the G sound",
    "P": "the P sound",
    "B": "the B sound",
    "F": "the F sound",
    "M": "the M sound",
    "N": "the N sound",
    "H": "the H sound",
    "Y": "the Y sound",
}


def _phoneme_description(symbol: str | None) -> str | None:
    if not symbol:
        return None
    base = symbol.rstrip("012")
    return _PHONEME_DESCRIPTIONS.get(base, f"the {base} sound")


def _build_word_input(diag: WordDiagnosis) -> dict[str, Any]:
    """Minimal, clean representation of a word diagnosis for the LLM."""
    # Look up authoritative pronunciation from CMU dict
    pron = lookup_pronunciation(diag.word)
    return {
        "word": diag.word,
        "score": diag.score,
        "severity": diag.severity,
        "error_type": diag.error_type if diag.error_type not in ("None", "") else None,
        # Plain English descriptions — never raw ARPABET
        "weakest_sound": phoneme_plain_english(diag.weakest_phoneme_symbol) if diag.weakest_phoneme_symbol else None,
        "weakest_sound_score": round(diag.weakest_phoneme_score, 1) if diag.weakest_phoneme_score is not None else None,
        "weakest_sound_is_final": diag.weakest_phoneme_is_final if diag.weakest_phoneme_symbol else None,
        "weakest_syllable": diag.weakest_syllable_grapheme,
        "weakest_syllable_score": round(diag.weakest_syllable_score, 1) if diag.weakest_syllable_score is not None else None,
        "final_consonant_dropped": diag.has_final_consonant_drop or None,
        "stress_error": diag.has_stress_error or None,
        "issue_categories": diag.issue_categories or None,
        # Authoritative pronunciation data from CMU — LLM must use these, not invent
        "correct_stress_hint": pron.stress_hint if pron else None,
        "correct_syllables": pron.syllables if pron else None,
        "correct_stress_position": pron.stress_position if pron else None,
    }


def _build_pattern_input(pattern: SpeakingPattern) -> dict[str, Any]:
    return {
        "label": pattern.label,
        "description": pattern.description,
        "affected_words": pattern.affected_words[:5],
        "frequency": pattern.frequency,
        "severity": pattern.severity,
    }


def _build_llm_payload(bundle: DiagnosticsBundle) -> dict[str, Any]:
    """Build the minimal JSON payload sent to the LLM."""
    return {
        "scores": {
            "overall": bundle.scores.overall,
            "accuracy": bundle.scores.accuracy,
            "fluency": bundle.scores.fluency,
            "prosody": bundle.scores.prosody,
            "completeness": bundle.scores.completeness,
        },
        "evidence_quality": bundle.evidence_quality,
        "gain_estimate": bundle.gain_estimate,
        "transcript_excerpt": bundle.transcript[:300],
        "words_to_coach": [
            _build_word_input(d) for d in bundle.words_needing_coaching[:8]
        ],
        "speaking_patterns": [
            _build_pattern_input(p) for p in bundle.speaking_patterns[:4]
        ],
    }


_SYSTEM_PROMPT = """\
You are a pronunciation coach for adult English learners.
You receive structured diagnostic data. Never invent facts beyond what is provided.

Rules:
- Never mention Azure, APIs, ARPABET, or phoneme codes like ER1, AH0.
- Never invent scores, phoneme names, or syllables not in the input.
- Never repeat the same explanation across different fields.
- Do NOT generate native_audio_hint — it is provided from a pronunciation dictionary.
- what_happened: one sentence — what the learner did wrong, specific to this word and the evidence provided.
- why: one sentence — which specific sound or syllable caused the issue and why it affects intelligibility.
- how_to_fix: 2-3 sentences of physical articulation instruction. Be specific:
  * Describe tongue/lip/jaw position
  * Reference the correct_stress_hint syllables by name when relevant
  * Tell the learner what to avoid (e.g. "avoid starting with 'ex'")
  * Do NOT say "focus on the X sound" — describe HOW to produce it
- practice_drills: exactly 3 strings that build progressively:
  * [0] the word in isolation
  * [1] a 3-5 word phrase where the target sound repeats or the word appears naturally
  * [2] a full sentence that ideally contains the word multiple times or uses related vocabulary
  The goal is maximum repetition of the target pattern, not variety.
- overall_habit: two sentences about the learner's most consistent speaking pattern across the whole recording.
- primary_action: one sentence — most impactful single fix.
- No motivational filler. Sound like a knowledgeable human coach.
- Return strict JSON only."""


def _build_user_prompt(bundle: DiagnosticsBundle) -> str:
    payload = _build_llm_payload(bundle)
    schema = {
        "recording_summary": {
            "overall_habit": "2 sentences about the learner's most consistent speaking pattern",
            "strengths": ["1-2 short evidence-based strength statements"],
            "primary_action": "1 sentence — what to fix first",
        },
        "word_coaching": [
            {
                "word": "exact word from words_to_coach",
                "what_happened": "1 sentence — what specifically went wrong",
                "why": "1 sentence — which sound or syllable and why it matters for intelligibility",
                "how_to_fix": "2-3 sentences — physical articulation instruction using correct_stress_hint syllables",
                "practice_drills": [
                    "word in isolation",
                    "short phrase that maximizes repetition of the target sound",
                    "full sentence with multiple occurrences of the word or related words",
                ],
            }
        ],
    }
    return (
        f"Evidence:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"Required JSON shape:\n{json.dumps(schema, ensure_ascii=False)}"
    )


async def generate_coaching(bundle: DiagnosticsBundle) -> dict[str, Any] | None:
    """
    Call the LLM with structured diagnostics and return parsed coaching JSON.
    Returns None on failure — caller falls back to deterministic coaching.
    """
    if not settings.groq_api_key:
        return None
    if not bundle.words_needing_coaching:
        return None

    user_prompt = _build_user_prompt(bundle)
    logger.debug("LLM_INPUT_WORDS %d PATTERNS %d",
                 len(bundle.words_needing_coaching), len(bundle.speaking_patterns))

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": settings.groq_model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            logger.debug("LLM_RESPONSE_KEYS %s", list(parsed.keys()))
            return parsed
    except httpx.HTTPStatusError as exc:
        logger.warning("LLM call failed (HTTP %s): %s",
                       exc.response.status_code if exc.response is not None else "?",
                       exc.response.text[:200] if exc.response is not None else "")
        return None
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return None
