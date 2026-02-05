import logging
import json
from typing import List, Dict, Any

# Relative import: 
# taxa_mapping.core.postprocessing -> taxa_mapping.core -> taxa_mapping -> schemas
from ...schemas.report import MappingReport, MappingItem, MappingCandidate, MappingStatus

logger = logging.getLogger(__name__)

"""
ASSEMBLY & REPORTING MODULE
---------------------------
This module handles the final Post-Processing phase.

It is responsible for:
1. Aggregating raw results from the Jaccard Matching and NCBI Rescue phases.
2. Normalizing confidence scores and status codes (Traffic Light system).
3. formatting the final output into the standardized JSON structure (MappingReport) 
   required by the API contract.

Design Decision on Scoring:
The `confidence_score` primarily relies on the Jaccard Index (0.0-1.0) rather than 
the NCBI Rescue score (0-100) to maintain metric consistency across the pipeline, 
except for specific overrides (e.g., Auto-Accept, Yellow-Green).
"""


def determine_status_and_score(row: Dict[str, Any]) -> tuple[MappingStatus, float]:
    """
    Determines the final status color and normalized confidence score for a taxon.

    Logic:
    - GREEN / AUTO_ACCEPT: 1.0
    - YELLOW_GREEN: 0.95 (High confidence rescue)
    - YELLOW / GREY_ZONE: Max(Jaccard Score, 0.60)
    - BLACK / NOT_FOUND: 0.0
    - RED: Raw Jaccard Score

    Args:
        row: Dictionary containing the processing results for a single taxon.

    Returns:
        Tuple containing the Enum status and the float confidence score.
    """
    raw_band = str(row.get("final_band") or row.get("bands") or "red")
    band = raw_band.lower().replace("-", "_").strip()

    j_score = float(row.get("j_score") or 0.0)
    final_score = j_score 

    # A) GREEN / AUTO-ACCEPT
    if "green" in band and "yellow" not in band:
        return MappingStatus.GREEN, 1.0

    if "auto_accept" in band:
        return MappingStatus.GREEN, 1.0

    # B) YELLOW_GREEN (Special high-confidence rescue)
    if "yellow_green" in band:
        return MappingStatus.YELLOW_GREEN, 0.95

    # C) YELLOW / GREY-ZONE
    if "yellow" in band or "grey_zone" in band:
        return MappingStatus.YELLOW, max(final_score, 0.60)

    # D) BLACK / NOT FOUND
    if "black" in band or "not_found" in band:
        return MappingStatus.BLACK, 0.0

    # E) RED (Low confidence)
    return MappingStatus.RED, final_score


def parse_candidates(row: Dict[str, Any]) -> List[MappingCandidate]:
    """
    Constructs the list of potential candidates for the final report.

    Priority:
    1. 'ranked_candidates' (Structured output from NCBI Rescue).
    2. 'mat_candidates_str' (Fallback to raw Jaccard candidates).

    Args:
        row: Dictionary containing the processing results for a single taxon.

    Returns:
        List of MappingCandidate objects.
    """
    candidates: List[MappingCandidate] = []

    # --- CASE 1: Structured Data from NCBI Rescue ---
    ranked_data = row.get("ranked_candidates")
    
    # Check if ranked_candidates is already a parsed list of dicts (from Rescue module)
    # Note: If it's a raw string "@@", it falls through to legacy handling or needs pre-parsing.
    # Assuming upstream modules provide a list or compatible structure here.
    if ranked_data and isinstance(ranked_data, list) and len(ranked_data) > 0:
        for cand in ranked_data:
            # Handle dictionary format if available
            if isinstance(cand, dict):
                raw_s = cand.get("score", 0)
                try:
                    # Normalize rescue score (0-100) to float (0-1)
                    c_score = float(raw_s) / 100.0
                except Exception:
                    c_score = 0.0

                candidates.append(MappingCandidate(
                    model_id=str(cand.get("model", "unknown")),
                    score=round(c_score, 2),
                    reason=str(cand.get("reason", "Rescue Analysis"))
                ))
        return candidates

    # --- CASE 2: Fallback to Jaccard Raw Candidates (mat_candidates_str) ---
    cands_input = row.get("mat_candidates_str")
    raw_list: List[Any] = []

    if isinstance(cands_input, list):
        raw_list = cands_input
    elif isinstance(cands_input, str) and cands_input.strip():
        s = cands_input.strip()
        # Handle JSON array string
        if s.startswith("[") and s.endswith("]"):
            try:
                raw_list = json.loads(s.replace("'", '"'))
            except Exception:
                # Fallback to semicolon split on failure
                raw_list = [x.strip() for x in s.split(";") if x.strip()]
        else:
            # Handle legacy semicolon separation
            raw_list = [x.strip() for x in s.split(";") if x.strip()]

    # Fallback to single 'mat' match if no list is present
    if not raw_list:
        mat = row.get("mat")
        if mat:
            raw_list = [mat]
        else:
            return []

    winner = row.get("suggested_gem") or row.get("mat")
    try:
        j_score = float(row.get("j_score") or 0.5)
    except Exception:
        j_score = 0.5

    for mod in raw_list:
        mod = str(mod).strip()
        if not mod:
            continue
        
        # In Jaccard fallback, only the winner gets the high score
        is_winner = (mod == winner)
        score_val = j_score if is_winner else 0.5

        candidates.append(MappingCandidate(
            model_id=mod,
            score=round(score_val, 2),
            reason="Jaccard Similarity"
        ))

    return candidates


def assemble_report(job_id: int, rows: List[Dict[str, Any]]) -> MappingReport:
    """
    Main Factory method.
    
    Converts a list of row dictionaries (merged results) into the final 
    immutable MappingReport object compliant with the JSON schema.

    Args:
        job_id: The unique identifier for the mapping job.
        rows: List of dictionaries representing processed taxa.

    Returns:
        A populated MappingReport object.
    """
    items: List[MappingItem] = []

    for row in rows:
        status, conf = determine_status_and_score(row)

        mapped_id = row.get("suggested_gem") or row.get("mat") or ""
        
        # Fallback chain for the query name
        query_name = (row.get("taxa_name") 
                      or row.get("taxon") 
                      or row.get("input_name") 
                      or "Unknown")

        items.append(MappingItem(
            query_name=query_name,
            mapped_id=mapped_id,
            status=status,
            confidence_score=round(float(conf), 4),
            candidates=parse_candidates(row)
        ))

    return MappingReport(
        job_id=job_id,
        total_bacteria=len(items),
        results=items
    )
