from conftest import ABN_CO, ACN_CO, make_abn

from abr_mcp.identifiers import (
    abn_is_valid,
    acn_is_valid,
    format_abn,
    normalise_abn,
    normalise_acn,
    validate_abn,
    validate_acn,
)
from abr_mcp.names import fts_query, name_key

# Published worked examples (ATO ABN format guide; ASIC ACN check-digit guide).
ATO_EXAMPLE_ABN = "51824753556"
ASIC_EXAMPLE_ACNS = ("000000019", "004085616", "010499966", "006249976")


def test_published_examples_pass():
    assert abn_is_valid(ATO_EXAMPLE_ABN)
    for acn in ASIC_EXAMPLE_ACNS:
        assert acn_is_valid(acn), acn


def test_single_digit_change_fails_checksum():
    for i in range(11):
        d = list(ATO_EXAMPLE_ABN)
        d[i] = str((int(d[i]) + 1) % 10)
        assert not abn_is_valid("".join(d))


def test_generated_fixture_identifiers_are_valid():
    assert abn_is_valid(ABN_CO) and acn_is_valid(ACN_CO)
    assert ABN_CO[2:] == ACN_CO
    assert abn_is_valid(make_abn("999999999"))


def test_formats_are_normalised():
    for raw in ("51 824 753 556", "ABN: 51-824-753-556", "51.824.753.556", 51824753556,
                "51824753556.0", "5.1824753556E+10", 51824753556.0):
        v = validate_abn(raw)
        assert v["valid"], raw
        assert v["abn"] == ATO_EXAMPLE_ABN
        assert v["formatted"] == "51 824 753 556"
    assert format_abn(ATO_EXAMPLE_ABN) == "51 824 753 556"
    assert normalise_abn(" 51 824 753 556 ") == ATO_EXAMPLE_ABN
    assert normalise_abn("51 824 753 557") == ""


def test_invalid_reasons():
    assert validate_abn("")["reason"] == "no_digits"
    assert validate_abn(None)["reason"] == "no_digits"
    assert validate_abn("1234")["reason"] == "too_few_digits"
    assert validate_abn("518247535561")["reason"] == "too_many_digits"
    assert validate_abn("01824753556")["reason"] == "leading_zero_not_permitted"
    assert validate_abn("51824753557")["reason"] == "checksum_failed"
    # Womblex's synthetic test ABNs are not checksum-valid; neither is a placeholder.
    assert validate_abn("11111111111")["reason"] == "checksum_failed"


def test_two_identifiers_in_one_cell_flagged():
    v = validate_abn(f"{ATO_EXAMPLE_ABN} / {ATO_EXAMPLE_ABN}")
    assert not v["valid"] and "may_contain_two_identifiers" in v["notes"]


def test_acn_passed_as_abn_noted():
    assert "looks_like_acn" in validate_abn("004 085 616")["notes"]


def test_acn_validation():
    v = validate_acn("004 085 616")
    assert v["valid"] and v["acn"] == "004085616" and v["formatted"] == "004 085 616"
    assert validate_acn("004085617")["reason"] == "checksum_failed"
    assert normalise_acn("004-085-616") == "004085616"


def test_acn_leading_zero_loss_reported_not_assumed():
    v = validate_acn(4085616)  # spreadsheet ate "00"
    assert not v["valid"]
    assert v["reason"] == "too_few_digits"
    assert "possible_leading_zero_loss" in v["notes"]
    assert v["zero_padded_candidate"] == "004085616"


def test_abn_passed_as_acn_yields_embedded_acn():
    v = validate_acn(ABN_CO)
    assert not v["valid"]
    assert "abn_embeds_valid_acn" in v["notes"]
    assert v["acn_from_abn_suffix"] == ACN_CO


def test_name_key():
    assert name_key("The Trustee for Acme Pty. Ltd.") == "ACME"
    assert name_key("ACME PTY LTD") == "ACME"
    assert name_key("Acme P/L") == "ACME"
    assert name_key("S & S Kare") == name_key("S AND S KARE") == "S AND S KARE"
    assert name_key("Société Générale") == "SOCIETE GENERALE"
    # Geography and CO are kept: they distinguish real entities.
    assert name_key("Acme Australia Pty Ltd") == "ACME AUSTRALIA"
    assert name_key("Acme Co") == "ACME CO"
    assert name_key(None) == "" and name_key("  ") == ""
    # A name made only of legal-form words collapses to empty.
    assert name_key("Pty Ltd") == ""


def test_fts_query_quotes_tokens():
    assert fts_query('acme "widgets" pty') == '"ACME"* AND "WIDGETS"*'
    assert fts_query("Pty Ltd") == ""
