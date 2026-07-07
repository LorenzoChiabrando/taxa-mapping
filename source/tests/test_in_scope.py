from taxa_mapping.tools.taxdump_cache import (
    parse_nodes,
    compute_in_scope,
    ancestors_of_roots,
)


def test_in_scope_keeps_bacteria_and_archaea_drops_eukaryote(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    scope = compute_in_scope(nodes, {"2", "2157"})
    assert {"2", "909656", "821"} <= scope        # Bacteria lineage
    assert {"2157", "2172", "2173"} <= scope      # Archaea lineage
    assert "9606" not in scope                     # eukaryote
    assert "2759" not in scope                     # Eukaryota root
    assert "131567" not in scope                   # cellular organisms (above clades)


def test_ancestors_of_roots(taxdump_dir):
    nodes = parse_nodes(taxdump_dir / "nodes.dmp")
    extra = ancestors_of_roots(nodes, {"2", "2157"})
    assert "131567" in extra   # cellular organisms
    assert "1" in extra        # root
