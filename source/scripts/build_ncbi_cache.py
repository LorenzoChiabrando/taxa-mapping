#!/usr/bin/env python3
"""CLI: build a Bacteria+Archaea NCBI-taxonomy cache from the NCBI taxdump."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # source/

from taxa_mapping.tools.taxdump_cache import generate, DEFAULT_CLADES

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "ncbi_cache_full.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Bacteria+Archaea NCBI taxonomy cache from the taxdump.",
    )
    parser.add_argument("--taxdump", default=None,
                        help="Path to an extracted taxdump dir or taxdump.tar.gz. "
                             "If omitted, downloads from NCBI.")
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT),
                        help="Output JSON path (default: source/data/ncbi_cache_full.json).")
    parser.add_argument("--clades", default=",".join(sorted(DEFAULT_CLADES)),
                        help="Comma-separated root taxids (default: 2,2157).")
    parser.add_argument("--work-dir", default=None,
                        help="Scratch dir for download/extraction.")
    args = parser.parse_args()

    clades = {c.strip() for c in args.clades.split(",") if c.strip()}
    stats = generate(args.taxdump, args.output, clades, args.work_dir)

    print("NCBI taxonomy cache built:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
