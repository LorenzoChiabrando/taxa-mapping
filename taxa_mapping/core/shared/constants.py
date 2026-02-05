import re

"""
CONSTANTS & PATTERNS
--------------------
This module defines static constants, vocabulary sets, and pre-compiled 
Regular Expressions (Regex) used by the Taxa Mapping algorithm.

It serves as a centralized configuration for biological text parsing, 
including Culture Collection (CC) prefixes, taxonomic stopwords, and 
pattern matching rules for strain identifiers.
"""

# 1. BIOLOGICAL VOCABULARIES (LISTS & SETS)

# List of known Culture Collection prefixes used to identify strain IDs.
# Examples: ATCC (American Type Culture Collection), DSM (German Collection), etc.
CC_PREFIXES = [
    "ATCC", "DSM", "JCM", "NCTC", "CCUG", "LMG", "CECT", "NRRL", "KCTC", "NBRC",
    "CIP", "APEC", "Nissle", "NJS", "CGMCC", "BCCM", "IFO", "IAM", "CBS", "MTCC",
    "KACC", "BCRC", "DSMZ", "NZCM", "WAL", "ETEC", "ABU", "ECC"
]

# Set of stopwords specific to the biological/taxonomic context.
CONTEXT_STOPS = {
    'strain', 'isolate', 'clone', 'str', 'str.', 'of', 'from', 'in', 'on', 'associated',
    'host', 'et', 'al', 'ex'
}

# Adjective modifiers that may precede a taxon name or description.
ADJ_MODS = {
    'primary', 'secondary', 'facultative', 'obligate', 'obligatory',
    'intracellular', 'extracellular'
}

# Nouns (Heads) that frequently appear associated with the modifiers above.
HEADS = {'endosymbiont', 'symbiont', 'epibiont'}

# Keywords indicating a descriptive or provisional classification
# rather than a formal valid taxonomic name.
DESC_START = {
    'uncultured', 'unidentified', 'unclassified', 'unknown',
    'environmental', 'candidate', 'bacterium', 'bacterial',
    'archaeon', 'archaeal', 'endosymbiont', 'symbiont', 'epibiont', 'cyanobacterium'
}

# Common nouns found in isolation source descriptions that might be
# mistaken for alphanumeric codes.
COMMON_CONTEXT_NOUNS = {
    'lake', 'river', 'spring', 'bay', 'island', 'islet', 'mount', 'mt', 'valley', 'forest',
    'host', 'leaf', 'root', 'soil', 'sediment', 'gut', 'mouse', 'human', 'epithemia', 'turgida'
}

# 2. REGEX HELPERS (String Construction)

# Helper string to create regex patterns matching any defined Culture Collection prefix.
# Result example: "ATCC|DSM|JCM|..."
CC_ALT_PATTERN = '|'.join(CC_PREFIXES)

# 3. COMPILED REGEX PATTERNS

# Matches a general taxonomic epithet (lowercase word, possibly with hyphens).
# Used to validate species or subspecies names.
EPITHET_RX = re.compile(r'^[a-z][a-z-]*$')

# Matches infraspecific rank markers.
# Examples: "subsp.", "var.", "serovar", "pathovar".
INFRA_RX = re.compile(r'(?i)\b(?:subsp(?:\.|ecies)?|pv\.?|pathovar|var\.?|variety|biovar|serovar)\b')

# Matches Culture Collection Aliases in various formats.
# Examples: "ATCC 12345", "DSM-6789", "JCM_0001".
CC_ALIAS_RX = re.compile(rf'(?i)\b(?:{CC_ALT_PATTERN})\s*[A-Z]*[-_/]*\d[A-Za-z0-9-]*\b')

# Matches Serotype patterns (O-Antigen / H-Antigen / K-Antigen).
# Examples: "O157:H7", "O104".
SEROTYPE_RX = re.compile(r'(?i)\bO\d+[A-Za-z]?(?::(?:H|K)\d+[A-Za-z]?)?\b')
SEROTYPE_PAIR_RX = re.compile(r'(?i)\b(O\d+[A-Za-z]?)\s*[:\-_ ]\s*((?:H|K)\d+[A-Za-z]?)\b')
SEROTYPE_LONE_O_RX = re.compile(r'(?i)\b(O\d+[A-Za-z]?)\b')

# Matches administrative tokens often found in raw database dumps.
# Examples: "sp.", "spp.", "strain", "aff.".
ADMIN_TOKENS_RX = re.compile(r'(?i)^(sp|spp|strain|str|substr|subspecies|cf|aff|pv|var|biovar|serovar)$')

# --- Validation Patterns ---

# Matches valid alphanumeric codes (e.g., strain IDs).
CODE_WORD_RX = re.compile(r'^[A-Za-z][A-Za-z0-9]{0,6}$')
CODE_WORD_WITH_SEP_RX = re.compile(r'^[A-Za-z][A-Za-z0-9]{0,6}[-_./]$')
CODE_NUM_RX = re.compile(r'^\d+[A-Za-z0-9-]*$')

# Matches authorship citations to be stripped.
# Example: "Smith et al. 2020", "(Jones ex Brown 1999)".
AUTH_RX_1 = re.compile(r'\([^()]*\b(ex|et\s+al\.?)\b[^()]*\d{4}[^()]*\)', re.IGNORECASE)
AUTH_RX_2 = re.compile(r'\bex\s+[A-Z][a-z]+(?:\s+et\s+al\.?)?\s+\d{4}\b', re.IGNORECASE)

# Complex Pattern: Identifies if a token is a Code OR a Culture Collection ID.
# Matches:
# 1. Known CC Prefixes followed by numbers (e.g., "ATCC 123").
# 2. Generic Codes: Short alphanumeric prefix followed by numbers (e.g., "CAG 45").
CODE_OR_CC_RX = re.compile(
    rf'(?i)\b(?:{CC_ALT_PATTERN})\s*[-_/]?[A-Z]*\s*\d+[A-Za-z0-9-]*\b|'
    r'\b[A-Za-z][A-Za-z0-9]{1,6}[-_./]?\s*\d+[A-Za-z0-9-]*\b'
)