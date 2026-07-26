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


def vocabulary_tier(word: str) -> WordTier:
    normalized = word.strip().lower()
    if normalized in gaokao_words():
        return "high_school"
    if normalized in kaoyan_words():
        return "core"
    if normalized in common_american_20k():
        return "key"
    if normalized in gre_words():
        return "gre"
    return "rare"


def tier_importance(tier: WordTier) -> int:
    return {"high_school": 0, "core": 5, "key": 4, "gre": 3, "rare": 1}[tier]
