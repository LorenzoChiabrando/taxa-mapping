from taxa_mapping.tools import taxdump_cache


def test_module_imports_and_constants():
    assert taxdump_cache.DEFAULT_CLADES == {"2", "2157"}
    assert taxdump_cache.TAXDUMP_URL.endswith("taxdump.tar.gz")


def test_taxdump_fixture_writes_dmp(taxdump_dir):
    assert (taxdump_dir / "nodes.dmp").exists()
    assert (taxdump_dir / "names.dmp").exists()
    assert (taxdump_dir / "merged.dmp").exists()
