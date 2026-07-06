# NCBI Taxonomy Cache Generator — Design

- **Date:** 2026-07-06
- **Status:** Approved (pending spec review)
- **Author:** Lorenzo Chiabrando (with Claude)

## 1. Background & Problem

During the NCBI rescue stage (`source/taxa_mapping/core/rescue.py`), many taxa in
`test_problematici/` are classified `final_color = "black"`. Investigation showed the
`black` verdict (rescue.py lines ~205-213) requires **both** `top_score` and
`median_score` to be `<= 20` or missing. On `otu_O_taxa_input.csv`, 25/53 taxa are black,
splitting into two root causes:

- **Group A — taxon absent from the NCBI cache (21/25).** `NcbiRepository.fetch_records`
  is **cache-only** (never queries the network). If neither the name nor its normalized
  variants match a `TAX::` key, it returns `[]` → "No NCBI record" branch → `top_score=0`,
  `median_score=NaN` → black. The absence is mostly due to:
  - **Stale taxonomy / recent reclassifications** — e.g. `Phocaeicola vulgatus`,
    `Phocaeicola dorei`, `Agathobacter rectalis`, `Lachnospira eligens` are present in the
    cache only under **old names** (`Bacteroides vulgatus`, `Bacteroides dorei`,
    `Eubacterium rectale`, `Eubacterium eligens`). The cache was built from an older NCBI
    snapshot; the input uses current genus names.
  - **Non-NCBI placeholder IDs** — e.g. `Faecalibacterium SGB15346`, `GGB9699 SGB15216`,
    `Clostridium sp AM22 11AC` (MGnify/SGB metagenomic bins, never NCBI scientific names).
- **Group B — taxon present in cache but no AGORA model (4/25).** e.g.
  `Dysosmobacter welbionis`, `Lawsonibacter asaccharolyticus`, `Vescimonas coprocola`,
  `Pusillibacter faecalis` have a taxid and canonical name, but every candidate model scores
  only 20 ("weak/partial token overlap") because AGORA has no reconstruction for them
  (0 models contain e.g. "Dysosmobacter"). `top=20`, `median=20` → black.

## 2. Goal & Non-Goals

**Goal:** Provide a standalone script that generates an NCBI-taxonomy cache in the **exact
same JSON format** the pipeline already consumes, covering the full **Bacteria + Archaea**
domain from the offline NCBI taxdump. This eliminates the Group A "stale taxonomy" black
cases and makes old→new name resolution work.

**Non-goals (explicit):**
- Does **not** fix non-NCBI placeholder IDs (SGB/GGB) — a different data source
  (GTDB/MGnify) would be required.
- Does **not** fix Group B (missing AGORA models) — a model-availability problem, unrelated
  to the cache.
- Does **not** change `NcbiRepository` or the scoring/rescue logic. The new file is a
  drop-in replacement selected via `NCBI_CACHE_PATH`.

**Expected impact on `otu_O`:** ~17 of the 25 black taxa (the Group A stale-taxonomy subset)
become non-black; SGB/GGB and Group B remain black by design.

## 3. Chosen Approach

Parse the **NCBI taxdump** (`taxdump.tar.gz`: `nodes.dmp`, `names.dmp`, `merged.dmp`),
filter to Bacteria (taxid `2`) + Archaea (taxid `2157`) by ancestry, and emit one JSON
record per taxon in the current cache schema. Pure-Python `.dmp` parsing — **no new
dependency**. Offline and reproducible.

Rejected alternatives:
- **Entrez efetch bulk** (how the current cache was built): ~1M rate-limited calls = days,
  fragile. Kept only conceptually for incremental top-ups; not used here.
- **Taxdump → SQLite indexed store + repository change**: scales to the whole tree without
  loading into RAM, but breaks the "same JSON style" compatibility and changes
  `NcbiRepository`. Out of scope; possible future evolution.

## 4. Data Source

`taxdump.tar.gz` from NCBI FTP (`https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz`).
Relevant members:

- **`nodes.dmp`** — `tax_id | parent_tax_id | rank | ...` (also genetic code, division; unused).
- **`names.dmp`** — `tax_id | name_txt | unique_name | name_class |`. Relevant name classes:
  `scientific name`, `synonym`, `genbank synonym`, `equivalent name`, `includes`, `authority`.
- **`merged.dmp`** — `old_tax_id | new_tax_id |` (old ids merged into a current taxon).

Acquisition: script uses `--taxdump <path>` if provided (a directory of extracted `.dmp`
files or the `.tar.gz`); otherwise downloads the archive to a local cache dir and extracts
it. Download failure is a hard error with a clear message (offer the `--taxdump` flag).

## 5. Clade Filter (Bacteria + Archaea)

1. Parse `nodes.dmp` into `taxid -> (parent_taxid, rank)`.
2. For each taxid, determine membership by walking parents up to the root; a taxid is
   **in scope** if `2` or `2157` appears in its ancestor chain. Memoize ancestor resolution
   to keep this near-linear.
3. Only in-scope taxids get records and name lookups. (`nodes.dmp` for all life is parsed to
   build the parent map, but only Bacteria+Archaea are materialized as records.)

## 6. Output Record Schema

Identical to the fields the pipeline reads (`parse_tax_record`, `build_name_pool`,
`expand_with_aka_merged`). Unused efetch fields (`Division`, `GeneticCode`,
`MitoGeneticCode`, `CreateDate/UpdateDate/PubDate`) are omitted.

```json
{
  "TaxId": "821",
  "ScientificName": "Phocaeicola vulgatus",
  "ParentTaxId": "909656",
  "Rank": "species",
  "OtherNames": {
    "Synonym": ["Bacteroides vulgatus"],
    "GenbankSynonym": [],
    "EquivalentName": [],
    "Includes": [],
    "Name": [{"ClassCDE": "authority", "DispName": "Bacteroides vulgatus (Eggerth and Gagnon 1933) ..."}]
  },
  "Lineage": "cellular organisms; Bacteria; ...; Phocaeicola",
  "LineageEx": [
    {"TaxId": "131567", "ScientificName": "cellular organisms", "Rank": "no rank"},
    {"TaxId": "2", "ScientificName": "Bacteria", "Rank": "domain"},
    {"TaxId": "909656", "ScientificName": "Phocaeicola", "Rank": "genus"}
  ],
  "AkaTaxIds": [],
  "MergedTaxIds": ["76856"]
}
```

Field mapping from taxdump:
- `ScientificName`, `Rank`, `ParentTaxId` ← `nodes.dmp` + `names.dmp` (scientific name class).
- `OtherNames.Synonym` ← `synonym`; `GenbankSynonym` ← `genbank synonym`;
  `EquivalentName` ← `equivalent name`; `Includes` ← `includes`;
  `OtherNames.Name` ← `authority` names as `{ClassCDE:"authority", DispName:<name>}`.
- `LineageEx` ← ancestor chain (root→…→parent) as `{TaxId, ScientificName, Rank}`;
  `Lineage` ← `"; "`-joined scientific names of that chain.
  Note: the scorer's `lineage_genera` derive from entries with `Rank == "genus"`.
- `AkaTaxIds` ← `[]` (no taxdump equivalent).
- `MergedTaxIds` ← sorted list of old ids from `merged.dmp` that merged into this taxid.

## 7. Key Indexing

Top-level cache keys, matching `NcbiRepository`:

- **`TAX::<scientific name>` → `[record]`** for every in-scope taxon.
- **`TAX::<alt name>` → `[record]`** for every alternate name (synonym, genbank synonym,
  equivalent name, includes) of that record, enabling old→new resolution
  (`Bacteroides vulgatus` resolves to the `Phocaeicola vulgatus` record).
  **Precedence:** scientific-name keys always win. A synonym key is only written if that key
  is not already occupied by a scientific name. Synonym-vs-synonym collisions keep the first
  writer (documented as a known limitation; see §11).
- **`IDS::<sorted,comma-joined merged ids>` → `[record]`** for every record whose
  `MergedTaxIds` is non-empty. This is the exact key `expand_with_aka_merged` →
  `cache_fetch_by_taxids` reconstructs from `aka_taxids (empty) + merged_taxids`, so the
  merged ids resolve back to the current record and its synonyms are re-collected coherently.
  Records with empty `MergedTaxIds` produce no `IDS::` key (the function returns early).

## 8. Component & CLI

Single standalone generator, invoked manually — it does **not** run as part of the pipeline.

- **Path:** `source/scripts/build_ncbi_cache.py`
- **No new dependencies** (stdlib only: `tarfile`, `urllib`, `json`, `argparse`, `pathlib`).
- **CLI:**
  - `--taxdump <path>` — extracted dir or `.tar.gz` (optional; else download).
  - `--output <path>` — default `source/data/ncbi_cache_full.json`.
  - `--clades <taxids>` — default `2,2157` (Bacteria, Archaea).
  - `--work-dir <path>` — download/extract scratch dir.
- Emits a summary: taxa in scope, records written, TAX/synonym/IDS key counts, output size.

## 9. Algorithm

1. Acquire + extract taxdump.
2. Parse `nodes.dmp` → `parent`, `rank` maps (all life).
3. Compute in-scope taxid set via memoized ancestry to `{2, 2157}`.
4. Parse `names.dmp` (single pass), bucketing names by `(taxid, name_class)` for in-scope ids;
   capture scientific name separately.
5. Parse `merged.dmp` → `new_taxid -> [old ids]`, restricted to in-scope new ids.
6. For each in-scope taxid: build `LineageEx`/`Lineage` from the parent chain, assemble the
   record (§6).
7. Build the key map (§7): TAX scientific keys first, then synonym keys (respecting
   precedence), then IDS keys.
8. Write JSON to `--output`; print summary.

## 10. Testing (TDD)

**Unit tests** on tiny synthetic `.dmp` fixtures (a handful of taxa incl. Bacteria, Archaea,
one out-of-scope eukaryote, one synonym, one merged id):
- Clade filter keeps Bacteria/Archaea, drops the eukaryote.
- Record schema round-trips through `parse_tax_record` (canonical, rank, synonyms).
- `lineage_genera` extracted correctly (genus-ranked ancestor present).
- Synonym key resolves to the scientific-name record; scientific precedence on collision.
- `IDS::` key matches what `cache_fetch_by_taxids` builds; `expand_with_aka_merged` returns
  the record.

**End-to-end validation:** regenerate on a real (or reduced) taxdump, point
`NCBI_CACHE_PATH` at `ncbi_cache_full.json`, re-run `otu_O_taxa_input.csv`, and confirm the
Group A stale-taxonomy taxa (Phocaeicola vulgatus/dorei, Agathobacter rectalis,
Lachnospira eligens, …) are no longer `black`; SGB/GGB and Group B remain black.

## 11. Risks & Edge Cases

- **Memory/runtime:** parsing all of `nodes.dmp`/`names.dmp` holds several large dicts in RAM
  (peak ~2-4 GB) and runs a few minutes. Acceptable for an offline one-off. If it proves too
  heavy, the ancestry pass can be streamed, but not planned initially.
- **Output size:** Bacteria+Archaea with full lineage is expected in the hundreds-of-MB range
  (JSON). Loadable as a dict, consistent with the existing repository design.
- **Homonyms / synonym collisions:** the same alt-name may map to multiple taxa. Scientific
  names always win; among synonyms, first writer wins. Documented limitation; a future
  improvement could disambiguate by lineage or keep a list per key.
- **Download availability:** environments without NCBI FTP access must pass `--taxdump`.
- **Taxonomy drift:** the cache reflects the taxdump snapshot at generation time; regenerate
  periodically to stay current.

## 12. Compatibility & Rollout

- New file `source/data/ncbi_cache_full.json`; original `ncbi_cache.json` untouched.
- Switch by setting `NCBI_CACHE_PATH` (config.py) to the new file when ready; trivially
  reversible for A/B comparison.
