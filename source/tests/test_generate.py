import json
from taxa_mapping.tools.taxdump_cache import generate


def test_generate_writes_expected_keys(taxdump_dir, tmp_path):
    out = tmp_path / "ncbi_cache_full.json"
    stats = generate(str(taxdump_dir), str(out), {"2", "2157"}, str(tmp_path / "work"))
    assert out.exists()

    cache = json.loads(out.read_text(encoding="utf-8"))
    assert "TAX::Phocaeicola vulgatus" in cache        # bacterium (current name)
    assert "TAX::Bacteroides vulgatus" in cache         # synonym resolves
    assert "TAX::Methanobrevibacter smithii" in cache   # archaeon
    assert "TAX::Homo sapiens" not in cache             # eukaryote excluded
    assert "IDS::76856" in cache                         # merged id index

    assert stats["records"] >= 4
    assert stats["ids_keys"] == 1
