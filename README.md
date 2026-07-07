# Taxa Mapping — Local Pipeline

Maps microbial taxa names to AGORA model identifiers using Jaccard matching followed by an NCBI-assisted rescue stage.

---

## Requirements

- Python ≥ 3.10

All Python dependencies (including `plotly` and `kaleido` for `--plots`) are managed automatically by `run.sh` via a local virtual environment (`source/venv/`).

<!--
### R plots (disabled — work in progress)
R + ggplot2 + patchwork + scales are required for the R-based QC panels (Panel A, B).
```r
install.packages(c("tidyverse", "ggplot2", "patchwork", "scales", "ggalluvial"))
```
-->

---

## Input Format

A CSV file with a `taxa_name` column (also accepted: `taxon`, `name`, `organism`, `species`).

```
taxa_name
Akkermansia muciniphila ATCC BAA 835
Alistipes onderdonkii DSM 19147
...
```

---

## Usage

```bash
# Basic run
./run.sh --input input/multiple_sclerosis.csv

# Named run
./run.sh --input input/multiple_sclerosis.csv --name multiple_sclerosis

# With PDF report
./run.sh --input input/multiple_sclerosis.csv --name multiple_sclerosis --report

# With PDF report and plots
./run.sh --input input/multiple_sclerosis.csv --name multiple_sclerosis --report --plots
```

| Flag | Short | Default | Description |
|---|---|---|---|
| `--input` | `-i` | *(required)* | Path to the input CSV file. |
| `--output` | `-o` | `./output` | Base output directory. |
| `--name` | `-n` | *(empty)* | Label appended to the run directory name. |
| `--report` | — | off | Generate a PDF debug report. |
| `--plots` | — | off | Generate Sankey flow plot (requires `plotly` + `kaleido`, auto-installed). |

---

## Output

Each run writes to `output/run_TIMESTAMP_NAME/`:

```
debug/
  00_input.csv              # Cleaned names
  01_jaccard_raw.csv        # Jaccard scores and candidates
  02_filtering_stats.json   # Band breakdown
  02_rescue_candidates.csv  # Taxa sent to NCBI rescue
  03_rescue_process.csv     # NCBI scoring details
results/
  final_mapping.csv
  mapping_report.json
debug_report.pdf            # (--report only)
plots/                      # (--plots only)
```

### Status codes

| Status | Meaning |
|---|---|
| `unambiguous` | Unique high-confidence Jaccard match. |
| `high_similarity` | Strong match confirmed by NCBI rescue. |
| `near_tier` | Plausible match with residual ambiguity. |
| `low_similarity` | Weak match; manual review recommended. |
| `no_correspondence` | No suitable AGORA model found. |

---

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
