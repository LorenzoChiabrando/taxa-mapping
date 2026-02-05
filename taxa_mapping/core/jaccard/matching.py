import logging
import pandas as pd
from typing import List, Dict, Any
from joblib import Parallel, delayed

# Import shared constants and internal modules
from ..shared.constants import CC_PREFIXES
from .tokenization import (
    clean_and_tokenize,
    extract_anchor,
    build_anchor,
    count_anchor_tokens_subspp,
    has_code_or_cc
)
from .scoring import containment_jaccard_distance

# Setup logger
logger = logging.getLogger(__name__)

"""
MATCHING ORCHESTRATOR
---------------------
This module coordinates the high-level taxonomic matching process.

It is responsible for:
1. Loading and tokenizing reference models.
2. Parallelizing the Jaccard distance calculation across available CPUs.
3. Aggregating results and applying biological deduplication logic to select 
   the most specific match for each input taxon.
"""

# ==============================================================================
# 1. WORKER FUNCTION (Parallel Unit)
# ==============================================================================

def process_single_taxa(
        taxon_clean: str,
        anchor: str,
        model_tokens_list: List[List[str]],
        model_filenames: List[str],
        cc_prefixes: List[str]
) -> Dict[str, Any]:
    """
    Executes the matching logic for a single taxonomic query against the reference database.

    Operations:
    1. Tokenizes the input taxon.
    2. Computes Containment Jaccard Distance against all reference models.
    3. Identifies the minimum distance (best match) and handles ties.
    4. Applies a tie-breaking strategy favoring models that explicitly contain 
       the Genus-Species (GS) tokens found in the anchor.
    5. Assigns a confidence band (auto-accept, grey-zone, flag, not-accept) based 
       on the Jaccard score and GS verification.

    Args:
        taxon_clean: The cleaned input taxon string.
        anchor: The extracted 'Genus species' anchor.
        model_tokens_list: Pre-computed token lists for all reference models.
        model_filenames: List of reference model identifiers.
        cc_prefixes: List of culture collection prefixes.

    Returns:
        Dictionary containing the best match, score, confidence band, and candidates.
    """
    # 1. Tokenize input taxon
    tokens_taxa = clean_and_tokenize(taxon_clean, cc_prefixes)

    # 2. Tokenize anchor (if present) to verify Genus-Species (GS) presence
    gs_tokens = []
    if anchor:
        tokens_species = clean_and_tokenize(anchor, cc_prefixes)
        gs_tokens = tokens_species[:2] if len(tokens_species) >= 2 else tokens_species

    # 3. Calculate Distances against all models
    distances = [
        containment_jaccard_distance(tokens_taxa, tokens_mat, cc_prefixes)
        for tokens_mat in model_tokens_list
    ]

    # 4. Find Minimum Distance (Best Match)
    d_min = min(distances)

    # Identify ties (models with distance very close to min)
    tie_idx = [i for i, d in enumerate(distances) if abs(d - d_min) <= 1e-5]

    # 5. Tie-Breaking Logic (Prefer matches containing GS tokens)
    pick_idx = None
    for k in tie_idx:
        chosen_tokens_k = model_tokens_list[k]

        # Check if both Taxon and Model contain the Genus-Species parts
        has_gs_k = (all(t in tokens_taxa for t in gs_tokens) and
                    all(t in chosen_tokens_k for t in gs_tokens))

        if has_gs_k:
            pick_idx = k
            break

    # Default to first tie if no GS preference found
    if pick_idx is None:
        pick_idx = tie_idx[0]

    # 6. Retrieve Best Match Info
    best_mat = model_filenames[pick_idx]
    j_star = 1.0 - distances[pick_idx]

    chosen_tokens = model_tokens_list[pick_idx]

    # Final GS Validation check for the chosen match
    has_gs = (len(gs_tokens) == 2 and
              all(t in tokens_taxa for t in gs_tokens) and
              all(t in chosen_tokens for t in gs_tokens))

    # 7. Classification Bands (Confidence Levels)
    if pd.isna(j_star):
        bands = "na"
    elif j_star >= 0.90 and has_gs:
        bands = "auto-accept"
    elif j_star >= 0.30 and has_gs:
        bands = "grey-zone"
    elif j_star >= 0.30 and not has_gs:
        bands = "flag"
    else:
        bands = "not-accept"

    # Collect list of candidates involved in the tie
    mat_cands = [model_filenames[idx] for idx in tie_idx]
    mat_cands_str = ';'.join(mat_cands)

    return {
        'mat': best_mat,
        'j_score': j_star,
        'has_gs': has_gs,
        'bands': bands,
        'n_candidates': len(mat_cands),
        'mat_candidates_str': mat_cands_str
    }


# ==============================================================================
# 2. DEDUPLICATION LOGIC
# ==============================================================================

def _deduplicate_within_anchor(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies filtering to remove redundant or less specific matches within the same 
    biological anchor (Genus species).

    Logic:
    - Groups results by 'anchor'.
    - Compares the 'subspp_anchor' (specific strain info) of entries within the group.
    - Removes entries where the subspecies tokens are a strict prefix of another 
      entry, favoring the most specific resolution.
    - Handles exact duplicates by prioritizing matches with explicit codes or higher scores.

    Args:
        df: DataFrame containing the aggregated matching results.

    Returns:
        Deduplicated DataFrame.
    """
    if df.empty:
        return df

    rows = []
    # Group by the broad Genus species anchor
    for anchor, g in df.groupby("anchor", dropna=False, sort=False):
        g = g.copy()

        # Tokenize the constructed subspecies anchor for comparison
        g["_subspp_tokens"] = g["subspp_anchor"].apply(lambda x: str(x).split() if x else [])

        keep_mask = [True] * len(g)
        toks_list = g["_subspp_tokens"].tolist()

        for i in range(len(g)):
            ti = toks_list[i]
            for j in range(len(g)):
                if i == j:
                    continue
                tj = toks_list[j]

                # Logic: If 'ti' is a strict prefix of 'tj', drop 'ti'
                if len(tj) > len(ti) and ti and tj[:len(ti)] == ti:
                    keep_mask[i] = False
                    break

        # Apply mask
        g = g.iloc[keep_mask].copy()

        # Final Tie-Breaker for exact duplicates
        g = g.sort_values(
            by=["has_code_or_cc", "j_score", "n_candidates"],
            ascending=[False, False, True]
        )
        g = g.drop_duplicates(subset=["subspp_anchor"], keep="first")

        rows.append(g.drop(columns=["_subspp_tokens"], errors="ignore"))

    return pd.concat(rows, axis=0, ignore_index=True)


# ==============================================================================
# 3. MAIN ORCHESTRATOR
# ==============================================================================

def run_jaccard_matching(
        taxa_list: List[str],
        raw_taxa_list: List[str],
        models_csv_path: str,
        n_jobs: int = -2
) -> List[Dict[str, Any]]:
    """
    Orchestrates the complete Jaccard matching pipeline.

    Workflow:
    1. Loads the reference models CSV.
    2. Pre-tokenizes all reference models for efficiency.
    3. Prepares the input DataFrame with raw and cleaned taxon names.
    4. Executes parallel matching using `process_single_taxa`.
    5. Calculates additional metadata (e.g., specific anchors, token counts).
    6. Performs deduplication to ensure unique, best-fit results.
    7. Formats the output for downstream processing (Rescue/Reporting).

    Args:
        taxa_list: List of cleaned input taxon names.
        raw_taxa_list: List of original raw input taxon names.
        models_csv_path: Path to the CSV file containing reference models.
        n_jobs: Number of CPUs to use for parallel processing.

    Returns:
        List of dictionaries representing the final matching results.
    """
    logger.info(f"Starting Jaccard Matching with {len(taxa_list)} queries...")

    # 1. Load Reference Models
    try:
        models_df = pd.read_csv(models_csv_path)
        # Remove extension if present
        models_df['Filename'] = models_df['Filename'].astype(str).str.replace(r'\.mat$', '', regex=True)
        model_filenames = models_df['Filename'].tolist()
    except Exception as e:
        logger.error(f"Failed to load models CSV: {e}")
        raise e

    # 2. Pre-Tokenize Models
    model_tokens_list = [clean_and_tokenize(fn, CC_PREFIXES) for fn in model_filenames]

    # 3. Prepare Input Data
    # taxa_name = Original | taxon = Cleaned
    input_df = pd.DataFrame({
        'taxa_name': raw_taxa_list,
        'taxon': taxa_list
    })
    input_df['anchor'] = input_df['taxon'].apply(extract_anchor)

    # 4. Run Parallel Matching
    results = Parallel(n_jobs=n_jobs)(
        delayed(process_single_taxa)(
            row['taxon'],
            row['anchor'],
            model_tokens_list,
            model_filenames,
            CC_PREFIXES
        )
        for _, row in input_df.iterrows()
    )

    # 5. Merge Results
    results_df = pd.DataFrame(results)
    combined_df = pd.concat([input_df.reset_index(drop=True), results_df], axis=1)

    # 6. Post-Processing & Metadata
    combined_df['subspp_anchor'] = combined_df.apply(
        lambda row: build_anchor(row['taxon'], row['anchor'], CC_PREFIXES),
        axis=1
    )

    # Calculate token counts for anchor specificity
    combined_df['anchor_tokens'] = combined_df['subspp_anchor'].apply(
        lambda x: count_anchor_tokens_subspp(x, CC_PREFIXES)
    )

    combined_df['anchor_tokens_base'] = combined_df['anchor'].apply(
        lambda x: count_anchor_tokens_subspp(x, CC_PREFIXES)
    )

    combined_df['has_code_or_cc'] = combined_df['taxon'].apply(has_code_or_cc)

    # 7. Deduplication
    final_df = _deduplicate_within_anchor(combined_df)

    # 8. Reorder Columns for Consistency
    # Ensures the output structure matches the expected contract.
    desired_order = [
        "taxa_name",
        "taxon",
        "anchor",
        "mat",
        "j_score",
        "has_gs",
        "bands",
        "n_candidates",
        "mat_candidates_str",
        "subspp_anchor",
        "anchor_tokens",
        "anchor_tokens_base",
        "has_code_or_cc"
    ]

    # Select only existing columns (safe filter) but in the desired order
    final_cols = [c for c in desired_order if c in final_df.columns]
    final_df = final_df[final_cols]

    return final_df.to_dict(orient='records')
