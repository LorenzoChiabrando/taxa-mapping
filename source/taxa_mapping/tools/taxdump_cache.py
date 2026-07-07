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

from ..core.name_normalization import normalize_species_key

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


def parse_names(names_path, capture: Set[str]):
    sci_name: Dict[str, str] = {}
    alt: Dict[str, Dict[str, List[str]]] = {}
    authority: Dict[str, List[str]] = {}
    for row in _dmp_rows(Path(names_path)):
        if len(row) < 4 or row[0] not in capture:
            continue
        taxid, name, name_class = row[0], row[1], row[3]
        if name_class == "scientific name":
            sci_name[taxid] = name
        elif name_class in _ALT_CLASSES:
            alt.setdefault(taxid, {}).setdefault(name_class, []).append(name)
        elif name_class == "authority":
            authority.setdefault(taxid, []).append(name)
    return sci_name, alt, authority


def parse_merged(merged_path, in_scope: Set[str]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    for row in _dmp_rows(Path(merged_path)):
        if len(row) < 2:
            continue
        old_id, new_id = row[0], row[1]
        if old_id and new_id in in_scope:
            merged.setdefault(new_id, []).append(old_id)
    return merged


def build_lineage(taxid: str, nodes: Dict[str, Tuple[str, str]], sci_name: Dict[str, str]) -> List[dict]:
    chain: List[dict] = []
    cur = nodes.get(taxid, ("", ""))[0]  # start at parent
    seen: Set[str] = set()
    while cur and cur in nodes and cur != "1" and cur not in seen:
        seen.add(cur)
        parent, rank = nodes[cur]
        chain.append({
            "TaxId": cur,
            "ScientificName": sci_name.get(cur, ""),
            "Rank": rank,
        })
        if parent == cur:
            break
        cur = parent
    chain.reverse()
    return chain


def build_record(taxid, nodes, sci_name, alt, authority, merged) -> dict:
    parent, rank = nodes.get(taxid, ("", ""))
    other: Dict[str, object] = {
        "Synonym": [],
        "GenbankSynonym": [],
        "EquivalentName": [],
        "Includes": [],
        "Name": [],
    }
    for cls, names in (alt.get(taxid) or {}).items():
        key = _OTHERNAMES_MAP.get(cls)
        if key:
            other[key] = list(names)
    for auth in (authority.get(taxid) or []):
        other["Name"].append({"ClassCDE": "authority", "DispName": auth})

    lineage_ex = build_lineage(taxid, nodes, sci_name)
    lineage_str = "; ".join(e["ScientificName"] for e in lineage_ex if e["ScientificName"])
    merged_ids = sorted(set(merged.get(taxid, [])))

    return {
        "TaxId": taxid,
        "ScientificName": sci_name.get(taxid, ""),
        "ParentTaxId": parent,
        "Rank": rank,
        "OtherNames": other,
        "Lineage": lineage_str,
        "LineageEx": lineage_ex,
        "AkaTaxIds": [],
        "MergedTaxIds": merged_ids,
    }


def build_cache(records: Dict[str, dict]) -> Dict[str, List[dict]]:
    cache: Dict[str, List[dict]] = {}

    # 1. scientific-name keys (highest priority)
    for rec in records.values():
        sci = rec.get("ScientificName")
        if sci:
            cache[f"TAX::{sci}"] = [rec]

    # 2. synonym keys — only if the key is not already a scientific-name key
    for rec in records.values():
        other = rec.get("OtherNames", {})
        alt_names: List[str] = []
        for k in ("Synonym", "GenbankSynonym", "EquivalentName", "Includes"):
            alt_names.extend(other.get(k, []))
        for name in alt_names:
            if not name:
                continue
            key = f"TAX::{name}"
            if key not in cache:
                cache[key] = [rec]

    # 2b. clean-binomial alias keys for authored names — only if the key is not
    #     already a scientific-name or synonym key (lowest taxid wins)
    def _taxid_sort_key(rec):
        t = str(rec.get("TaxId", ""))
        return (0, int(t)) if t.isdigit() else (1, t)

    for rec in sorted(records.values(), key=_taxid_sort_key):
        sci = rec.get("ScientificName")
        if not sci:
            continue
        clean = normalize_species_key(sci)
        if not clean or clean == sci or len(clean.split()) < 2:
            continue
        key = f"TAX::{clean}"
        if key not in cache:
            cache[key] = [rec]

    # 3. IDS:: keys for merged taxids (matches cache_fetch_by_taxids)
    for rec in records.values():
        merged = rec.get("MergedTaxIds") or []
        ids = sorted({str(x).strip() for x in merged if str(x).strip()})
        if ids:
            cache[f"IDS::{','.join(ids)}"] = [rec]

    return cache


_DMP_MEMBERS = ("nodes.dmp", "names.dmp", "merged.dmp")


def _extract_tarball(archive: Path, work: Path) -> Path:
    dest = work / "extracted"
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            base = Path(member.name).name
            if base in _DMP_MEMBERS and member.isfile():
                member.name = base  # flatten any leading path
                tf.extract(member, dest)
    return dest


def _download(url: str, dest: Path) -> None:
    import requests

    with requests.get(url, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)


def resolve_taxdump(taxdump: Optional[str], work_dir: Optional[str]) -> Path:
    work = Path(work_dir) if work_dir else Path.cwd() / ".taxdump_work"
    if taxdump:
        p = Path(taxdump)
        if p.is_dir():
            return p
        if p.is_file() and p.name.endswith((".tar.gz", ".tgz")):
            return _extract_tarball(p, work)
        raise FileNotFoundError(f"taxdump path not found or unsupported: {taxdump}")
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "taxdump.tar.gz"
    _download(TAXDUMP_URL, archive)
    return _extract_tarball(archive, work)


def generate(taxdump: Optional[str], output: str,
             clades: Optional[Set[str]] = None, work_dir: Optional[str] = None) -> dict:
    clade_roots = set(clades) if clades else set(DEFAULT_CLADES)
    dmp_dir = resolve_taxdump(taxdump, work_dir)

    nodes = parse_nodes(dmp_dir / "nodes.dmp")
    in_scope = compute_in_scope(nodes, clade_roots)
    capture = in_scope | ancestors_of_roots(nodes, clade_roots)
    sci_name, alt, authority = parse_names(dmp_dir / "names.dmp", capture)
    merged = parse_merged(dmp_dir / "merged.dmp", in_scope)

    records = {
        t: build_record(t, nodes, sci_name, alt, authority, merged)
        for t in sorted(in_scope)
        if sci_name.get(t)
    }
    cache = build_cache(records)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)

    tax_keys = sum(1 for k in cache if k.startswith("TAX::"))
    ids_keys = sum(1 for k in cache if k.startswith("IDS::"))
    sci_keys = len({r["ScientificName"] for r in records.values() if r["ScientificName"]})
    return {
        "in_scope": len(in_scope),
        "records": len(records),
        "tax_keys": tax_keys,
        "synonym_keys": tax_keys - sci_keys,
        "ids_keys": ids_keys,
        "output": str(out_path),
        "bytes": out_path.stat().st_size,
    }
