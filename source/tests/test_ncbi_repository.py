import json

from taxa_mapping.tools.taxdump_cache import build_cache
from taxa_mapping.infrastructure.ncbi_repository import NcbiRepository


def _rec(taxid, sci, rank="species"):
    return {
        "TaxId": taxid,
        "ScientificName": sci,
        "ParentTaxId": "",
        "Rank": rank,
        "OtherNames": {"Synonym": [], "GenbankSynonym": [], "EquivalentName": [],
                       "Includes": [], "Name": []},
        "Lineage": "",
        "LineageEx": [],
        "AkaTaxIds": [],
        "MergedTaxIds": [],
    }


def _repo_from_records(tmp_path, records):
    cache = build_cache(records)
    p = tmp_path / "cache.json"
    p.write_text(json.dumps(cache), encoding="utf-8")
    return NcbiRepository(str(p))


def test_bare_authorship_input_resolves_to_species(tmp_path):
    # species indexed under an authored name, queried with bare authorship
    records = {"2364881": _rec("2364881", "Ruminococcus bicirculans (ex Wegman et al. 2014)")}
    repo = _repo_from_records(tmp_path, records)

    recs = repo.fetch_records("Ruminococcus bicirculans ex Wegman et al 2014")
    assert recs and recs[0]["TaxId"] == "2364881"


def test_plain_binomial_still_resolves(tmp_path):
    records = {"562": _rec("562", "Escherichia coli")}
    repo = _repo_from_records(tmp_path, records)
    assert repo.fetch_records("Escherichia coli")[0]["TaxId"] == "562"


def test_exact_key_takes_priority_over_alias(tmp_path):
    # a real genus name must not be shadowed by a species alias
    records = {
        "1263": _rec("1263", "Ruminococcus", rank="genus"),
        "2364881": _rec("2364881", "Ruminococcus bicirculans (ex Wegman et al. 2014)"),
    }
    repo = _repo_from_records(tmp_path, records)
    assert repo.fetch_records("Ruminococcus")[0]["TaxId"] == "1263"
