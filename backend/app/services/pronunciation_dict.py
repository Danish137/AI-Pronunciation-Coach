"""
Pronunciation dictionary service.

Source of truth for: IPA, friendly stress hint, syllable breakdown, stress position.
Uses the CMU Pronouncing Dictionary (bundled via the `cmudict` package).

The LLM is NEVER used for pronunciation guides. If a word is not in CMU,
native_audio_hint is omitted entirely rather than generated.
"""
from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger("pronounceai.pronunciation_dict")

# ---------------------------------------------------------------------------
# ARPABET → IPA mapping (monophthongs, diphthongs, consonants)
# ---------------------------------------------------------------------------
_ARPABET_TO_IPA: dict[str, str] = {
    # Vowels
    "AA": "ɑ", "AE": "æ", "AH": "ə", "AO": "ɔ",
    "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "ER": "ɜːr",
    "EY": "eɪ", "IH": "ɪ", "IY": "iː", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "uː",
    # Consonants
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð",
    "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ",
    "K": "k", "L": "l", "M": "m", "N": "n",
    "NG": "ŋ", "P": "p", "R": "r", "S": "s",
    "SH": "ʃ", "T": "t", "TH": "θ", "V": "v",
    "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}

# ---------------------------------------------------------------------------
# ARPABET → friendly syllable spelling
# Maps each phoneme to its most common English spelling approximation
# used in stress guides like "en-juh-NEER"
# ---------------------------------------------------------------------------
_ARPABET_TO_FRIENDLY: dict[str, str] = {
    "AA": "ah", "AE": "a", "AH": "uh", "AO": "aw",
    "AW": "ow", "AY": "eye", "EH": "eh", "ER": "er",
    "EY": "ay", "IH": "ih", "IY": "ee", "OW": "oh",
    "OY": "oy", "UH": "oo", "UW": "oo",
    "B": "b", "CH": "ch", "D": "d", "DH": "th",
    "F": "f", "G": "g", "HH": "h", "JH": "j",
    "K": "k", "L": "l", "M": "m", "N": "n",
    "NG": "ng", "P": "p", "R": "r", "S": "s",
    "SH": "sh", "T": "t", "TH": "th", "V": "v",
    "W": "w", "Y": "y", "Z": "z", "ZH": "zh",
}

# Plain-English descriptions of phonemes for coaching text
PHONEME_PLAIN_ENGLISH: dict[str, str] = {
    "AA": 'the "ah" sound (as in "father")',
    "AE": 'the short "a" sound (as in "cat")',
    "AH": 'the weak "uh" sound (schwa, as in "about")',
    "AO": 'the "aw" sound (as in "law")',
    "AW": 'the "ow" sound (as in "cow")',
    "AY": 'the long "i" sound (as in "my")',
    "EH": 'the short "e" sound (as in "bed")',
    "ER": 'the R-colored vowel (as in "her" or "bird")',
    "EY": 'the long "a" sound (as in "say")',
    "IH": 'the short "i" sound (as in "sit")',
    "IY": 'the long "ee" sound (as in "see")',
    "OW": 'the long "o" sound (as in "go")',
    "OY": 'the "oy" sound (as in "boy")',
    "UH": 'the short "oo" sound (as in "book")',
    "UW": 'the long "oo" sound (as in "food")',
    "B": 'the "b" sound',
    "CH": 'the "ch" sound (as in "chair")',
    "D": 'the "d" sound',
    "DH": 'the voiced "th" (as in "the")',
    "F": 'the "f" sound',
    "G": 'the "g" sound (as in "go")',
    "HH": 'the "h" sound',
    "JH": 'the "j" sound (as in "jump")',
    "K": 'the "k" sound',
    "L": 'the "l" sound',
    "M": 'the "m" sound',
    "N": 'the "n" sound',
    "NG": 'the "ng" sound (as in "sing")',
    "P": 'the "p" sound',
    "R": 'the American "r" sound',
    "S": 'the "s" sound',
    "SH": 'the "sh" sound (as in "shoe")',
    "T": 'the "t" sound',
    "TH": 'the unvoiced "th" (as in "think")',
    "V": 'the "v" sound',
    "W": 'the "w" sound',
    "Y": 'the "y" glide (as in "yes")',
    "Z": 'the "z" sound',
    "ZH": 'the "zh" sound (as in "measure")',
}


@lru_cache(maxsize=1)
def _load_cmu_dict() -> dict[str, list[list[str]]]:
    try:
        import cmudict  # type: ignore[import-not-found]
        return cmudict.dict()
    except Exception as exc:
        logger.warning("cmudict unavailable: %s", exc)
        return {}


def _strip_stress(phone: str) -> str:
    return phone.rstrip("012")


def _get_stress_digit(phone: str) -> str:
    if phone[-1:].isdigit():
        return phone[-1]
    return ""


def _phones_to_ipa(phones: list[str]) -> str:
    return "".join(_ARPABET_TO_IPA.get(_strip_stress(p), "") for p in phones)


def _phones_to_syllables(phones: list[str]) -> list[str]:
    """
    Split ARPABET phones into syllables.
    Rule: each syllable consists of onset consonants + nucleus vowel + coda consonants.
    We split before each vowel, keeping any preceding consonants with it (onset).
    """
    vowel_indices = [i for i, p in enumerate(phones) if _get_stress_digit(p)]
    if not vowel_indices:
        return ["".join(_ARPABET_TO_FRIENDLY.get(_strip_stress(p), "") for p in phones)]

    # Build split points: each syllable starts at the first consonant before its vowel
    # that isn't already claimed by the previous syllable's coda.
    split_starts = [0]
    for i in range(1, len(vowel_indices)):
        prev_vowel = vowel_indices[i - 1]
        curr_vowel = vowel_indices[i]
        consonants_between = list(range(prev_vowel + 1, curr_vowel))
        if not consonants_between:
            split_starts.append(curr_vowel)
        elif len(consonants_between) == 1:
            # Single consonant goes to next syllable as onset
            split_starts.append(consonants_between[0])
        else:
            # Multiple consonants: last one goes to onset, rest stay as coda
            split_starts.append(consonants_between[-1])

    split_starts.append(len(phones))

    syllables: list[str] = []
    for start, end in zip(split_starts, split_starts[1:]):
        chunk = phones[start:end]
        text = "".join(_ARPABET_TO_FRIENDLY.get(_strip_stress(p), "") for p in chunk)
        if text:
            syllables.append(text)

    return syllables or [
        "".join(_ARPABET_TO_FRIENDLY.get(_strip_stress(p), "") for p in phones)
    ]


def _build_stress_hint(phones: list[str]) -> str:
    """
    Build a stress guide like 'en-juh-NEER' or 'ih-SPESH-uh-lee'.
    Uses the same syllable split as _phones_to_syllables.

    CMU convention: when a word has two vowels marked stress=1 (e.g. 'engineer':
    EH1 N JH AH0 N IH1 R), the last one carries the primary phrasal stress.
    The earlier one is treated as secondary (Title Case).
    Unstressed is lowercase.
    """
    vowel_indices = [i for i, p in enumerate(phones) if _get_stress_digit(p)]
    if not vowel_indices:
        return "".join(_ARPABET_TO_FRIENDLY.get(_strip_stress(p), "") for p in phones)

    # Find the last vowel that carries stress=1 (primary)
    primary_vowel_idx: int | None = None
    for i in reversed(range(len(vowel_indices))):
        if _get_stress_digit(phones[vowel_indices[i]]) == "1":
            primary_vowel_idx = vowel_indices[i]
            break

    split_starts = [0]
    for i in range(1, len(vowel_indices)):
        prev_vowel = vowel_indices[i - 1]
        curr_vowel = vowel_indices[i]
        consonants_between = list(range(prev_vowel + 1, curr_vowel))
        if not consonants_between:
            split_starts.append(curr_vowel)
        elif len(consonants_between) == 1:
            split_starts.append(consonants_between[0])
        else:
            split_starts.append(consonants_between[-1])
    split_starts.append(len(phones))

    syllables: list[str] = []
    for start, end in zip(split_starts, split_starts[1:]):
        chunk = phones[start:end]
        text = "".join(_ARPABET_TO_FRIENDLY.get(_strip_stress(p), "") for p in chunk)
        # Determine stress level for this syllable's nucleus
        nucleus_idx = None
        for p_idx in range(start, end):
            if _get_stress_digit(phones[p_idx]):
                nucleus_idx = p_idx
                break
        if nucleus_idx == primary_vowel_idx:
            text = text.upper()  # Primary stress
        elif nucleus_idx is not None and _get_stress_digit(phones[nucleus_idx]) in ("1", "2"):
            text = text.capitalize()  # Secondary stress
        else:
            text = text.lower()
        syllables.append(text)

    return "-".join(syllables)


class WordPronunciation:
    __slots__ = ("word", "ipa", "stress_hint", "syllables", "stress_position", "phonemes")

    def __init__(
        self,
        word: str,
        ipa: str,
        stress_hint: str,
        syllables: list[str],
        stress_position: int | None,
        phonemes: list[str],
    ):
        self.word = word
        self.ipa = ipa                      # e.g.  ˌɛn.dʒəˈnɪr
        self.stress_hint = stress_hint      # e.g.  en-juh-NEER
        self.syllables = syllables          # e.g.  ["en", "juh", "neer"]
        self.stress_position = stress_position  # 1-indexed, 1 = first syllable
        self.phonemes = phonemes            # raw ARPABET e.g. ["EH1","N","JH",...]


def lookup(word: str) -> WordPronunciation | None:
    """
    Look up a word in CMU dict.
    Returns None if the word is not found — callers must handle this gracefully.
    The LLM must NEVER be used as a fallback for pronunciation data.
    """
    clean = word.lower().strip(".,!?;:'\"")
    cmu = _load_cmu_dict()
    phones_variants = cmu.get(clean)
    if not phones_variants:
        return None

    phones = phones_variants[0]  # use first (most common) pronunciation

    ipa = _phones_to_ipa(phones)
    stress_hint = _build_stress_hint(phones)
    syllables = _phones_to_syllables(phones)

    # stress_position: which syllable (1-indexed) carries primary stress
    # When multiple vowels have stress=1 (e.g. "engineer"), use the last one
    # as it represents the primary phrasal stress in CMU convention.
    vowels_in_order = [p for p in phones if _get_stress_digit(p)]
    stress_position: int | None = None
    last_primary = None
    for i, p in enumerate(vowels_in_order):
        if _get_stress_digit(p) == "1":
            last_primary = i + 1
    stress_position = last_primary

    return WordPronunciation(
        word=clean,
        ipa=ipa,
        stress_hint=stress_hint,
        syllables=syllables,
        stress_position=stress_position,
        phonemes=phones,
    )


def phoneme_plain_english(arpabet_symbol: str) -> str:
    """Convert an ARPABET symbol to a plain English description for coaching."""
    base = arpabet_symbol.rstrip("012")
    return PHONEME_PLAIN_ENGLISH.get(base, f'the "{base}" sound')
