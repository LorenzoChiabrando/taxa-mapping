import logging
import pandas as pd
from typing import List, Dict, Any

# Setup logger
logger = logging.getLogger(__name__)

"""
FILTERING & PREPARATION
-----------------------
This module acts as a logical gatekeeper between the Jaccard Matching Phase 
and the NCBI Rescue Phase.

Its primary responsibility is to segregate high-confidence matches (which are 
accepted immediately) from ambiguous or low-confidence matches that require 
secondary validation via the NCBI taxonomy database.
"""

def get_candidates_for_rescue(jaccard_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters matching results to identify the subset of candidates requiring NCBI Rescue.

    Selection Logic:
    - **DROP**: Items classified as 'auto-accept' (High confidence, validated Genus-Species).
    - **RETAIN**: Items classified as 'grey-zone', 'flag', 'not-accept', or 'na'.
    
    This inverse selection strategy ("Keep everything that is NOT auto-accept") ensures 
    that edge cases, missing data, or unexpected classification bands are always 
    forwarded to the rescue pipeline for safety.

    Args:
        jaccard_results: The complete list of results from the Jaccard matching process.

    Returns:
        A list of dictionaries representing the subset of taxa to be rescued.
    """
    logger.info("--- Step 01a: Filtering candidates for NCBI Rescue ---")

    if not jaccard_results:
        logger.warning("Input results are empty. No candidates to filter.")
        return []

    # Use Pandas for efficient filtering and statistical overview
    df = pd.DataFrame(jaccard_results)

    if "bands" not in df.columns:
        logger.error("Critical: Column 'bands' missing in Jaccard results. Aborting filter.")
        # Fail-safe: If filtering is impossible, pass everything to rescue to avoid data loss.
        return jaccard_results

    # --- FILTERING LOGIC ---
    initial_count = len(df)

    # Define the mask: Retain rows where the confidence band is NOT 'auto-accept'
    mask = df["bands"] != "auto-accept"
    subset_df = df[mask].copy()

    rescue_count = len(subset_df)

    # --- LOGGING & STATISTICS ---
    if initial_count > 0:
        pct = (rescue_count / initial_count) * 100
        logger.info(f"Total Taxa: {initial_count}")
        logger.info(f"Auto-Accepted: {initial_count - rescue_count}")
        logger.info(f"Need Rescue: {rescue_count} ({pct:.1f}%)")

    if not subset_df.empty:
        # Log the breakdown of bands entering the rescue phase (e.g., how many Reds vs Yellows)
        breakdown = subset_df["bands"].value_counts().to_dict()
        logger.info(f"Rescue Breakdown: {breakdown}")
    else:
        logger.info("All taxa were auto-accepted. No NCBI Rescue required.")

    # Return the filtered subset as a list of dictionaries
    return subset_df.to_dict(orient='records')
