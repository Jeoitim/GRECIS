from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GAOKAO_PATH = PROJECT_ROOT / "data" / "gaokao_3500.txt"
KAOYAN_PATH = PROJECT_ROOT / "data" / "kaoyan_5530.txt"
SUBTLEX_US_PATH = PROJECT_ROOT / "data" / "subtlex_us_20k.txt"
GRE_PATH = PROJECT_ROOT / "data" / "gre_2942.txt"
WordTier = Literal["high_school", "core", "key", "gre", "rare"]
SINGLE_WORD_RE = re.compile(r"[a-z]+(?:[-'][a-z]+)*")
CONTRACTION_FORMS = {
    "ain't": "be",
    "can't": "can",
    "shan't": "shall",
    "won't": "will",
}
IRREGULAR_FORMS = {
    "am": "be",
    "are": "be",
    "been": "be",
    "better": "good",
    "brought": "bring",
    "children": "child",
    "could": "can",
    "did": "do",
    "done": "do",
    "feet": "foot",
    "found": "find",
    "gave": "give",
    "given": "give",
    "gone": "go",
    "had": "have",
    "has": "have",
    "held": "hold",
    "is": "be",
    "made": "make",
    "men": "man",
    "mice": "mouse",
    "might": "may",
    "people": "person",
    "ran": "run",
    "re": "be",
    "should": "shall",
    "taken": "take",
    "teeth": "tooth",
    "took": "take",
    "was": "be",
    "were": "be",
    "went": "go",
    "ve": "have",
    "women": "woman",
    "worse": "bad",
    "would": "will",
    "ll": "will",
    "written": "write",
    "wrote": "write",
}


@lru_cache(maxsize=1)
def gaokao_words() -> frozenset[str]:
    """Load entry words and phrase components from the local Gaokao list."""
    lines = [
        line.strip()
        for line in GAOKAO_PATH.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    words: set[str] = set()
    for index, line in enumerate(lines[:-1]):
        if lines[index + 1].startswith("[") and re.match(r"^[A-Za-z]", line):
            words.update(match.group(0).lower() for match in SINGLE_WORD_RE.finditer(line.lower()))
    return frozenset(words)


@lru_cache(maxsize=1)
def kaoyan_words() -> frozenset[str]:
    words = {
        line.strip().lower()
        for line in KAOYAN_PATH.read_text(encoding="utf-8").splitlines()
        if SINGLE_WORD_RE.fullmatch(line.strip().lower())
    }
    return frozenset(words)


@lru_cache(maxsize=1)
def common_american_20k() -> frozenset[str]:
    """Load the local top-20K adaptation of the SUBTLEX-US frequency data."""
    words = {
        line.strip().lower()
        for line in SUBTLEX_US_PATH.read_text(encoding="utf-8").splitlines()
        if SINGLE_WORD_RE.fullmatch(line.strip().lower())
    }
    return frozenset(words)


@lru_cache(maxsize=1)
def gre_words() -> frozenset[str]:
    words = {
        line.strip().lower()
        for line in GRE_PATH.read_text(encoding="utf-8-sig").splitlines()
        if SINGLE_WORD_RE.fullmatch(line.strip().lower())
    }
    return frozenset(words)


def _exact_vocabulary_tier(normalized: str) -> WordTier:
    if normalized in gaokao_words():
        return "high_school"
    if normalized in kaoyan_words():
        return "core"
    if normalized in common_american_20k():
        return "key"
    if normalized in gre_words():
        return "gre"
    return "rare"


def _lemma_candidates(word: str) -> tuple[str, ...]:
    candidates: list[str] = []

    def add(candidate: str) -> None:
        if len(candidate) > 1 and candidate != word and candidate not in candidates:
            candidates.append(candidate)

    if word.endswith("'s"):
        add(word[:-2])
    if contraction := CONTRACTION_FORMS.get(word):
        add(contraction)
    for ending in ("'re", "'ve", "'ll", "'d", "'m"):
        if word.endswith(ending):
            add(word[: -len(ending)])
    if word.endswith("n't"):
        add(word[:-3])
    if len(word) > 4 and word.endswith("ies"):
        add(f"{word[:-3]}y")
    if len(word) > 4 and word.endswith("ves"):
        add(f"{word[:-3]}f")
        add(f"{word[:-3]}fe")
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        add(word[:-1])
    if len(word) > 4 and word.endswith("es"):
        add(word[:-2])
    if len(word) > 5 and word.endswith("ing"):
        stem = word[:-3]
        add(f"{stem}e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            add(stem[:-1])
        add(stem)
    if len(word) > 4 and word.endswith("ied"):
        add(f"{word[:-3]}y")
    if len(word) > 4 and word.endswith("ed"):
        stem = word[:-2]
        add(f"{stem}e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            add(stem[:-1])
        add(stem)
    return tuple(candidates)


def match_vocabulary_tier(word: str) -> tuple[str, WordTier]:
    """Return the list entry and tier matched by a surface form."""
    normalized = word.strip().lower().replace("’", "'").replace("‘", "'")
    if not SINGLE_WORD_RE.fullmatch(normalized):
        return normalized, "rare"
    irregular = IRREGULAR_FORMS.get(normalized)
    if irregular:
        irregular_tier = _exact_vocabulary_tier(irregular)
        if irregular_tier != "rare":
            return irregular, irregular_tier
    exact_tier = _exact_vocabulary_tier(normalized)
    candidate_matches: list[tuple[str, WordTier]] = []
    for candidate in _lemma_candidates(normalized):
        candidate_lemma = IRREGULAR_FORMS.get(candidate, candidate)
        tier = _exact_vocabulary_tier(candidate_lemma)
        if tier != "rare":
            candidate_matches.append((candidate_lemma, tier))
    if exact_tier == "rare":
        return candidate_matches[0] if candidate_matches else (normalized, "rare")
    priority = {"high_school": 0, "core": 1, "key": 2, "gre": 3, "rare": 4}
    earlier_match = next(
        (match for match in candidate_matches if priority[match[1]] < priority[exact_tier]),
        None,
    )
    if earlier_match:
        return earlier_match
    return normalized, exact_tier


def vocabulary_tier(word: str) -> WordTier:
    return match_vocabulary_tier(word)[1]


def tier_importance(tier: WordTier) -> int:
    return {"high_school": 0, "core": 5, "key": 4, "gre": 3, "rare": 1}[tier]
