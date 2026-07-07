import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # make source/ importable

import pytest

# taxid, parent, rank
NODES = [
    ["1", "1", "no rank"],
    ["131567", "1", "no rank"],
    ["2", "131567", "superkingdom"],
    ["2157", "131567", "superkingdom"],
    ["2759", "131567", "superkingdom"],
    ["909656", "2", "genus"],
    ["821", "909656", "species"],
    ["2172", "2157", "genus"],
    ["2173", "2172", "species"],
    ["9606", "2759", "species"],
]
# taxid, name, unique, class
NAMES = [
    ["1", "root", "", "scientific name"],
    ["131567", "cellular organisms", "", "scientific name"],
    ["2", "Bacteria", "", "scientific name"],
    ["2157", "Archaea", "", "scientific name"],
    ["2759", "Eukaryota", "", "scientific name"],
    ["909656", "Phocaeicola", "", "scientific name"],
    ["821", "Phocaeicola vulgatus", "", "scientific name"],
    ["821", "Bacteroides vulgatus", "", "synonym"],
    ["821", "Bacteroides vulgatus (Eggerth and Gagnon 1933)", "", "authority"],
    ["2172", "Methanobrevibacter", "", "scientific name"],
    ["2173", "Methanobrevibacter smithii", "", "scientific name"],
    ["9606", "Homo sapiens", "", "scientific name"],
]
# old, new
MERGED = [
    ["76856", "821"],
]


def _write_dmp(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write("\t|\t".join(row) + "\t|\n")


@pytest.fixture
def taxdump_dir(tmp_path):
    d = tmp_path / "taxdump"
    d.mkdir()
    _write_dmp(d / "nodes.dmp", NODES)
    _write_dmp(d / "names.dmp", NAMES)
    _write_dmp(d / "merged.dmp", MERGED)
    return d
