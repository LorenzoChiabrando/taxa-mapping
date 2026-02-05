import re
from typing import List, Optional, Set

# Import default prefixes for fallback
from ..shared.constants import CC_PREFIXES

"""
SCORING & DISTANCE METRICS
--------------------------
This module implements the mathematical core of the taxonomic matching algorithm.

It is responsible for:
1. Extracting Culture Collection (CC) tokens from tokenized strings.
2. Selecting the optimal CC alias to represent a strain, handling synonym resolution.
3. Calculating the Containment Jaccard Distance between a query taxon and a reference model.
"""

# ==============================================================================
# 1. CC ALIAS MANAGEMENT
# ==============================================================================

def extract_cc(tokens: List[str], cc_prefixes: List[str] = CC_PREFIXES) -> List[str]:
    """
    Identifies and extracts normalized Culture Collection aliases from a list of tokens.

    This function filters tokens that match the standard pattern 'PREFIX_NUMBER'
    (e.g., 'ATCC_12345', 'DSM_20014').

    Args:
        tokens: List of string tokens to inspect.
        cc_prefixes: List of valid culture collection prefixes.

    Returns:
        List of matching tokens found in the input.
    """
    # Regex matching: Start of string ^, Prefix, Underscore, Alphanumeric, End $
    # Example: ^(ATCC|DSM|...)_[A-Za-z0-9-]+$
    cc_rx = rf"^({'|'.join(cc_prefixes)})_[A-Za-z0-9-]+$"

    return [t for t in tokens if re.match(cc_rx, t, re.IGNORECASE)]


def choose_cc(ccs: List[str],
              ref_overlap: Optional[List[str]] = None,
              cc_prefixes: List[str] = CC_PREFIXES) -> Optional[str]:
    """
    Selects the single best representative Culture Collection alias from a list of candidates.

    The selection logic follows a strict priority order to ensure consistent matching:
    1. **Overlap Priority**: If an alias is present in both the Query and the Reference Model
       (provided via `ref_overlap`), it is selected immediately to maximize the match score.
    2. **Prefix Rank**: If no overlap exists, standard prefixes (defined by the order in `cc_prefixes`,
       e.g., ATCC, DSM) are preferred over less common ones.
    3. **Lexicographic Order**: Used as a final tie-breaker.

    Args:
        ccs: List of available CC tokens in the current set.
        ref_overlap: List of CC tokens shared with the comparison target (optional).
        cc_prefixes: Ordered list of prefixes defining priority.

    Returns:
        The single selected token string, or None if the input list is empty.
    """
    if not ccs:
        return None

    # Filter candidates: restrict to overlap if exists, otherwise keep all
    cand = list(set(ccs) & set(ref_overlap)) if ref_overlap else ccs

    # Fallback: if overlap filtering resulted in an empty list, revert to original ccs
    if not cand:
        cand = ccs

    def get_rank(token: str) -> int:
        """Helper: Lower index in CC_PREFIXES list indicates Higher Priority."""
        # Extract prefix part (ATCC_123 -> ATCC)
        prefix = re.sub(r'^([A-Z]+)_.*$', r'\1', token)
        try:
            return cc_prefixes.index(prefix)
        except ValueError:
            # If prefix not in known list, assign lowest priority
            return len(cc_prefixes) + 1

    # Sort: Primary key = Rank (asc), Secondary key = Token string (asc)
    cand_sorted = sorted(cand, key=lambda x: (get_rank(x), x))

    return cand_sorted[0]


# ==============================================================================
# 2. DISTANCE CALCULATION
# ==============================================================================

def containment_jaccard_distance(tokens_taxa: List[str],
                                 tokens_model: List[str],
                                 cc_prefixes: List[str] = CC_PREFIXES) -> float:
    """
    Calculates the 'Containment Jaccard Distance' between a Taxon Query and a Reference Model.

    The standard Jaccard Index is defined as Intersection / Union.
    This implementation adds biological awareness:
    
    1. **Synonym Resolution**: It detects multiple Culture Collection aliases referring to the 
       same strain (e.g., ATCC_123 and DSM_456).
    2. **Noise Reduction**: Instead of treating mismatched aliases as different entities, 
       it forces the comparison to use a single representative alias per side. If the correct 
       synonym exists in both sets, the `choose_cc` logic ensures they align, maximizing the intersection.

    Formula:
        Distance = 1.0 - (Intersection(SetA, SetB) / Union(SetA, SetB))

    Args:
        tokens_taxa: List of tokens representing the input taxon.
        tokens_model: List of tokens representing the reference model.
        cc_prefixes: List of valid culture collection prefixes.

    Returns:
        Float value representing the distance (0.0 = identical, 1.0 = completely different).
    """
    T0 = list(set(tokens_taxa))
    M0 = list(set(tokens_model))

    Tcc = extract_cc(T0, cc_prefixes)
    Mcc = extract_cc(M0, cc_prefixes)

    # Regex to identify CC tokens for filtering
    cc_rx = rf"^({'|'.join(cc_prefixes)})_[A-Za-z0-9-]+$"

    # --- Synonym Resolution Logic ---
    if Tcc or Mcc:
        # Find aliases common to both sets
        overlap = list(set(Tcc) & set(Mcc))

        # Choose the single best representative for each side
        keep_T = choose_cc(Tcc, ref_overlap=overlap, cc_prefixes=cc_prefixes)
        keep_M = choose_cc(Mcc, ref_overlap=overlap, cc_prefixes=cc_prefixes)

        # Rebuild sets:
        # 1. Remove ALL CC tokens from the original list
        # 2. Add back ONLY the chosen representative (if any)

        Tset = list(set(
            [t for t in T0 if not re.match(cc_rx, t, re.IGNORECASE)] +
            ([keep_T] if keep_T else [])
        ))

        Mset = list(set(
            [t for t in M0 if not re.match(cc_rx, t, re.IGNORECASE)] +
            ([keep_M] if keep_M else [])
        ))
    else:
        # No aliases involved, use raw sets
        Tset = T0
        Mset = M0

    # --- Standard Jaccard Calculation ---
    inter = len(set(Tset) & set(Mset))
    uni = len(set(Tset) | set(Mset))

    # Avoid division by zero
    if uni == 0:
        return 1.0

    return 1.0 - (inter / uni)
