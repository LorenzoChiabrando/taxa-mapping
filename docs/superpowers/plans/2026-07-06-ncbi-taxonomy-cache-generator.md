# NCBI Taxonomy Cache Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone script that generates a Bacteria+Archaea NCBI-taxonomy cache, in the exact JSON schema the pipeline already consumes, from the offline NCBI taxdump — eliminating the Group A "stale taxonomy" black cases in the rescue stage.

**Architecture:** A pure-Python core module (`taxa_mapping/tools/taxdump_cache.py`) parses `nodes.dmp`/`names.dmp`/`merged.dmp`, filters to Bacteria (taxid `2`) + Archaea (taxid `2157`) by ancestry, assembles one record per taxon, and writes a `{ "TAX::<name>": [record], "IDS::<ids>": [record] }` dict. A thin CLI wrapper (`scripts/build_ncbi_cache.py`) handles arguments and taxdump acquisition. `NcbiRepository` and the scoring/rescue code are untouched; the new file is drop-in via `NCBI_CACHE_PATH`.

**Tech Stack:** Python 3 (stdlib: `json`, `tarfile`, `pathlib`, `argparse`), `requests` (already a project dependency, for the optional download), `pytest` (new dev-only dependency for tests).

## Global Constraints

- Runtime code uses **stdlib + `requests` only** — no new *runtime* dependency. `pytest` is dev-only, in `source/requirements-dev.txt`.
- Do **not** modify `taxa_mapping/infrastructure/ncbi_repository.py`, `taxa_mapping/core/ncbi_scoring.py`, or `taxa_mapping/core/rescue.py`. The generated file must be consumed by the existing code unchanged.
- Default clade roots: `{"2", "2157"}` (Bacteria, Archaea).
- Default output path: `source/data/ncbi_cache_full.json`. The existing `source/data/ncbi_cache.json` must remain untouched.
- Cache key rules: `TAX::<scientific name>` always wins over `TAX::<synonym>` on collision; among synonyms, first writer wins.
- All work happens under `source/`. Run tests with the project venv: `source/venv/bin/python -m pytest source/tests -v`.
- All commits end with the trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- The record schema and field mapping are defined in the spec: `docs/superpowers/specs/2026-07-06-ncbi-taxonomy-cache-generator-design.md`.

---

### Task 1: Test scaffolding & tools package skeleton

**Files:**
- Create: `source/requirements-dev.txt`
- Create: `source/taxa_mapping/tools/__init__.py`
- Create: `source/taxa_mapping/tools/taxdump_cache.py` (module docstring + constants only)
- Create: `source/tests/conftest.py` (sys.path + shared synthetic-taxdump fixture)
- Create: `source/tests/test_scaffolding.py` (smoke test)

**Interfaces:**
- Produces: importable module `taxa_mapping.tools.taxdump_cache` exposing constants `TAXDUMP_URL: str`, `DEFAULT_CLADES: set[str]`.
- Produces: pytest fixture `taxdump_dir` → `pathlib.Path` to a directory containing synthetic `nodes.dmp`, `names.dmp`, `merged.dmp`; and helper `_write_dmp(path, rows)`.

- [ ] **Step 1: Create the dev requirements file**

Create `source/requirements-dev.txt`:

```
pytest>=8.0
```

- [ ] **Step 2: Install pytest into the existing venv**

Run: `source/venv/bin/pip install -q -r source/requirements-dev.txt`
Expected: installs pytest; `source/venv/bin/python -m pytest --version` prints a version.

- [ ] **Step 3: Create the tools package**

Create `source/taxa_mapping/tools/__init__.py` (empty file).

Create `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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
```

- [ ] **Step 4: Create the shared test fixture**

Create `source/tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # make source/ importable

import pytest

# taxid, parent, rank
NODES = [
    ["1", "1", "no rank"],
    ["131567", "1", "no rank"],
    ["2", "131567", "superkingdom"],
    ["2157", "131567", "superkingdom"],
    ["2759", "131567", "superkingdom"],
    ["909656", "2", "genus"],
    ["821", "909656", "species"],
    ["2172", "2157", "genus"],
    ["2173", "2172", "species"],
    ["9606", "2759", "species"],
]
# taxid, name, unique, class
NAMES = [
    ["1", "root", "", "scientific name"],
    ["131567", "cellular organisms", "", "scientific name"],
    ["2", "Bacteria", "", "scientific name"],
    ["2157", "Archaea", "", "scientific name"],
    ["2759", "Eukaryota", "", "scientific name"],
    ["909656", "Phocaeicola", "", "scientific name"],
    ["821", "Phocaeicola vulgatus", "", "scientific name"],
    ["821", "Bacteroides vulgatus", "", "synonym"],
    ["821", "Bacteroides vulgatus (Eggerth and Gagnon 1933)", "", "authority"],
    ["2172", "Methanobrevibacter", "", "scientific name"],
    ["2173", "Methanobrevibacter smithii", "", "scientific name"],
    ["9606", "Homo sapiens", "", "scientific name"],
]
# old, new
MERGED = [
    ["76856", "821"],
]


def _write_dmp(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write("\t|\t".join(row) + "\t|\n")


@pytest.fixture
def taxdump_dir(tmp_path):
    d = tmp_path / "taxdump"
    d.mkdir()
    _write_dmp(d / "nodes.dmp", NODES)
    _write_dmp(d / "names.dmp", NAMES)
    _write_dmp(d / "merged.dmp", MERGED)
    return d
```

- [ ] **Step 5: Write the smoke test**

Create `source/tests/test_scaffolding.py`:

```python
from taxa_mapping.tools import taxdump_cache


def test_module_imports_and_constants():
    assert taxdump_cache.DEFAULT_CLADES == {"2", "2157"}
    assert taxdump_cache.TAXDUMP_URL.endswith("taxdump.tar.gz")


def test_taxdump_fixture_writes_dmp(taxdump_dir):
    assert (taxdump_dir / "nodes.dmp").exists()
    assert (taxdump_dir / "names.dmp").exists()
    assert (taxdump_dir / "merged.dmp").exists()
```

- [ ] **Step 6: Run the smoke test**

Run: `source/venv/bin/python -m pytest source/tests/test_scaffolding.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add source/requirements-dev.txt source/taxa_mapping/tools/ source/tests/
git commit -m "test: scaffold tools package and synthetic taxdump fixture

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `.dmp` row parser + `parse_nodes`

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_parse_nodes.py`

**Interfaces:**
- Produces: `_dmp_rows(path) -> Iterator[list[str]]` — yields fields split on `\t|\t`, trailing `\t|` removed.
- Produces: `parse_nodes(nodes_path) -> Dict[str, Tuple[str, str]]` mapping `taxid -> (parent_taxid, rank)`.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_parse_nodes.py`:

```python
from taxa_mapping.tools.taxdump_cache import parse_nodes


def test_parse_nodes_maps_parent_and_rank(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    assert nodes["821"] == ("909656", "species")
    assert nodes["909656"] == ("2", "genus")
    assert nodes["2"] == ("131567", "superkingdom")
    assert len(nodes) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_parse_nodes.py -v`
Expected: FAIL with `ImportError` / `cannot import name 'parse_nodes'`.

- [ ] **Step 3: Implement `_dmp_rows` and `parse_nodes`**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_parse_nodes.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_parse_nodes.py
git commit -m "feat: parse taxdump nodes.dmp into taxid->(parent,rank)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Clade filter — `compute_in_scope` + `ancestors_of_roots`

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_in_scope.py`

**Interfaces:**
- Consumes: `parse_nodes` output (`Dict[str, Tuple[str, str]]`).
- Produces: `compute_in_scope(nodes, clade_roots: Set[str]) -> Set[str]` — taxids whose ancestry reaches any clade root (roots themselves included).
- Produces: `ancestors_of_roots(nodes, clade_roots: Set[str]) -> Set[str]` — the ancestor taxids of the clade roots (used to keep their scientific names for lineage strings).

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_in_scope.py`:

```python
from taxa_mapping.tools.taxdump_cache import (
    parse_nodes,
    compute_in_scope,
    ancestors_of_roots,
)


def test_in_scope_keeps_bacteria_and_archaea_drops_eukaryote(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    scope = compute_in_scope(nodes, {"2", "2157"})
    assert {"2", "909656", "821"} <= scope        # Bacteria lineage
    assert {"2157", "2172", "2173"} <= scope      # Archaea lineage
    assert "9606" not in scope                     # eukaryote
    assert "2759" not in scope                     # Eukaryota root
    assert "131567" not in scope                   # cellular organisms (above clades)


def test_ancestors_of_roots(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    extra = ancestors_of_roots(nodes, {"2", "2157"})
    assert "131567" in extra   # cellular organisms
    assert "1" in extra        # root
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_in_scope.py -v`
Expected: FAIL with `cannot import name 'compute_in_scope'`.

- [ ] **Step 3: Implement the filter**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_in_scope.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_in_scope.py
git commit -m "feat: filter taxdump to Bacteria+Archaea by ancestry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `parse_names`

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_parse_names.py`

**Interfaces:**
- Consumes: a `capture` set of taxids (typically `in_scope | ancestors_of_roots`).
- Produces: `parse_names(names_path, capture: Set[str]) -> Tuple[Dict[str,str], Dict[str,Dict[str,List[str]]], Dict[str,List[str]]]` returning `(sci_name, alt, authority)` where `sci_name[taxid]=scientific name`, `alt[taxid][name_class]=[names]` for the four alt classes, `authority[taxid]=[author strings]`.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_parse_names.py`:

```python
from taxa_mapping.tools.taxdump_cache import parse_names


def test_parse_names_buckets(taxdump_dir):
    capture = {"821", "909656", "2", "131567"}
    sci, alt, authority = parse_names(taxdump_dir / "names.dmp", capture)
    assert sci["821"] == "Phocaeicola vulgatus"
    assert sci["909656"] == "Phocaeicola"
    assert alt["821"]["synonym"] == ["Bacteroides vulgatus"]
    assert authority["821"] == ["Bacteroides vulgatus (Eggerth and Gagnon 1933)"]


def test_parse_names_excludes_out_of_capture(taxdump_dir):
    capture = {"821"}
    sci, alt, authority = parse_names(taxdump_dir / "names.dmp", capture)
    assert "9606" not in sci
    assert "2173" not in sci
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_parse_names.py -v`
Expected: FAIL with `cannot import name 'parse_names'`.

- [ ] **Step 3: Implement `parse_names`**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_parse_names.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_parse_names.py
git commit -m "feat: parse taxdump names.dmp into scientific/alt/authority buckets

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `parse_merged`

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_parse_merged.py`

**Interfaces:**
- Consumes: `in_scope` set.
- Produces: `parse_merged(merged_path, in_scope: Set[str]) -> Dict[str, List[str]]` mapping `new_taxid -> [old_taxid, ...]`, restricted to in-scope new ids.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_parse_merged.py`:

```python
from taxa_mapping.tools.taxdump_cache import parse_merged


def test_parse_merged_maps_new_to_old(taxdump_dir):
    merged = parse_merged(taxdump_dir / "merged.dmp", {"821"})
    assert merged["821"] == ["76856"]


def test_parse_merged_excludes_out_of_scope(taxdump_dir):
    merged = parse_merged(taxdump_dir / "merged.dmp", {"999"})
    assert merged == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_parse_merged.py -v`
Expected: FAIL with `cannot import name 'parse_merged'`.

- [ ] **Step 3: Implement `parse_merged`**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
def parse_merged(merged_path, in_scope: Set[str]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    for row in _dmp_rows(Path(merged_path)):
        if len(row) < 2:
            continue
        old_id, new_id = row[0], row[1]
        if old_id and new_id in in_scope:
            merged.setdefault(new_id, []).append(old_id)
    return merged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_parse_merged.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_parse_merged.py
git commit -m "feat: parse taxdump merged.dmp into new->old taxids

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `build_lineage` + `build_record`

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_build_record.py`

**Interfaces:**
- Consumes: `nodes`, `sci_name`, `alt`, `authority`, `merged` maps from Tasks 2–5.
- Produces: `build_lineage(taxid, nodes, sci_name) -> List[dict]` — root→parent chain of `{"TaxId","ScientificName","Rank"}` (excludes the taxon itself and root `"1"`).
- Produces: `build_record(taxid, nodes, sci_name, alt, authority, merged) -> dict` — a record with keys `TaxId, ScientificName, ParentTaxId, Rank, OtherNames{Synonym,GenbankSynonym,EquivalentName,Includes,Name}, Lineage, LineageEx, AkaTaxIds, MergedTaxIds`.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_build_record.py`. It also feeds the record through the pipeline's own parser to prove compatibility.

```python
from taxa_mapping.tools.taxdump_cache import (
    parse_nodes, compute_in_scope, ancestors_of_roots, parse_names, parse_merged,
    build_lineage, build_record,
)
from taxa_mapping.core import ncbi_scoring


def _load(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    in_scope = compute_in_scope(nodes, {"2", "2157"})
    capture = in_scope | ancestors_of_roots(nodes, {"2", "2157"})
    sci, alt, authority = parse_names(taxdump_dir / "names.dmp", capture)
    merged = parse_merged(taxdump_dir / "merged.dmp", in_scope)
    return nodes, sci, alt, authority, merged


def test_build_lineage_root_to_parent(taxdump_dir):
    nodes, sci, alt, authority, merged = _load(taxdump_dir)
    lineage = build_lineage("821", nodes, sci)
    names = [e["ScientificName"] for e in lineage]
    assert names == ["cellular organisms", "Bacteria", "Phocaeicola"]
    genus = [e for e in lineage if e["Rank"] == "genus"]
    assert genus[0]["ScientificName"] == "Phocaeicola"


def test_build_record_roundtrips_through_parse_tax_record(taxdump_dir):
    nodes, sci, alt, authority, merged = _load(taxdump_dir)
    rec = build_record("821", nodes, sci, alt, authority, merged)
    assert rec["ScientificName"] == "Phocaeicola vulgatus"
    assert rec["Rank"] == "species"
    assert rec["OtherNames"]["Synonym"] == ["Bacteroides vulgatus"]
    assert rec["MergedTaxIds"] == ["76856"]

    info = ncbi_scoring.parse_tax_record(rec)
    assert info["canonical"] == "Phocaeicola vulgatus"
    assert info["rank"] == "species"
    assert "Phocaeicola" in info["lineage_genera"]
    assert "Bacteroides vulgatus" in info["synonyms"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_build_record.py -v`
Expected: FAIL with `cannot import name 'build_lineage'`.

- [ ] **Step 3: Implement `build_lineage` and `build_record`**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_build_record.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_build_record.py
git commit -m "feat: assemble taxdump records compatible with parse_tax_record

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: `build_cache` — TAX/synonym/IDS key indexing

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_build_cache.py`

**Interfaces:**
- Consumes: `records: Dict[str, dict]` (taxid -> record from `build_record`).
- Produces: `build_cache(records) -> Dict[str, List[dict]]` — keys `TAX::<scientific name>` (priority), `TAX::<synonym>` (only if key free), `IDS::<sorted,comma-joined merged ids>` (when `MergedTaxIds` non-empty). Each value is a one-element `[record]` list.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_build_cache.py`. The IDS test proves the key matches what the pipeline's `expand_with_aka_merged` reconstructs.

```python
from taxa_mapping.tools.taxdump_cache import build_cache
from taxa_mapping.core import ncbi_scoring


def _rec(taxid, sci, synonyms=None, merged=None):
    return {
        "TaxId": taxid,
        "ScientificName": sci,
        "ParentTaxId": "",
        "Rank": "species",
        "OtherNames": {
            "Synonym": synonyms or [],
            "GenbankSynonym": [],
            "EquivalentName": [],
            "Includes": [],
            "Name": [],
        },
        "Lineage": "",
        "LineageEx": [],
        "AkaTaxIds": [],
        "MergedTaxIds": merged or [],
    }


def test_scientific_and_synonym_keys():
    records = {"821": _rec("821", "Phocaeicola vulgatus", synonyms=["Bacteroides vulgatus"])}
    cache = build_cache(records)
    assert cache["TAX::Phocaeicola vulgatus"][0]["TaxId"] == "821"
    assert cache["TAX::Bacteroides vulgatus"][0]["TaxId"] == "821"


def test_scientific_name_wins_over_colliding_synonym():
    records = {
        "821": _rec("821", "Phocaeicola vulgatus"),
        "999": _rec("999", "Other species", synonyms=["Phocaeicola vulgatus"]),
    }
    cache = build_cache(records)
    # the scientific-name owner (821) must win the shared key
    assert cache["TAX::Phocaeicola vulgatus"][0]["TaxId"] == "821"


def test_ids_key_matches_expand_with_aka_merged():
    records = {"821": _rec("821", "Phocaeicola vulgatus", merged=["76856"])}
    cache = build_cache(records)
    assert "IDS::76856" in cache

    base = ncbi_scoring.parse_tax_record(records["821"])
    fetched = ncbi_scoring.cache_fetch_by_taxids(base["merged_taxids"], cache)
    assert fetched and fetched[0]["TaxId"] == "821"
    # expand must run without error and return the record's own synonym set
    expanded = ncbi_scoring.expand_with_aka_merged(base, cache)
    assert isinstance(expanded["synonyms"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_build_cache.py -v`
Expected: FAIL with `cannot import name 'build_cache'`.

- [ ] **Step 3: Implement `build_cache`**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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

    # 3. IDS:: keys for merged taxids (matches cache_fetch_by_taxids)
    for rec in records.values():
        merged = rec.get("MergedTaxIds") or []
        ids = sorted({str(x).strip() for x in merged if str(x).strip()})
        if ids:
            cache[f"IDS::{','.join(ids)}"] = [rec]

    return cache
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_build_cache.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_build_cache.py
git commit -m "feat: index taxdump records into TAX/synonym/IDS cache keys

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Taxdump acquisition — `resolve_taxdump`

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_resolve_taxdump.py`

**Interfaces:**
- Produces: `resolve_taxdump(taxdump: Optional[str], work_dir: Optional[str]) -> Path` — returns a directory containing the three `.dmp` files. Accepts a local extracted directory, a local `.tar.gz`, or (when `None`) downloads from `TAXDUMP_URL`.
- Produces internal helpers `_extract_tarball(archive, work) -> Path` and `_download(url, dest) -> None`.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_resolve_taxdump.py`. It covers the two offline paths (local dir, local tarball); the network download is not exercised in tests.

```python
import tarfile
from taxa_mapping.tools.taxdump_cache import resolve_taxdump, parse_nodes


def test_resolve_local_directory(taxdump_dir, tmp_path):
    resolved = resolve_taxdump(str(taxdump_dir), str(tmp_path / "work"))
    assert (resolved / "nodes.dmp").exists()
    assert parse_nodes(resolved / "nodes.dmp")["821"] == ("909656", "species")


def test_resolve_local_tarball(taxdump_dir, tmp_path):
    archive = tmp_path / "taxdump.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name in ("nodes.dmp", "names.dmp", "merged.dmp"):
            tf.add(taxdump_dir / name, arcname=name)
    resolved = resolve_taxdump(str(archive), str(tmp_path / "work"))
    assert (resolved / "names.dmp").exists()
    assert parse_nodes(resolved / "nodes.dmp")["2173"] == ("2172", "species")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_resolve_taxdump.py -v`
Expected: FAIL with `cannot import name 'resolve_taxdump'`.

- [ ] **Step 3: Implement acquisition**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
_DMP_MEMBERS = ("nodes.dmp", "names.dmp", "merged.dmp")


def _extract_tarball(archive: Path, work: Path) -> Path:
    dest = work / "extracted"
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            base = Path(member.name).name
            if base in _DMP_MEMBERS:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_resolve_taxdump.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_resolve_taxdump.py
git commit -m "feat: resolve taxdump from local dir, tarball, or NCBI download

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: `generate` orchestrator

**Files:**
- Modify: `source/taxa_mapping/tools/taxdump_cache.py`
- Create: `source/tests/test_generate.py`

**Interfaces:**
- Consumes: all functions from Tasks 2–8.
- Produces: `generate(taxdump: Optional[str], output: str, clades: Optional[Set[str]] = None, work_dir: Optional[str] = None) -> dict` — writes the cache JSON to `output` and returns stats `{"in_scope","records","tax_keys","synonym_keys","ids_keys","output","bytes"}`.

- [ ] **Step 1: Write the failing test**

Create `source/tests/test_generate.py`:

```python
import json
from taxa_mapping.tools.taxdump_cache import generate


def test_generate_writes_expected_keys(taxdump_dir, tmp_path):
    out = tmp_path / "ncbi_cache_full.json"
    stats = generate(str(taxdump_dir), str(out), {"2", "2157"}, str(tmp_path / "work"))
    assert out.exists()

    cache = json.loads(out.read_text(encoding="utf-8"))
    assert "TAX::Phocaeicola vulgatus" in cache        # bacterium (current name)
    assert "TAX::Bacteroides vulgatus" in cache         # synonym resolves
    assert "TAX::Methanobrevibacter smithii" in cache   # archaeon
    assert "TAX::Homo sapiens" not in cache             # eukaryote excluded
    assert "IDS::76856" in cache                         # merged id index

    assert stats["records"] >= 4
    assert stats["ids_keys"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source/venv/bin/python -m pytest source/tests/test_generate.py -v`
Expected: FAIL with `cannot import name 'generate'`.

- [ ] **Step 3: Implement `generate`**

Append to `source/taxa_mapping/tools/taxdump_cache.py`:

```python
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
        for t in in_scope
        if sci_name.get(t)
    }
    cache = build_cache(records)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    tax_keys = sum(1 for k in cache if k.startswith("TAX::"))
    ids_keys = sum(1 for k in cache if k.startswith("IDS::"))
    return {
        "in_scope": len(in_scope),
        "records": len(records),
        "tax_keys": tax_keys,
        "synonym_keys": tax_keys - len(records),
        "ids_keys": ids_keys,
        "output": str(out_path),
        "bytes": out_path.stat().st_size,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_generate.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add source/taxa_mapping/tools/taxdump_cache.py source/tests/test_generate.py
git commit -m "feat: orchestrate taxdump-to-cache generation with stats

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: CLI script + rescue end-to-end validation + README note

**Files:**
- Create: `source/scripts/build_ncbi_cache.py`
- Create: `source/tests/test_rescue_end_to_end.py`
- Modify: `README.md` (add a "Generating the NCBI taxonomy cache" section)

**Interfaces:**
- Consumes: `generate`, `DEFAULT_CLADES` from `taxa_mapping.tools.taxdump_cache`; `run_ncbi_rescue` from `taxa_mapping.core.rescue`.
- Produces: an executable CLI and a passing end-to-end test proving a stale-taxonomy taxon is no longer `black` when the pipeline reads the generated cache.

- [ ] **Step 1: Write the failing end-to-end test**

Create `source/tests/test_rescue_end_to_end.py`. It builds the cache from the synthetic taxdump, then runs the real `run_ncbi_rescue` against it.

```python
from taxa_mapping.tools.taxdump_cache import generate
from taxa_mapping.core.rescue import run_ncbi_rescue


def test_stale_taxon_not_black_with_generated_cache(taxdump_dir, tmp_path):
    cache_path = tmp_path / "ncbi_cache_full.json"
    generate(str(taxdump_dir), str(cache_path), {"2", "2157"}, str(tmp_path / "work"))

    # current name
    out = run_ncbi_rescue(
        [{"taxon": "Phocaeicola vulgatus", "mat_candidates_str": "Phocaeicola_vulgatus_ERR1"}],
        str(cache_path),
    )
    assert out[0]["final_color"] != "black"

    # old name resolves via synonym key
    out_old = run_ncbi_rescue(
        [{"taxon": "Bacteroides vulgatus", "mat_candidates_str": "Phocaeicola_vulgatus_ERR1"}],
        str(cache_path),
    )
    assert out_old[0]["final_color"] != "black"
```

- [ ] **Step 2: Run the end-to-end test**

Run: `source/venv/bin/python -m pytest source/tests/test_rescue_end_to_end.py -v`

This test imports only existing modules (`generate` + `run_ncbi_rescue`), so after Tasks 2–9 it is expected to **PASS immediately** — it is a regression/validation test guarding the generate→rescue integration, not a red-first test for this task. This task's new deliverables (the CLI script and README) are verified in Steps 4 and 6. Record the actual result; if it fails, fix the integration before continuing.

- [ ] **Step 3: Create the CLI script**

Create `source/scripts/build_ncbi_cache.py`:

```python
#!/usr/bin/env python3
"""CLI: build a Bacteria+Archaea NCBI-taxonomy cache from the NCBI taxdump."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # source/

from taxa_mapping.tools.taxdump_cache import generate, DEFAULT_CLADES

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "ncbi_cache_full.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Bacteria+Archaea NCBI taxonomy cache from the taxdump.",
    )
    parser.add_argument("--taxdump", default=None,
                        help="Path to an extracted taxdump dir or taxdump.tar.gz. "
                             "If omitted, downloads from NCBI.")
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT),
                        help="Output JSON path (default: source/data/ncbi_cache_full.json).")
    parser.add_argument("--clades", default=",".join(sorted(DEFAULT_CLADES)),
                        help="Comma-separated root taxids (default: 2,2157).")
    parser.add_argument("--work-dir", default=None,
                        help="Scratch dir for download/extraction.")
    args = parser.parse_args()

    clades = {c.strip() for c in args.clades.split(",") if c.strip()}
    stats = generate(args.taxdump, args.output, clades, args.work_dir)

    print("NCBI taxonomy cache built:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify the CLI runs against the synthetic taxdump**

Build a synthetic tarball and run the CLI end-to-end (no network):

```bash
source/venv/bin/python - <<'PY'
import tarfile, tempfile, subprocess, os
from pathlib import Path
import sys
sys.path.insert(0, "source/tests")
from conftest import NODES, NAMES, MERGED, _write_dmp
tmp = Path(tempfile.mkdtemp())
d = tmp / "td"; d.mkdir()
_write_dmp(d/"nodes.dmp", NODES); _write_dmp(d/"names.dmp", NAMES); _write_dmp(d/"merged.dmp", MERGED)
out = tmp / "cache.json"
subprocess.run(["source/venv/bin/python", "source/scripts/build_ncbi_cache.py",
                "--taxdump", str(d), "--output", str(out), "--work-dir", str(tmp/"work")], check=True)
print("EXISTS:", out.exists(), "BYTES:", out.stat().st_size)
PY
```

Expected: prints the stats block and `EXISTS: True` with a non-zero byte count.

- [ ] **Step 5: Run the end-to-end test to verify it passes**

Run: `source/venv/bin/python -m pytest source/tests/test_rescue_end_to_end.py -v`
Expected: 1 passed.

- [ ] **Step 6: Add a README section**

Add to `README.md` (under an appropriate heading) the following section:

```markdown
## Generating the NCBI taxonomy cache

Build a Bacteria + Archaea taxonomy cache from the offline NCBI taxdump
(fixes rescue "black" cases caused by stale taxonomy / renamed genera):

    # download the taxdump automatically and write source/data/ncbi_cache_full.json
    source/venv/bin/python source/scripts/build_ncbi_cache.py

    # or use an already-downloaded taxdump (dir of .dmp files or taxdump.tar.gz)
    source/venv/bin/python source/scripts/build_ncbi_cache.py --taxdump /path/to/taxdump.tar.gz

To use the generated cache, point `NCBI_CACHE_PATH` in `source/taxa_mapping/config.py`
at `data/ncbi_cache_full.json`. The original `ncbi_cache.json` is left untouched.

Note: this covers organisms that exist in NCBI. It does not resolve non-NCBI
placeholder IDs (e.g. `SGB…`/`GGB…` metagenomic bins), nor does it create missing
AGORA models.
```

- [ ] **Step 7: Run the full test suite**

Run: `source/venv/bin/python -m pytest source/tests -v`
Expected: all tests pass (Tasks 1–10).

- [ ] **Step 8: Commit**

```bash
git add source/scripts/build_ncbi_cache.py source/tests/test_rescue_end_to_end.py README.md
git commit -m "feat: add build_ncbi_cache CLI and rescue end-to-end validation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Validation (manual, optional — requires the real taxdump)

After the plan is implemented, validate against real data:

1. Generate the full cache (downloads ~60 MB, runs a few minutes, writes a hundreds-of-MB JSON):
   `source/venv/bin/python source/scripts/build_ncbi_cache.py`
2. Temporarily point `NCBI_CACHE_PATH` at `data/ncbi_cache_full.json`.
3. Re-run the problematic input:
   `./run.sh -i test_problematici/otu_O_taxa_input.csv -n full_cache_check`
4. Inspect `output/run_*/debug/03_rescue_process.csv`: the Group A stale-taxonomy taxa
   (`Phocaeicola vulgatus`, `Phocaeicola dorei`, `Agathobacter rectalis`,
   `Lachnospira eligens`, …) should no longer be `black`. SGB/GGB placeholders and the
   Group B taxa (`Dysosmobacter welbionis`, etc.) are expected to remain `black`.
