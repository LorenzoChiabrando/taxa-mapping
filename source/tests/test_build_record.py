from taxa_mapping.tools.taxdump_cache import (
    parse_nodes, compute_in_scope, ancestors_of_roots, parse_names, parse_merged,
    build_lineage, build_record,
)
from taxa_mapping.core import ncbi_scoring


def _load(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    in_scope = compute_in_scope(nodes, {"2", "2157"})
    capture = in_scope | ancestors_of_roots(nodes, {"2", "2157"})
    sci, alt, authority = parse_names(taxdump_dir / "names.dmp", capture)
    merged = parse_merged(taxdump_dir / "merged.dmp", in_scope)
    return nodes, sci, alt, authority, merged


def test_build_lineage_root_to_parent(taxdump_dir):
    nodes, sci, alt, authority, merged = _load(taxdump_dir)
    lineage = build_lineage("821", nodes, sci)
    names = [e["ScientificName"] for e in lineage]
    assert names == ["cellular organisms", "Bacteria", "Phocaeicola"]
    genus = [e for e in lineage if e["Rank"] == "genus"]
    assert genus[0]["ScientificName"] == "Phocaeicola"


def test_build_record_roundtrips_through_parse_tax_record(taxdump_dir):
    nodes, sci, alt, authority, merged = _load(taxdump_dir)
    rec = build_record("821", nodes, sci, alt, authority, merged)
    assert rec["ScientificName"] == "Phocaeicola vulgatus"
    assert rec["Rank"] == "species"
    assert rec["OtherNames"]["Synonym"] == ["Bacteroides vulgatus"]
    assert rec["MergedTaxIds"] == ["76856"]

    info = ncbi_scoring.parse_tax_record(rec)
    assert info["canonical"] == "Phocaeicola vulgatus"
    assert info["rank"] == "species"
    assert "Phocaeicola" in info["lineage_genera"]
    assert "Bacteroides vulgatus" in info["synonyms"]
