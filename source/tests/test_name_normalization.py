from taxa_mapping.core.name_normalization import normalize_species_key


def test_parenthetical_authorship_stripped():
    assert normalize_species_key(
        "Ruminococcus bicirculans (ex Wegman et al. 2014)"
    ) == "Ruminococcus bicirculans"


def test_bare_authorship_stripped():
    assert normalize_species_key(
        "Ruminococcus bicirculans ex Wegman et al 2014"
    ) == "Ruminococcus bicirculans"


def test_candidatus_prefix_stripped():
    assert normalize_species_key("Candidatus Cibionibacter quicibialis") == \
        "Cibionibacter quicibialis"


def test_infraspecific_tail_cut():
    assert normalize_species_key("Escherichia coli subsp. foo") == "Escherichia coli"
    assert normalize_species_key("Escherichia coli strain K-12") == "Escherichia coli"


def test_plain_binomial_unchanged():
    assert normalize_species_key("Escherichia coli") == "Escherichia coli"


def test_genus_only_unchanged():
    assert normalize_species_key("Ruminococcus") == "Ruminococcus"


def test_ex_inside_epithet_not_stripped():
    assert normalize_species_key("Genus exiguum") == "Genus exiguum"


def test_empty():
    assert normalize_species_key("") == ""
    assert normalize_species_key(None) == ""
