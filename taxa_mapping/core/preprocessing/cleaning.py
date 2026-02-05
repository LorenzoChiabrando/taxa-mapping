import re
import logging
from typing import List

logger = logging.getLogger(__name__)

def clean_taxa_names(raw_names: List[str]) -> List[str]:
    """
    Standardizes a list of taxonomic names by applying specific cleaning rules.

    The pipeline performs the following operations:
    1. Removes square brackets around genus names (e.g., "[Eubacterium]" -> "Eubacterium").
    2. Normalizes strain codes by separating short prefixes from numbers (e.g., "CAG-123" -> "CAG 123").
    3. Removes extraneous punctuation (commas, semicolons).
    4. Normalizes whitespace (trims leading/trailing spaces and collapses internal spaces).

    Args:
        raw_names: List of raw taxonomic strings.

    Returns:
        List of cleaned strings.
    """
    cleaned_list = []

    # 1. Regex to remove enclosing square brackets often found in taxonomy databases.
    # Example: "[Eubacterium] rectale" -> "Eubacterium rectale"
    re_brackets = re.compile(r"^\[([^\]]+)\]")

    # 2. Regex to normalize strain numbers attached with a dash.
    # Logic: Separates the prefix from the number with a space (e.g., "CAG-123" -> "CAG 123").
    # Constraint: Only applies if the prefix is short (1-4 letters) to avoid splitting 
    # valid hyphenated genus names (e.g., "Clostridium-like").
    re_strain_dash = re.compile(r"(\b[A-Za-z]{1,4})-([0-9]+)\b")

    # 3. Regex to remove specific punctuation characters.
    re_punct = re.compile(r"[,;]+")

    for name in raw_names:
        if not isinstance(name, str):
            cleaned_list.append("")
            continue

        s = name

        # Apply Step 1: Remove brackets
        s = re_brackets.sub(r"\1", s)

        # Apply Step 2: Format strain codes
        s = re_strain_dash.sub(r"\1 \2", s)

        # Apply Step 3: Remove punctuation
        s = re_punct.sub("", s)

        # Apply Step 4: Squash whitespace (equivalent to trimming + reducing internal spaces)
        s = " ".join(s.split())

        cleaned_list.append(s)

    return cleaned_list
