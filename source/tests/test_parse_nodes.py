from taxa_mapping.tools.taxdump_cache import parse_nodes


def test_parse_nodes_maps_parent_and_rank(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    assert nodes["821"] == ("909656", "species")
    assert nodes["909656"] == ("2", "genus")
    assert nodes["2"] == ("131567", "superkingdom")
    assert len(nodes) == 10
