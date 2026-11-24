# Ported from calibre's utils/titlecase.py (GPL, Stuart Colband's
# smart_titlecase lineage; small-rules constants from the XML:UI spec),
# for the CalibreQuarry plugin host per the parity crosswalk.

"""calibre's titlecase: the title-case algorithm upstream's
check_title_case and the quality_check plugin compare against."""

from __future__ import annotations

import re

_SMALL = """a an and as at but by en for if in of on or the to v v. via vs vs."""
_SMALL_SET = {w for w in _SMALL.split() if w}
_IRISH = re.compile(r"([A-Z][A-Za-z0-9'`-]+)")
_NOSCAPE = re.compile(r"[\]\[({})]")

_SMALL_RE = re.compile(r"^(%s)$" % "|".join(_SMALL_SET), re.IGNORECASE)
_PUNCT_RE = re.compile(r"[,:;!\?\.\[\]]")
_DIGIT_RE = re.compile(r"[0-9]")
_ROMAN_RE = re.compile(
    r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})"
    "(I[VX]|V?I{0,3})$",
    re.IGNORECASE,
)


def _is_irish(name: str) -> bool:
    name = name.replace("'", "")
    return name in ("Mac", "Mc") or _IRISH.match(name)


def _capitalize_first(word: str) -> str:
    if not word:
        return word
    return word[0].upper() + word[1:]


def titlecase(text: str) -> str:
    """Ported verbatim in behavior: small words lower (unless first/last),
    roman numerals upper, Irish names preserved, first/last always capped."""
    if not text:
        return text
    result = []
    words = re.split(r"\s+", text.strip())
    for i, word in enumerate(words):
        if not word:
            continue
        if _DIGIT_RE.search(word):
            result.append(word)
            continue
        if _ROMAN_RE.match(word) and len(word) > 1:
            result.append(word.upper())
            continue
        core = word
        leading = ""
        while core and _NOSCAPE.match(core[0]):
            leading += core[0]
            core = core[1:]
        trailing = ""
        while core and _NOSCAPE.match(core[-1]):
            trailing = core[-1] + trailing
            core = core[:-1]
        if not core:
            result.append(word)
            continue
        if i != 0 and i != len(words) - 1 and _SMALL_RE.match(core):
            result.append(leading + core.lower() + trailing)
            continue
        if "-" in core:
            pieces = core.split("-")
            cased = "-".join(
                p if _SMALL_RE.match(p) else _capitalize_first(p) for p in pieces
            )
        else:
            cased = _capitalize_first(core)
        result.append(leading + cased + trailing)
    return " ".join(result)
