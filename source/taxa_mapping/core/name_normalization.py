"""Taxon-name normalization shared by the cache builder and the cache resolver."""

import re

_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")
_BARE_AUTHORSHIP_RE = re.compile(r"\s+\bex\b\s+.*$", flags=re.IGNORECASE)
_CANDIDATUS_RE = re.compile(r"^\s*Candidatus\s+", flags=re.IGNORECASE)
_INFRASPECIFIC_RE = re.compile(
    r"\b(subsp\.?|ssp\.?|subspecies|strain|pv\.?|pathovar|serovar|biovar|var\.?|variant|f\.?|forma)\b",
    flags=re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[\[\]\(\)\{\}:;,\|]+")
_WS_RE = re.compile(r"\s+")


def normalize_species_key(name: str) -> str:
    if not name:
        return ""
    s = _WS_RE.sub(" ", str(name)).strip()
    s = _PAREN_RE.sub(" ", s)
    s = _BARE_AUTHORSHIP_RE.sub("", s)
    s = _CANDIDATUS_RE.sub("", s)
    m = _INFRASPECIFIC_RE.search(s)
    if m:
        s = s[:m.start()]
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s
