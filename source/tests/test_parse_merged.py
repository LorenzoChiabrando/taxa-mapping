from taxa_mapping.tools.taxdump_cache import parse_merged


def test_parse_merged_maps_new_to_old(taxdump_dir):
    merged = parse_merged(taxdump_dir / "merged.dmp", {"821"})
    assert merged["821"] == ["76856"]


def test_parse_merged_excludes_out_of_scope(taxdump_dir):
    merged = parse_merged(taxdump_dir / "merged.dmp", {"999"})
    assert merged == {}
