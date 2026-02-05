import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ==============================================================================
# REGEX PATTERNS & HELPERS
# ==============================================================================

# Matches 'Candidatus' prefix (case-insensitive)
_CANDIDATUS_RE = re.compile(r"^\s*Candidatus\s+", flags=re.IGNORECASE)

# Matches infraspecific rank markers (e.g., subsp., strain, var.)
_INFRASPECIFIC_RE = re.compile(
    r"\b(subsp\.?|ssp\.?|subspecies|strain|pv\.?|pathovar|serovar|biovar|var\.?|variant|f\.?|forma)\b",
    flags=re.IGNORECASE
)

# Matches strain-like tokens: 1-5 letters followed by 2+ alphanumeric chars (e.g., "K12", "ATCC123")
_STRAIN_TOKEN_RE = re.compile(r"\b([A-Za-z]{1,5}[A-Za-z0-9_.-]{2,})\b")


def _strip_parenthetical_authorship(s: str) -> str:
    """Removes text inside parentheses (often authorship citations)."""
    return re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()


def _sanitize_punct(s: str) -> str:
    """Removes extraneous punctuation brackets and normalizes whitespace."""
    s = re.sub(r"[\[\]\(\)\{\}:;,\|]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_candidatus(s: str) -> str:
    """Removes the 'Candidatus' prefix from a taxon name."""
    return _CANDIDATUS_RE.sub("", s).strip()


def _strip_infraspecific(s: str) -> str:
    """
    Truncates a taxon name at the first infraspecific rank marker.
    Preserves 'sp.' placeholders if they follow the genus.
    """
    s2 = s
    m = _INFRASPECIFIC_RE.search(s2)
    if m:
        s2 = s2[:m.start()].strip()
    # Ensure 'Genus sp' format is preserved if it existed
    s2 = re.sub(r"\bsp\.?\s+\S.*$", "sp.", s2, flags=re.IGNORECASE).strip()
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2


def _extract_strain_token(s: str) -> Optional[str]:
    """
    Attempts to isolate a distinct strain identifier from the end of the string.
    Filters out common taxonomic stopwords (e.g., 'strain', 'subsp').
    """
    if not s:
        return None
    
    STOP = {
        "strain", "subsp", "ssp", "pv", "serovar", "biovar", "var", 
        "variant", "sp", "genus", "species", "candidatus"
    }
    
    toks = re.split(r"\s+", s.strip())
    # Iterate backwards to find the last valid token
    for t in reversed(toks):
        t_clean = re.sub(r"[^A-Za-z0-9_.-]", "", t)
        if not t_clean or t_clean.lower() in STOP:
            continue
        
        m = _STRAIN_TOKEN_RE.fullmatch(t_clean)
        if m:
            return m.group(1)
            
    return None


class NcbiRepository:
    """
    Read-only Repository for accessing NCBI taxonomic data from a local JSON cache.
    
    This class simulates database access by querying a pre-loaded dictionary.
    
    Expected Cache Structure:
      - Keys like "TAX::<term>" -> List of matching records.
      - Keys like "IDS::<id1,id2>" -> List of specific records.
    """

    def __init__(self, cache_path: str):
        """
        Initialize the repository and load the cache into memory.
        
        Args:
            cache_path: Filesystem path to the NCBI JSON cache file.
        """
        self.cache_path = Path(cache_path)
        self.cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Loads the JSON cache from disk. Handles missing files gracefully."""
        if not self.cache_path.exists():
            logger.warning(f"NCBI cache file not found at: {self.cache_path}")
            self.cache = {}
            return
        
        try:
            logger.info(f"Loading NCBI Cache from {self.cache_path}...")
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            logger.info(f"Cache loaded successfully with {len(self.cache)} entries.")
        except Exception as e:
            logger.exception(f"Failed to load cache {self.cache_path}: {e}")
            self.cache = {}

    def fetch_records(self, raw_name: str) -> List[Dict[str, Any]]:
        """
        Retrieves taxonomic records using a cascading search strategy ("Monolithic" logic).

        The search attempts multiple variations of the input name in order of specificity:
        1. Exact match (raw name).
        2. Stripped authorship (e.g., remove "(Smith 1990)").
        3. Sanitized punctuation.
        4. Stripped 'Candidatus'.
        5. Stripped infraspecific ranks (Genus species).
        6. Strain token rescue (searching just the strain ID or 'Genus + ID').
        7. Genus-only fallback.

        Args:
            raw_name: The taxonomic name string to search for.

        Returns:
            A list of matching records found in the cache (first hit wins).
        """
        if not raw_name:
            return []

        name = re.sub(r"\s+", " ", str(raw_name)).strip()
        if not name:
            return []

        # Generate name variations
        stripped = _strip_parenthetical_authorship(name)
        san = _sanitize_punct(stripped or name)
        cand = _strip_candidatus(san or stripped or name)
        infra = _strip_infraspecific(cand or san or stripped or name)

        # Build prioritized search list (unique entries only)
        variants: List[str] = []
        for v in [name, stripped, san, cand, infra]:
            if v and v not in variants:
                variants.append(v)

        # Try to extract and search by specific strain tokens
        base_str = infra or cand or san or stripped or name
        token = _extract_strain_token(base_str)
        genus = base_str.split()[0] if base_str.split() else None

        if token:
            for v in [token, f"{genus} {token}" if genus else None]:
                if v and v not in variants:
                    variants.append(v)

        # Final fallback: Genus only
        if genus and genus not in variants:
            variants.append(genus)

        # Execute search against cache
        for v in variants:
            recs = self.cache.get(f"TAX::{v}")
            if isinstance(recs, list) and recs:
                return recs

        return []

    def fetch_by_taxids(self, taxids: List[str]) -> List[Dict[str, Any]]:
        """
        Retrieves records for a specific list of NCBI Taxonomy IDs.

        Args:
            taxids: List of TaxID strings (e.g., ["562", "1234"]).

        Returns:
            List of matching records.
        """
        if not taxids:
            return []
        
        # Normalize IDs: sort and strip to ensure cache key consistency
        ids = sorted({str(x).strip() for x in taxids if str(x).strip()})
        if not ids:
            return []
            
        key = f"IDS::{','.join(ids)}"
        recs = self.cache.get(key)
        
        return recs if isinstance(recs, list) else []
