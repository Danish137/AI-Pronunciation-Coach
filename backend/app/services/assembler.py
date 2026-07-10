"""
Stage 8 – Response assembler.

Maps DiagnosticsBundle + validated LLM coaching → AssessmentResponse.

Rules:
- Scores come from DiagnosticsBundle (Azure source of truth)
- Coaching text comes from validated LLM output or deterministic fallbacks
- No ARPABET tokens ever reach this layer
- No internal fields ever appear in the output schema
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from ..schemas.assessment import (
    AssessmentResponse,
    PatternInsight,
    PracticeDrill,
    PracticeSession,
    RecordingSummary,
    ScoreMetric,
    WordCoaching,
)
from ..schemas.internal import DiagnosticsBundle, SpeakingPattern, WordDiagnosis
from .diagnostics import COACHING_THRESHOLD
from .pronunciation_dict import lookup as lookup_pronunciation

logger = logging.getLogger("pronounceai.assembler")


def assemble_response(
    bundle: DiagnosticsBundle,
    validated_llm: dict[str, Any],
    provider_mode: str,
) -> AssessmentResponse:
    metrics = _build_metrics(bundle)
    word_coaching = _build_word_coaching(bundle, validated_llm)
    summary = _build_summary(bundle, validated_llm, word_coaching)
    practice = _build_practice_session(bundle, word_coaching)

    return AssessmentResponse(
        overall_score=bundle.scores.overall,
        accuracy_score=bundle.scores.accuracy,
        fluency_score=bundle.scores.fluency,
        prosody_score=bundle.scores.prosody,
        completeness_score=bundle.scores.completeness,
        duration_seconds=bundle.scores.duration_seconds,
        transcript=bundle.transcript,
        provider_mode=provider_mode,  # type: ignore[arg-type]
        summary=summary,
        metrics=metrics,
        word_coaching=word_coaching,
        practice=practice,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _build_metrics(bundle: DiagnosticsBundle) -> list[ScoreMetric]:
    s = bundle.scores
    pattern_text = (
        bundle.speaking_patterns[0].description
        if bundle.speaking_patterns
        else _default_overall_explanation(bundle)
    )
    return [
        ScoreMetric(
            key="overall",
            label="Overall",
            score=s.overall,
            band=_band(s.overall),
            explanation=pattern_text,
        ),
        ScoreMetric(
            key="accuracy",
            label="Accuracy",
            score=s.accuracy,
            band=_band(s.accuracy),
            explanation=_accuracy_explanation(bundle),
        ),
        ScoreMetric(
            key="fluency",
            label="Fluency",
            score=s.fluency,
            band=_band(s.fluency),
            explanation=_fluency_explanation(s),
        ),
        ScoreMetric(
            key="prosody",
            label="Prosody",
            score=s.prosody,
            band=_band(s.prosody),
            explanation=_prosody_explanation(bundle),
        ),
        ScoreMetric(
            key="completeness",
            label="Completeness",
            score=s.completeness,
            band=_band(s.completeness),
            explanation=_completeness_explanation(s),
        ),
    ]


def _default_overall_explanation(bundle: DiagnosticsBundle) -> str:
    if not bundle.words_needing_coaching:
        return "Pronunciation is strong across the recording."
    words = [d.word for d in bundle.words_needing_coaching[:3]]
    return f"Main deductions came from {', '.join(words)}."


def _accuracy_explanation(bundle: DiagnosticsBundle) -> str:
    severe = [d for d in bundle.words_needing_coaching if d.severity == "severe"]
    if not severe:
        return "Individual word forms were mostly clear and recognizable."
    return (
        f"{len(severe)} word{'s' if len(severe) > 1 else ''} "
        f"({', '.join(d.word for d in severe[:3])}) scored significantly below average."
    )


def _fluency_explanation(s) -> str:
    if s.fluency >= 85:
        return "Speech flowed continuously without major pauses or breaks."
    if s.fluency >= 72:
        return "Flow was mostly steady with some minor hesitations."
    return "Several pauses or breaks reduced the overall flow of the recording."


def _prosody_explanation(bundle: DiagnosticsBundle) -> str:
    if not bundle.has_prosody_issue:
        return "Rhythm and emphasis were natural and varied across the recording."
    stress_words = [d.word for d in bundle.words_needing_coaching if d.has_stress_error]
    if stress_words:
        return (
            f"Stress placement was inconsistent on {', '.join(stress_words[:3])}. "
            "Natural English rhythm relies on stressed syllables being longer and louder."
        )
    return "Sentence rhythm was relatively flat — more variation in stress and pitch would help."


def _completeness_explanation(s) -> str:
    if s.completeness >= 90:
        return "Nearly all of the spoken content was captured and recognized."
    return "Some words may not have been fully captured — clearer articulation of endings will help."


# ---------------------------------------------------------------------------
# Word coaching
# ---------------------------------------------------------------------------

def _build_word_coaching(
    bundle: DiagnosticsBundle,
    validated_llm: dict[str, Any],
) -> list[WordCoaching]:
    llm_by_word: dict[str, dict[str, Any]] = {}
    for item in validated_llm.get("word_coaching", []):
        word_key = (item.get("word") or "").lower()
        if word_key:
            llm_by_word[word_key] = item

    coaching: list[WordCoaching] = []
    for diag in bundle.words_needing_coaching:
        llm_item = llm_by_word.get(diag.word.lower())
        if llm_item:
            coaching.append(_word_coaching_from_llm(diag, llm_item))
        else:
            coaching.append(_word_coaching_fallback(diag, bundle.transcript))

    return coaching


def _word_coaching_from_llm(
    diag: WordDiagnosis,
    llm: dict[str, Any],
) -> WordCoaching:
    drills = llm.get("practice_drills") or [diag.word]
    # Always use CMU dict for the pronunciation hint — never trust LLM-generated hints
    pron = lookup_pronunciation(diag.word)
    hint = pron.stress_hint if pron else None
    return WordCoaching(
        word=diag.word,
        score=diag.score,
        severity=diag.severity,  # type: ignore[arg-type]
        what_happened=str(llm.get("what_happened") or "").strip(),
        why=str(llm.get("why") or "").strip(),
        how_to_fix=str(llm.get("how_to_fix") or "").strip(),
        practice_drills=drills[:3],
        native_audio_hint=hint,
        start_ms=diag.offset_ms,
        end_ms=diag.offset_ms + diag.duration_ms,
    )


def _word_coaching_fallback(
    diag: WordDiagnosis,
    transcript: str,
) -> WordCoaching:
    """Deterministic coaching when LLM is unavailable or failed validation."""
    what_happened = _fallback_what_happened(diag)
    why = _fallback_why(diag)
    how_to_fix = _fallback_how_to_fix(diag)
    drills = _build_drill_progression(diag, transcript)
    pron = lookup_pronunciation(diag.word)

    return WordCoaching(
        word=diag.word,
        score=diag.score,
        severity=diag.severity,  # type: ignore[arg-type]
        what_happened=what_happened,
        why=why,
        how_to_fix=how_to_fix,
        practice_drills=drills,
        native_audio_hint=pron.stress_hint if pron else None,
        start_ms=diag.offset_ms,
        end_ms=diag.offset_ms + diag.duration_ms,
    )


def _fallback_what_happened(diag: WordDiagnosis) -> str:
    if diag.error_type == "Omission":
        return f"'{diag.word}' was not clearly recognized — part of the word may have dropped out entirely."
    if diag.error_type == "Insertion":
        return f"'{diag.word}' picked up an extra sound that was not expected."
    if diag.has_final_consonant_drop and diag.weakest_syllable_grapheme:
        return f"The ending of '{diag.word}' dropped — the final sound did not come through clearly."
    if diag.has_final_consonant_drop:
        return f"'{diag.word}' lost its final consonant — the word trailed off before finishing."
    if diag.weakest_syllable_grapheme:
        return (
            f"The '{diag.weakest_syllable_grapheme}' part of '{diag.word}' was the least stable "
            f"syllable (scored {round(diag.weakest_syllable_score or 0)}/100)."
        )
    return f"'{diag.word}' scored {round(diag.score)}/100 — the articulation was less precise than your stronger words."


def _fallback_why(diag: WordDiagnosis) -> str:
    if diag.error_type == "Omission":
        return "Omitted sounds make words harder to recognize, especially in connected speech."
    if diag.has_stress_error:
        return (
            f"Stress landed on the wrong syllable in '{diag.word}', "
            "which changes how the word sounds to a listener."
        )
    if diag.weakest_syllable_grapheme and diag.weakest_syllable_score is not None:
        score = round(diag.weakest_syllable_score)
        return (
            f"The '{diag.weakest_syllable_grapheme}' syllable scored {score}/100 — "
            "that's the part pulling the word's overall score down."
        )
    if diag.has_final_consonant_drop:
        return (
            "Listeners use final consonants to identify words. "
            "When they drop, words blur together."
        )
    return f"The lower score on '{diag.word}' reduces clarity when this word appears in fast speech."


def _fallback_how_to_fix(diag: WordDiagnosis) -> str:
    if diag.error_type == "Omission":
        return (
            f"Say '{diag.word}' slowly and make every syllable audible before returning to normal speed. "
            "Record yourself and compare."
        )
    if diag.has_final_consonant_drop:
        return (
            f"Hold the final sound of '{diag.word}' for an extra beat. "
            "Exaggerate it in practice, then gradually return to natural speed."
        )
    if diag.has_stress_error and diag.weakest_syllable_grapheme:
        return (
            f"Try landing the main stress on '{diag.weakest_syllable_grapheme}' "
            f"and making it slightly longer and louder than the other syllables."
        )
    if diag.weakest_syllable_grapheme:
        return (
            f"Practice the '{diag.weakest_syllable_grapheme}' syllable in isolation, "
            f"then rebuild the full word around it: first slow, then at normal speed."
        )
    return (
        f"Say '{diag.word}' once very slowly (half speed), "
        "then once at normal speed, keeping all syllables equally audible."
    )


def _build_drill_progression(diag: WordDiagnosis, transcript: str) -> list[str]:
    word = diag.word
    # Level 1: isolated
    drills = [word]
    # Level 2: short phrase — use a 2-word context from transcript if possible
    phrase = _find_phrase_in_transcript(word, transcript, context_words=1)
    drills.append(phrase or f"the {word}")
    # Level 3: sentence — pull from transcript or construct minimal one
    sentence = _find_sentence_in_transcript(word, transcript)
    drills.append(sentence or f"I need to say {word} clearly in every sentence.")
    return drills


def _find_phrase_in_transcript(word: str, transcript: str, context_words: int = 1) -> str | None:
    tokens = transcript.split()
    lower_tokens = [t.lower().strip(".,!?;:") for t in tokens]
    for idx, token in enumerate(lower_tokens):
        if token == word.lower():
            start = max(0, idx - context_words)
            end = min(len(tokens), idx + context_words + 1)
            phrase = " ".join(tokens[start:end])
            if len(phrase) > len(word):
                return phrase
    return None


def _find_sentence_in_transcript(word: str, transcript: str) -> str | None:
    sentences = [s.strip() for s in transcript.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    for sentence in sentences:
        if word.lower() in sentence.lower() and len(sentence.split()) >= 4:
            return sentence
    return None


# ---------------------------------------------------------------------------
# Recording summary
# ---------------------------------------------------------------------------

def _build_summary(
    bundle: DiagnosticsBundle,
    validated_llm: dict[str, Any],
    word_coaching: list[WordCoaching],
) -> RecordingSummary:
    llm_rs = validated_llm.get("recording_summary") if isinstance(validated_llm.get("recording_summary"), dict) else {}

    headline = f"{round(bundle.scores.overall)}/100 — {_level_label(bundle.scores.overall)}"
    level_label = _level_label(bundle.scores.overall)

    # overall_habit from LLM, or deterministic fallback
    overall_habit = str(llm_rs.get("overall_habit") or "").strip() or _fallback_overall_habit(bundle)

    # strengths from LLM, or 1-2 deterministic observations
    llm_strengths = [str(s).strip() for s in (llm_rs.get("strengths") or []) if str(s).strip()]
    strengths = llm_strengths[:2] or _fallback_strengths(bundle)

    # patterns from deterministic detection
    patterns = [_pattern_to_insight(p) for p in bundle.speaking_patterns[:3]]

    # primary_action from LLM, or deterministic
    primary_action = str(llm_rs.get("primary_action") or "").strip() or _fallback_primary_action(bundle, word_coaching)

    return RecordingSummary(
        headline=headline,
        level_label=level_label,
        overall_habit=overall_habit,
        strengths=strengths,
        patterns=patterns,
        primary_action=primary_action,
        gain_estimate=bundle.gain_estimate,
    )


def _pattern_to_insight(pattern: SpeakingPattern) -> PatternInsight:
    return PatternInsight(
        label=pattern.label,
        affected_words=pattern.affected_words,
        explanation=pattern.description,
        priority=pattern.coaching_priority,
    )


def _fallback_overall_habit(bundle: DiagnosticsBundle) -> str:
    s = bundle.scores
    if not bundle.words_needing_coaching:
        return (
            "Pronunciation is clear and consistent across the recording. "
            "The main opportunity for growth is in natural rhythm and connected speech."
        )
    if bundle.speaking_patterns:
        p = bundle.speaking_patterns[0]
        return f"{p.description} This is the most consistent pattern in the recording."
    if s.prosody < s.accuracy - 8:
        return (
            "Individual word forms are stronger than sentence rhythm. "
            "Pacing and stress placement are the main areas to develop."
        )
    top_words = [d.word for d in bundle.words_needing_coaching[:3]]
    return (
        f"Most pronunciation is clear, but a small cluster of words "
        f"({', '.join(top_words)}) is pulling the score down. "
        "Targeting them specifically will have more impact than repeating the whole recording."
    )


def _fallback_strengths(bundle: DiagnosticsBundle) -> list[str]:
    s = bundle.scores
    strengths: list[str] = []
    strong_dim = max(
        [("accuracy", s.accuracy), ("fluency", s.fluency),
         ("prosody", s.prosody), ("completeness", s.completeness)],
        key=lambda x: x[1],
    )
    mapping = {
        "accuracy": "Individual word forms were mostly recognizable and stable.",
        "fluency": "Speech flowed steadily — pauses did not disrupt the overall delivery.",
        "prosody": "Rhythm and emphasis were already natural in most of the recording.",
        "completeness": "Nearly all spoken content came through clearly.",
    }
    strengths.append(mapping[strong_dim[0]])

    excellent_count = sum(
        1 for d in bundle.word_diagnoses if d.practice_priority == "skip"
    )
    if excellent_count > 0:
        total = len(bundle.word_diagnoses)
        pct = round(excellent_count / total * 100) if total else 0
        if pct >= 70:
            strengths.append(f"{pct}% of words scored at or above 90 — the foundation is strong.")

    return strengths[:2]


def _fallback_primary_action(bundle: DiagnosticsBundle, word_coaching: list[WordCoaching]) -> str:
    if not word_coaching:
        return "Your pronunciation is already very strong — focus on natural rhythm and connected speech."
    if bundle.speaking_patterns:
        p = bundle.speaking_patterns[0]
        words = ", ".join(p.affected_words[:3])
        return f"Start with {p.label.lower()} — practice {words} to address the most repeated issue."
    top = word_coaching[0]
    if len(word_coaching) == 1:
        return f"Focus on '{top.word}' — fixing this one word will have the most immediate impact."
    second = word_coaching[1]
    return (
        f"Start with '{top.word}' and '{second.word}' — "
        "these two words are causing the majority of the score deduction."
    )


# ---------------------------------------------------------------------------
# Practice session
# ---------------------------------------------------------------------------

def _build_practice_session(
    bundle: DiagnosticsBundle,
    word_coaching: list[WordCoaching],
) -> PracticeSession:
    if not word_coaching:
        return PracticeSession(
            focus="Your pronunciation is already very strong.",
            drills=[],
            context_sentences=[],
        )

    # Group words by pattern if they share one
    pattern_map: dict[str, list[WordCoaching]] = defaultdict(list)
    coached_words_set = {wc.word.lower() for wc in word_coaching}

    for pattern in bundle.speaking_patterns:
        for word in pattern.affected_words:
            if word.lower() in coached_words_set:
                matching_coaching = next(
                    (wc for wc in word_coaching if wc.word.lower() == word.lower()), None
                )
                if matching_coaching:
                    pattern_map[pattern.pattern_id].append(matching_coaching)

    # Words not grouped under any pattern
    grouped_words = {wc.word.lower() for items in pattern_map.values() for wc in items}
    ungrouped = [wc for wc in word_coaching if wc.word.lower() not in grouped_words]

    drills: list[PracticeDrill] = []

    # One drill group per pattern
    for pattern in bundle.speaking_patterns[:3]:
        group = pattern_map.get(pattern.pattern_id, [])
        if not group:
            continue
        # Use the drills from the first word in the group but build progression
        # around all group words
        first = group[0]
        all_group_words = [wc.word for wc in group]
        progression = _pattern_progression(all_group_words, pattern, bundle.transcript)
        drills.append(PracticeDrill(
            theme=pattern.label,
            words=all_group_words,
            progression=progression,
        ))

    # Ungrouped words get individual drills
    for wc in ungrouped[:3]:
        drills.append(PracticeDrill(
            theme=wc.word,
            words=[wc.word],
            progression=wc.practice_drills,
        ))

    # Focus line
    if bundle.speaking_patterns:
        focus = f"Today: {bundle.speaking_patterns[0].label}"
    elif word_coaching:
        focus = f"Today: Focus on {', '.join(wc.word for wc in word_coaching[:3])}"
    else:
        focus = "Today: General pronunciation review"

    # Context sentences from transcript
    context_sentences = _extract_context_sentences(
        bundle.transcript,
        [wc.word for wc in word_coaching[:5]],
    )

    return PracticeSession(
        focus=focus,
        drills=drills,
        context_sentences=context_sentences,
    )


def _pattern_progression(
    words: list[str],
    pattern: SpeakingPattern,
    transcript: str,
) -> list[str]:
    """Build a 3-level progression for a group of words sharing a pattern."""
    if not words:
        return []
    # Level 1: most severe word in isolation
    level1 = words[0]
    # Level 2: two target words combined into a short phrase
    if len(words) >= 2:
        level2 = f"{words[0]} and {words[1]}"
    else:
        level2 = _find_phrase_in_transcript(words[0], transcript, context_words=2) or f"the {words[0]}"
    # Level 3: sentence from transcript containing one of the words
    level3 = None
    for word in words:
        sentence = _find_sentence_in_transcript(word, transcript)
        if sentence:
            level3 = sentence
            break
    if not level3:
        level3 = f"I can clearly say {' and '.join(words[:2])} in a full sentence."
    return [level1, level2, level3]


def _extract_context_sentences(transcript: str, focus_words: list[str]) -> list[str]:
    if not transcript or not focus_words:
        return []
    sentences = [s.strip() for s in transcript.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    result: list[str] = []
    seen: set[str] = set()
    for word in focus_words:
        for sentence in sentences:
            if word.lower() in sentence.lower() and sentence not in seen and len(sentence.split()) >= 4:
                result.append(sentence)
                seen.add(sentence)
                break
    return result[:4]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _band(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 82:
        return "Strong"
    if score >= 72:
        return "Developing"
    return "Needs work"


def _level_label(score: float) -> str:
    if score >= 92:
        return "Excellent pronunciation"
    if score >= 84:
        return "Strong pronunciation"
    if score >= 74:
        return "Good foundation"
    return "Needs focused practice"


# Re-export for use in assembler
_find_phrase_in_transcript = _find_phrase_in_transcript
_find_sentence_in_transcript = _find_sentence_in_transcript
