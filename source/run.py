#!/usr/bin/env python3
"""
Taxa Mapping - Local Version
============================
"""
import sys
import argparse
import logging
import json
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from taxa_mapping.config import settings
from taxa_mapping.core.cleaning  import clean_taxa_names
from taxa_mapping.core.matching  import run_jaccard_matching
from taxa_mapping.core.filtering import get_candidates_for_rescue
from taxa_mapping.core.rescue    import run_ncbi_rescue
from taxa_mapping.core.assembly  import assemble_report
from taxa_mapping.schemas.report import MappingStatus

# Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [DEBUG] - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_pipeline(input_csv: str, output_base_dir: str, generate_report: bool = False, generate_plots: bool = False, run_name: str = "") -> None:

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id      = f"{run_name}_{timestamp}" if run_name else timestamp
    folder_name = f"run_{timestamp}_{run_name}" if run_name else f"run_{timestamp}"
    run_dir     = Path(output_base_dir) / folder_name
    debug_dir   = run_dir / "debug"
    results_dir = run_dir / "results"

    debug_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    _banner(f"JOB {job_id}")
    logger.info(f"Input  : {input_csv}")
    logger.info(f"Output : {run_dir}")
    logger.info(f"Models : {settings.AGORA_MODELS_PATH}")
    logger.info(f"NCBI   : {settings.NCBI_CACHE_PATH}")

    # 1. Load 
    input_path = Path(input_csv)
    if not input_path.exists():
        logger.error(f"File not found: {input_path}")
        sys.exit(1)

    df = pd.read_csv(input_path)


    target_col = df.columns[0]
    for col in ["taxa_name", "taxon", "name", "organism", "species"]:
        if col in df.columns:
            target_col = col
            break


    abundance_col = None
    for col in ["abundance", "relative_abundance", "rel_abundance", "count", "value", "proportion"]:
        if col in df.columns:
            abundance_col = col
            break

    raw_names = df[target_col].astype(str).tolist()

    if abundance_col:
        logger.info(f"Abundance column: '{abundance_col}'")
        abundances    = pd.to_numeric(df[abundance_col], errors="coerce").fillna(0.0).tolist()
        abundance_map = dict(zip(raw_names, abundances))
    else:
        abundance_map = {name: None for name in raw_names}

    logger.info(f"Loaded {len(raw_names)} taxa from column '{target_col}'")

    #  2. Cleaning 
    _phase("1/4 — Cleaning")
    cleaned_names = clean_taxa_names(raw_names)

    _save(
        pd.DataFrame({"taxa_name": raw_names, "taxon": cleaned_names}),
        debug_dir / "00_input.csv",
        "debug/00_input.csv",
    )

    #  3. Jaccard Matching 
    _phase("2/4 — Jaccard Matching")
    jaccard_results = run_jaccard_matching(
        taxa_list=cleaned_names,
        raw_taxa_list=raw_names,
        models_csv_path=settings.AGORA_MODELS_PATH,
        abundance_map=abundance_map,
        n_jobs=settings.N_JOBS,
    )

    df_jaccard = pd.DataFrame(jaccard_results)
    _save(df_jaccard, debug_dir / "01_jaccard_raw.csv", "debug/01_jaccard_raw.csv")

    # 3.5 Filtering 
    _phase("2.5/4 — Filtering")
    rescue_candidates = get_candidates_for_rescue(jaccard_results)

    if "bands" in df_jaccard.columns:
        total         = len(df_jaccard)
        auto_accepted = int((df_jaccard["bands"] == "auto-accept").sum())
        need_rescue   = total - auto_accepted
        pct           = round(need_rescue / total * 100, 1) if total else 0.0
        breakdown     = df_jaccard[df_jaccard["bands"] != "auto-accept"]["bands"].value_counts().to_dict()

        stats = {
            "total_taxa":      total,
            "auto_accepted":   auto_accepted,
            "need_rescue":     need_rescue,
            "need_rescue_pct": pct,
            "breakdown":       breakdown,
        }
        stats_path = debug_dir / "02_filtering_stats.json"
        stats_path.write_text(json.dumps(stats, indent=2))
        logger.info(f"[DEBUG] Saved: debug/02_filtering_stats.json")
        logger.info(f"        Auto-accepted: {auto_accepted}/{total}  —  Rescue: {need_rescue} ({pct}%)")
        logger.info(f"        Breakdown: {breakdown}")

        if rescue_candidates:
            _save(pd.DataFrame(rescue_candidates), debug_dir / "02_rescue_candidates.csv", "debug/02_rescue_candidates.csv")

    #  4. NCBI Rescue 
    final_results = jaccard_results

    if not rescue_candidates:
        _phase("3/4 — NCBI Rescue: SKIPPED (all auto-accepted)")
    else:
        _phase(f"3/4 — NCBI Rescue ({len(rescue_candidates)} candidates)")

        rescued_items = run_ncbi_rescue(
            candidates=rescue_candidates,
            ncbi_cache_path=settings.NCBI_CACHE_PATH,
        )

        rescue_map    = {item["taxon"]: item for item in rescued_items}
        final_results = [rescue_map.get(item["taxon"], item) for item in jaccard_results]

        df_rescued = pd.DataFrame(rescued_items)
        _save(df_rescued, debug_dir / "03_rescue_process.csv", "debug/03_rescue_process.csv")

        if "final_band" in df_rescued.columns:
            logger.info(f"        Outcomes: {df_rescued['final_band'].value_counts().to_dict()}")

    # 5. Assembly 
    _phase("4/4 — Assembly report")

    _save(pd.DataFrame(final_results), results_dir / "final_mapping.csv", "results/final_mapping.csv")

    report      = assemble_report(job_id, final_results)
    report_json = report.to_json()
    (results_dir / "mapping_report.json").write_text(report_json, encoding="utf-8")
    logger.info(f"[RESULT] Saved: results/mapping_report.json")

    # Summary 
    counts = {s.name: 0 for s in MappingStatus}
    for item in report.results:
        for s in MappingStatus:
            if s.value == item.status:
                counts[s.name] += 1
                break

    total_items = len(report.results)
    _banner("SUMMARY")
    logger.info(f"  Total: {total_items} taxa")
    logger.info(f"  {'─'*40}")
    for name, count in counts.items():
        pct = count / total_items * 100 if total_items else 0.0
        bar = "█" * int(pct / 5)
        logger.info(f"  {name:<15}  {count:>4}  ({pct:>5.1f}%)  {bar}")
    logger.info(f"  {'─'*40}")
    logger.info(f"  Output : {results_dir}")
    logger.info(f"  Debug  : {debug_dir}")


    print("\n" + "=" * 60)
    print("MAPPING REPORT (JSON)")
    print("=" * 60)
    print(report_json)

    #  Plots (optional)
    if generate_plots:
        _banner("PLOTS")
        from taxa_mapping.sankey_plot import generate_sankey
        result = generate_sankey(run_dir)
        if result:
            logger.info(f"[PLOTS] Saved: {result.relative_to(run_dir)}")

    #  PDF report (optional) 
    if generate_report:
        _banner("PDF REPORT")
        try:
            from taxa_mapping.pdf_report import generate_pdf_report
            pdf_path = generate_pdf_report(run_dir)
            logger.info(f"[REPORT] Saved: {pdf_path}")
        except ImportError as exc:
            logger.warning(f"[REPORT] Skipped: {exc}")


#  Helpers 

def _banner(text: str) -> None:
    logger.info("─" * 50)
    logger.info(f"  {text}")
    logger.info("─" * 50)

def _phase(text: str) -> None:
    logger.info(f"▶  {text}")

def _save(df: pd.DataFrame, path: Path, label: str) -> None:
    df.to_csv(path, index=False)
    logger.info(f"[DEBUG] Saved: {label}  ({len(df)} rows, {len(df.columns)} cols)")

def _run_r_plots(run_dir: Path) -> None:
    import shutil
    import subprocess
    rscript = shutil.which("Rscript")
    if rscript is None:
        logger.warning("[PLOTS] Rscript not found — skipping. Install R to generate plots.")
        return
    script = Path(__file__).resolve().parent / "plot_r" / "run_plots.R"
    if not script.exists():
        logger.warning(f"[PLOTS] Script not found: {script}")
        return
    result = subprocess.run(
        [rscript, str(script), str(run_dir)],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        logger.info(f"[R] {line}")
    for line in result.stderr.splitlines():
        logger.info(f"[R] {line}")
    if result.returncode != 0:
        logger.warning(f"[PLOTS] R script exited with code {result.returncode}")
    else:
        plots_dir = run_dir / "plots"
        pngs = sorted(plots_dir.glob("*.png")) if plots_dir.exists() else []
        logger.info(f"[PLOTS] Generated {len(pngs)} plot(s): {[p.name for p in pngs]}")


# main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Taxa Mapping Debug Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run.py --input input/test_input.csv
        """,
    )
    parser.add_argument("--input",  "-i", required=True, help="Path to the input CSV file.")
    parser.add_argument("--output", "-o", default="./output", help="Base output directory (default: ./output).")
    parser.add_argument("--name",   "-n", default="",         help="Custom identifier for the execution run (e.g., 'my_taxa_mapping'). Appended to the output directory name as: run_TIMESTAMP_NAME.")
    parser.add_argument("--report", action="store_true", help="Generate a PDF debug report upon completion of the run.")
    parser.add_argument("--plots",  action="store_true", help="Execute R scripts to generate quality control plots (requires: R, ggplot2, and patchwork).")
    args = parser.parse_args()

    run_pipeline(args.input, args.output, args.report, args.plots, args.name)
