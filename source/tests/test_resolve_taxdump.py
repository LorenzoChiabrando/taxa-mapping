import tarfile
from taxa_mapping.tools.taxdump_cache import resolve_taxdump, parse_nodes


def test_resolve_local_directory(taxdump_dir, tmp_path):
    resolved = resolve_taxdump(str(taxdump_dir), str(tmp_path / "work"))
    assert (resolved / "nodes.dmp").exists()
    assert parse_nodes(resolved / "nodes.dmp")["821"] == ("909656", "species")


def test_resolve_local_tarball(taxdump_dir, tmp_path):
    archive = tmp_path / "taxdump.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name in ("nodes.dmp", "names.dmp", "merged.dmp"):
            tf.add(taxdump_dir / name, arcname=name)
    resolved = resolve_taxdump(str(archive), str(tmp_path / "work"))
    assert (resolved / "names.dmp").exists()
    assert parse_nodes(resolved / "nodes.dmp")["2173"] == ("2172", "species")
