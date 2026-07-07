from taxa_mapping.tools.taxdump_cache import parse_names


def test_parse_names_buckets(taxdump_dir):
    capture = {"821", "909656", "2", "131567"}
    sci, alt, authority = parse_names(taxdump_dir / "names.dmp", capture)
    assert sci["821"] == "Phocaeicola vulgatus"
    assert sci["909656"] == "Phocaeicola"
    assert alt["821"]["synonym"] == ["Bacteroides vulgatus"]
    assert authority["821"] == ["Bacteroides vulgatus (Eggerth and Gagnon 1933)"]


def test_parse_names_excludes_out_of_capture(taxdump_dir):
    capture = {"821"}
    sci, alt, authority = parse_names(taxdump_dir / "names.dmp", capture)
    assert "9606" not in sci
    assert "2173" not in sci
