"""Text helpers: sentence segmentation and whitespace-insensitive span matching."""
import re

_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def sentences(text: str) -> list[str]:
    parts = (_BULLET.sub("", p).strip() for p in _SPLIT.split(text))
    return [p for p in parts if len(p) > 1]


def contains(text: str, span: str) -> bool:
    return bool(span.strip()) and norm(span) in norm(text)
