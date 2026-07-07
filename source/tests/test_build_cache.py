from taxa_mapping.tools.taxdump_cache import build_cache
from taxa_mapping.core import ncbi_scoring


def _rec(taxid, sci, synonyms=None, merged=None):
    return {
        "TaxId": taxid,
        "ScientificName": sci,
        "ParentTaxId": "",
        "Rank": "species",
        "OtherNames": {
            "Synonym": synonyms or [],
            "GenbankSynonym": [],
            "EquivalentName": [],
            "Includes": [],
            "Name": [],
        },
        "Lineage": "",
        "LineageEx": [],
        "AkaTaxIds": [],
        "MergedTaxIds": merged or [],
    }


def test_scientific_and_synonym_keys():
    records = {"821": _rec("821", "Phocaeicola vulgatus", synonyms=["Bacteroides vulgatus"])}
    cache = build_cache(records)
    assert cache["TAX::Phocaeicola vulgatus"][0]["TaxId"] == "821"
    assert cache["TAX::Bacteroides vulgatus"][0]["TaxId"] == "821"


def test_scientific_name_wins_over_colliding_synonym():
    records = {
        "821": _rec("821", "Phocaeicola vulgatus"),
        "999": _rec("999", "Other species", synonyms=["Phocaeicola vulgatus"]),
    }
    cache = build_cache(records)
    # the scientific-name owner (821) must win the shared key
    assert cache["TAX::Phocaeicola vulgatus"][0]["TaxId"] == "821"


def test_revived_name_gets_clean_binomial_alias():
    # authored scientific name must also be indexed under its clean binomial
    records = {"2364881": _rec("2364881", "Ruminococcus bicirculans (ex Wegman et al. 2014)")}
    cache = build_cache(records)
    assert cache["TAX::Ruminococcus bicirculans (ex Wegman et al. 2014)"][0]["TaxId"] == "2364881"
    assert cache["TAX::Ruminococcus bicirculans"][0]["TaxId"] == "2364881"


def test_alias_does_not_overwrite_real_key():
    # a real scientific-name/synonym key must win over a colliding alias
    records = {
        "111": _rec("111", "Ruminococcus bicirculans"),                        # real binomial
        "222": _rec("222", "Ruminococcus bicirculans (ex Wegman et al. 2014)"),  # would alias to same
    }
    cache = build_cache(records)
    assert cache["TAX::Ruminococcus bicirculans"][0]["TaxId"] == "111"


def test_alias_collision_is_deterministic_lowest_taxid_wins():
    # two decorated names collapsing to the same binomial -> lowest taxid wins
    records = {
        "300": _rec("300", "Ruminococcus bicirculans (ex Liu et al. 2021)"),
        "200": _rec("200", "Ruminococcus bicirculans (ex Wegman et al. 2014)"),
    }
    cache = build_cache(records)
    assert cache["TAX::Ruminococcus bicirculans"][0]["TaxId"] == "200"


def test_ids_key_matches_expand_with_aka_merged():
    records = {"821": _rec("821", "Phocaeicola vulgatus", merged=["76856"])}
    cache = build_cache(records)
    assert "IDS::76856" in cache

    base = ncbi_scoring.parse_tax_record(records["821"])
    fetched = ncbi_scoring.cache_fetch_by_taxids(base["merged_taxids"], cache)
    assert fetched and fetched[0]["TaxId"] == "821"
    # expand must run without error and return the record's own synonym set
    expanded = ncbi_scoring.expand_with_aka_merged(base, cache)
    assert isinstance(expanded["synonyms"], list)
