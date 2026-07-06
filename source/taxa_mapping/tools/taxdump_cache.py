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


def _dmp_rows(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.endswith("\t|"):
                line = line[:-2]
            yield line.split("\t|\t")


def parse_nodes(nodes_path) -> Dict[str, Tuple[str, str]]:
    nodes: Dict[str, Tuple[str, str]] = {}
    for row in _dmp_rows(Path(nodes_path)):
        if len(row) < 3 or not row[0]:
            continue
        nodes[row[0]] = (row[1], row[2])
    return nodes


def compute_in_scope(nodes: Dict[str, Tuple[str, str]], clade_roots: Set[str]) -> Set[str]:
    memo: Dict[str, bool] = {}

    def in_scope(taxid: str) -> bool:
        stack: List[str] = []
        cur = taxid
        result = False
        while True:
            if cur in memo:
                result = memo[cur]
                break
            if cur in clade_roots:
                result = True
                break
            parent = nodes.get(cur, (cur, ""))[0]
            if not parent or parent == cur or parent not in nodes:
                result = False
                break
            stack.append(cur)
            cur = parent
        for t in stack:
            memo[t] = result
        memo[taxid] = result
        return result

    return {t for t in nodes if in_scope(t)}


def ancestors_of_roots(nodes: Dict[str, Tuple[str, str]], clade_roots: Set[str]) -> Set[str]:
    extra: Set[str] = set()
    for root in clade_roots:
        cur = root
        while cur in nodes:
            parent = nodes[cur][0]
            if not parent or parent == cur:
                break
            extra.add(parent)
            cur = parent
    return extra
