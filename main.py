import sys
import argparse
import logging
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

# Ensure local package is reachable
sys.path.append(str(Path(__file__).parent))

# Module Imports
try:
    from taxa_mapping.config import settings
    
    # Preprocessing
    from taxa_mapping.core.preprocessing import cleaning
    
    # Jaccard Phase
    from taxa_mapping.core.jaccard import matching, filtering
    
    # NCBI Phase
    from taxa_mapping.core.ncbi import rescue
    
    # Assembly Phase (Postprocessing)
    from taxa_mapping.core.postprocessing import assembly
    
    # Import Status Enum for counting
    from taxa_mapping.schemas.report import MappingStatus
    
except ImportError as e:
    print(f"Import Error: {e}")
    print("Please ensure the 'taxa_mapping/core' directory structure is correct and __init__.py files exist.")
    sys.exit(1)

# Console Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [LOCAL] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_local_pipeline(input_csv: str, output_base_dir: str):
    """
    Executes the Taxa Mapping pipeline locally.
    
    Organizes the output into a timestamped run folder containing:
    - /results: Final user-facing output (CSV and JSON).
    - /debug: Intermediate files for scientific validation.
    """
    # Generate numeric Job ID based on timestamp
    timestamp_str = datetime.now().strftime('%H%M%S')
    job_id = int(timestamp_str)
    
    # --- Directory Setup ---
    base_path = Path(output_base_dir)
    run_dir = base_path / f"run_{timestamp_str}" 
    
    debug_dir = run_dir / "debug"
    results_dir = run_dir / "results"

    # Create directories (parents=True ensures base path exists)
    debug_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"--- START JOB {job_id} ---")
    logger.info(f"Input: {input_csv}")
    logger.info(f"Output Directory: {run_dir}")

    try:
        input_path = Path(input_csv)
        
        # ==============================================================================
        # 1. LOAD DATA
        # ==============================================================================
        if not input_path.exists():
            logger.error(f"Input file not found: {input_path}")
            return

        df = pd.read_csv(input_path)
        
        # Automatic target column detection
        target_col = df.columns[0]
        for candidate in ["taxa_name", "taxon", "organism", "input_name"]:
            if candidate in df.columns:
                target_col = candidate
                break
                
        raw_names = df[target_col].astype(str).tolist()
        logger.info(f"Phase 1 Loaded: {len(raw_names)} taxa from column '{target_col}'")

        # ==============================================================================
        # 2. CLEANING
        # ==============================================================================
        logger.info("Phase 2: Cleaning...")
        cleaned_names = cleaning.clean_taxa_names(raw_names)

        # ==============================================================================
        # 3. MATCHING (Jaccard)
        # ==============================================================================
        logger.info("Phase 3: Jaccard Matching...")
        jaccard_results = matching.run_jaccard_matching(
            taxa_list=cleaned_names,
            raw_taxa_list=raw_names,
            models_csv_path=str(settings.AGORA_MODELS_PATH),
            n_jobs=settings.N_JOBS
        )
        
        # [DEBUG] Save raw Jaccard output
        pd.DataFrame(jaccard_results).to_csv(debug_dir / "01_jaccard_raw.csv", index=False)

				# ==============================================================================
        # 3.5. FILTERING (AND STATS GENERATION)
        # ==============================================================================

        rescue_candidates = filtering.get_candidates_for_rescue(jaccard_results)
        

        df_all = pd.DataFrame(jaccard_results)
        
        if "bands" in df_all.columns:
            total_taxa = len(df_all)

            auto_accepted = len(df_all[df_all["bands"] == "auto-accept"])
            need_rescue = len(df_all[df_all["bands"] != "auto-accept"])
            

            subset_df = df_all[df_all["bands"] != "auto-accept"]
            breakdown = subset_df["bands"].value_counts().to_dict()
            

            pct = round((need_rescue / total_taxa * 100), 1) if total_taxa > 0 else 0.0

            # Costruiamo il dizionario esatto
            filtering_stats = {
                "total_taxa": total_taxa,
                "auto_accepted": auto_accepted,
                "need_rescue": need_rescue,
                "need_rescue_pct": pct,
                "breakdown": breakdown
            }


            with open(debug_dir / "02_filtering_stats.json", "w") as f:
                json.dump(filtering_stats, f, indent=2)


            if rescue_candidates:
                pd.DataFrame(rescue_candidates).to_csv(debug_dir / "02_rescue_candidates.csv", index=False)
        
        else:
            logger.warning("Column 'bands' missing via Main. Cannot generate detailed stats json.")

        # ==============================================================================
        # 4. RESCUE (NCBI)
        # ==============================================================================
        final_results = jaccard_results
        
        if not rescue_candidates:
            logger.info("Skipping Phase 4 (No rescue needed).")
        else:
            logger.info(f"Phase 4: Running NCBI Rescue...")
            
            rescued_items = rescue.run_ncbi_rescue(
                candidates=rescue_candidates,
                ncbi_cache_path=str(settings.NCBI_CACHE_PATH)
            )
            
            # Merge results: Update original list with rescued items
            rescue_map = {item['taxon']: item for item in rescued_items}
            final_results = []
            for item in jaccard_results:
                key = item['taxon']
                final_results.append(rescue_map.get(key, item))
            
            # [DEBUG] Save rescue process details and statistics
            df_rescued = pd.DataFrame(rescued_items)
            
            if 'final_band' in df_rescued.columns:
                rescue_counts = df_rescued['final_band'].value_counts().to_dict()
                logger.info(f"Rescue Stats:\n{json.dumps(rescue_counts, indent=2)}")
            
            df_rescued.to_csv(debug_dir / "03_rescue_process.csv", index=False)

        # ==============================================================================
        # 5. ASSEMBLY & REPORT
        # ==============================================================================
        logger.info("Phase 5: Writing Final Reports...")
        
        # [RESULT] Save Final CSV
        final_csv_path = results_dir / "final_mapping.csv"
        pd.DataFrame(final_results).to_csv(final_csv_path, index=False)
        
        # [RESULT] Save Final JSON Report
        report_obj = assembly.assemble_report(job_id, final_results)
        
        status_counts = {status.name: 0 for status in MappingStatus}
        
        # Iterate results and map values back to keys (e.g. "unambiguous" -> "GREEN")
        for item in report_obj.results:
            # item.status contains the value (e.g. "unambiguous")
            for status in MappingStatus:
                if status.value == item.status:
                    status_counts[status.name] += 1
                    break

        total = len(report_obj.results)
        
        logger.info("=" * 40)
        logger.info(f"FINAL CLASSIFICATION SUMMARY (Total: {total})")
        logger.info("=" * 40)
        for status_name, count in status_counts.items():
            if total > 0:
                pct = (count / total) * 100
            else:
                pct = 0.0
            logger.info(f"{status_name:<15}: {count:>4} ({pct:>5.1f}%)")
        logger.info("=" * 40)
        # ------------------------------------------------

        final_json_path = results_dir / "mapping_report.json"
        
        with open(final_json_path, "w", encoding="utf-8") as f:
            f.write(report_obj.to_json())

        logger.info(f"--- SUCCESS ---")
        logger.info(f"Results: {results_dir}")
        logger.info(f"Debug:   {debug_dir}")

    except Exception as e:
        logger.exception(f"--- Pipeline FAILED: {e} ---")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MINeBUGS Local Runner")
    parser.add_argument("--input", "-i", required=True, help="Path to input CSV file")
    parser.add_argument("--output", "-o", default="./output", help="Base Output directory")
    
    args = parser.parse_args()
    
    run_local_pipeline(args.input, args.output)
