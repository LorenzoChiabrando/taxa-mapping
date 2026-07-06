"""Build an NCBI-taxonomy cache (same JSON schema the pipeline consumes) from the
offline NCBI taxdump, scoped to Bacteria + Archaea.

Pure stdlib + `requests` (already a project dependency) for the optional download.
See docs/superpowers/specs/2026-07-06-ncbi-taxonomy-cache-generator-design.md.
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
DEFAULT_CLADES: Set[str] = {"2", "2157"}  # Bacteria, Archaea

# name classes kept from names.dmp
_ALT_CLASSES = ("synonym", "genbank synonym", "equivalent name", "includes")

# name class -> OtherNames dict key
_OTHERNAMES_MAP = {
    "synonym": "Synonym",
    "genbank synonym": "GenbankSynonym",
    "equivalent name": "EquivalentName",
    "includes": "Includes",
}
