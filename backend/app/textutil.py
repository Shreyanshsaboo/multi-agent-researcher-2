"""Keyword helpers shared by passage selection and long-term recall."""

import re

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
STOPWORDS = frozenset(
    "the and for are but not you all any can had her was one our out has have this that with "
    "from they will what when who how why which their there about into more than then them "
    "these those some such only also just like over most other very been were does did "
    "find latest recent today summarize summarise research report tell show give".split()
)


def terms(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in STOPWORDS}


def similarity(a: str, b: str) -> tuple[float, int]:
    """Jaccard similarity of two texts' keywords, and how many keywords they share."""
    ta, tb = terms(a), terms(b)
    if not ta or not tb:
        return 0.0, 0
    shared = len(ta & tb)
    return shared / len(ta | tb), shared
