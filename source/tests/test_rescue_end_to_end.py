from taxa_mapping.tools.taxdump_cache import generate
from taxa_mapping.core.rescue import run_ncbi_rescue


def test_stale_taxon_not_black_with_generated_cache(taxdump_dir, tmp_path):
    cache_path = tmp_path / "ncbi_cache_full.json"
    generate(str(taxdump_dir), str(cache_path), {"2", "2157"}, str(tmp_path / "work"))

    # current name
    out = run_ncbi_rescue(
        [{"taxon": "Phocaeicola vulgatus", "mat_candidates_str": "Phocaeicola_vulgatus_ERR1"}],
        str(cache_path),
    )
    assert out[0]["final_color"] != "black"

    # old name resolves via synonym key
    out_old = run_ncbi_rescue(
        [{"taxon": "Bacteroides vulgatus", "mat_candidates_str": "Phocaeicola_vulgatus_ERR1"}],
        str(cache_path),
    )
    assert out_old[0]["final_color"] != "black"
