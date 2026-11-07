import io
import sqlite3
import zipfile
from pathlib import Path

import pytest
from conftest import (
    ABN_CHARITY,
    ABN_CO,
    ABN_IND,
    ABN_TRUST,
    ABR_CHARITY,
    ABR_IND,
    ABR_TRUST,
    ACN_CO,
    ALL_RECORDS,
    abr_company,
    extract_xml,
    write_full_extract,
)

from abr_mcp.bulk import NotABulkExtract, discover_sources, iter_extract, records_from
from abr_mcp.index import BuildError, LocalIndex, build_index


def parse(records):
    return records_from(io.BytesIO(extract_xml(records).encode()))


# ── parser ──────────────────────────────────────────────────────────────────


def test_parse_company():
    info, [rec] = parse([abr_company()])
    assert info.file_sequence_number == "1" and info.record_count == "1"
    r = rec.record
    assert r["abn"] == ABN_CO and r["abn_status"] == "ACT"
    assert r["display_name"] == "EXAMPLE WIDGETS PTY LTD" and r["name_type"] == "MN"
    assert r["asic_number"] == ACN_CO and r["gst_status"] == "ACT"
    assert r["state"] == "VIC" and r["postcode"] == "3000"
    assert rec.names == [("MN", "EXAMPLE WIDGETS PTY LTD"), ("BN", "WIDGETS DIRECT"),
                         ("TRD", "Widgets & Co")]


def test_parse_individual():
    _, [rec] = parse([ABR_IND])
    r = rec.record
    assert (r["name_title"], r["given_name_1"], r["given_name_2"], r["family_name"]) == \
        ("MS", "JANE", "ANNE", "CITIZEN")
    assert r["display_name"] == "JANE ANNE CITIZEN" and r["name_type"] == "LGL"
    assert r["gst_status"] == "NON"


def test_parse_absent_optionals_are_empty_strings():
    _, [rec] = parse([ABR_TRUST])
    r = rec.record
    assert r["abn_status"] == "CAN" and r["replaced"] == "Y"
    assert r["asic_number"] == r["gst_status"] == r["state"] == r["postcode"] == ""
    assert all(isinstance(v, str) for v in r.values())


def test_parse_dgr_without_name_and_empty_asic():
    _, [rec] = parse([ABR_CHARITY])
    assert rec.record["asic_number"] == ""
    assert rec.dgr == [("20010101", "", ""), ("20120101", "ACT", "KOALA RESCUE PUBLIC FUND")]
    assert ("DGR", "KOALA RESCUE PUBLIC FUND") in rec.names


def test_wrong_root_rejected():
    with pytest.raises(NotABulkExtract):
        list(iter_extract(io.BytesIO(b"<Business><ABN>1</ABN></Business>")))


def test_discover_sources(tmp_path: Path):
    write_full_extract(tmp_path / "x")
    z = write_full_extract(tmp_path / "z", as_zip=True)
    assert len(discover_sources([tmp_path / "x"])) == 20
    srcs = discover_sources([z])
    assert len(srcs) == 20 and srcs[0].member == "20261028Public01.xml"
    with pytest.raises(FileNotFoundError):
        discover_sources([tmp_path / "missing"])


# ── build ───────────────────────────────────────────────────────────────────


def test_build_complete_from_directory(built_index: Path):
    idx = LocalIndex(built_index)
    meta = idx.meta()
    assert meta["complete"] == "1" and meta["record_count"] == "4"
    assert meta["extract_dates"] == "2026-10-28"
    assert {s["status"] for s in idx.sources()} == {"loaded"}


def test_build_from_zip_streams_members(tmp_path: Path):
    z = write_full_extract(tmp_path / "z", ALL_RECORDS, as_zip=True)
    rep = build_index([z], tmp_path / "abr.sqlite")
    assert rep.complete and rep.record_count == 4


def test_missing_files_fail_unless_partial(tmp_path: Path):
    one = tmp_path / "20261028Public01.xml"
    one.write_text(extract_xml([ABR_IND]))
    db = tmp_path / "abr.sqlite"
    with pytest.raises(BuildError, match="missing file sequence"):
        build_index([one], db)
    assert not db.exists()
    rep = build_index([one], db, allow_partial=True)
    assert not rep.complete and rep.missing_sequence_numbers == list(range(2, 21))
    assert LocalIndex(db).meta()["complete"] == "0"


def test_truncated_file_fails_and_keeps_existing_index(tmp_path: Path, built_index: Path):
    before = built_index.read_bytes()
    src = write_full_extract(tmp_path / "bad", ALL_RECORDS)
    # Declares 3 records, contains 2: a truncated download.
    (src / "20261028Public01.xml").write_text(
        extract_xml([abr_company(), ABR_IND], seq=1, declared=3))
    with pytest.raises(BuildError, match="declares 3"):
        build_index([src], built_index)
    assert built_index.read_bytes() == before
    assert not list(built_index.parent.glob("*.building-*"))


def test_malformed_file_isolated_with_allow_partial(tmp_path: Path):
    src = write_full_extract(tmp_path / "bad", ALL_RECORDS)
    (src / "20261028Public02.xml").write_text(extract_xml([ABR_TRUST], seq=2)[:-40])
    rep = build_index([src], tmp_path / "abr.sqlite", allow_partial=True)
    failed = [s for s in rep.sources if s.status == "failed"]
    assert len(failed) == 1 and "ParseError" in failed[0].error
    assert rep.missing_sequence_numbers == [2] and not rep.complete
    idx = LocalIndex(tmp_path / "abr.sqlite")
    assert idx.get_by_abn(ABN_TRUST) is None  # partial rows were removed
    assert idx.get_by_abn(ABN_CO) is not None


def test_transfer_error_attribute_fails_file(tmp_path: Path):
    src = write_full_extract(tmp_path / "e", ALL_RECORDS)
    (src / "20261028Public20.xml").write_text(extract_xml([ABR_CHARITY], seq=20, error="true"))
    with pytest.raises(BuildError, match="Transfer error"):
        build_index([src], tmp_path / "abr.sqlite")


def test_same_file_twice_is_skipped_not_double_counted(tmp_path: Path):
    src = write_full_extract(tmp_path / "x", ALL_RECORDS)
    z = write_full_extract(tmp_path / "z", ALL_RECORDS, as_zip=True)
    rep = build_index([src, z], tmp_path / "abr.sqlite")
    assert rep.record_count == 4
    assert sum(s.status == "skipped_duplicate" for s in rep.sources) == 20


def test_duplicate_abn_keeps_latest_record(tmp_path: Path):
    old = abr_company(updated="20200101", name="OLD NAME PTY LTD")
    new = abr_company(updated="20260601", name="NEW NAME PTY LTD")
    src = write_full_extract(tmp_path / "d", {1: [new], 7: [old]})
    rep = build_index([src], tmp_path / "abr.sqlite")
    assert rep.duplicates_resolved == 1 and rep.record_count == 1
    idx = LocalIndex(tmp_path / "abr.sqlite")
    rec = idx.get_by_abn(ABN_CO)
    assert rec["display_name"] == "NEW NAME PTY LTD"
    assert ("MN", "OLD NAME PTY LTD") not in rec["names"]
    assert idx.search("old name", mode="tokens")["results"] == []


def test_mixed_extract_dates_warned(tmp_path: Path):
    src = write_full_extract(tmp_path / "m", ALL_RECORDS)
    (src / "20261028Public05.xml").write_text(extract_xml([], seq=5, extract_time="2026-09-01T00:00:00"))
    rep = build_index([src], tmp_path / "abr.sqlite")
    assert any("different extracts" in w for w in rep.warnings)


def test_index_opened_read_only(built_index: Path):
    con = LocalIndex(built_index)._connect()
    with pytest.raises(sqlite3.OperationalError):
        con.execute("DELETE FROM records")
    con.close()


# ── queries ─────────────────────────────────────────────────────────────────


def test_get_by_abn_and_acn(built_index: Path):
    idx = LocalIndex(built_index)
    rec = idx.get_by_abn(ABN_CO)
    assert rec["display_name"] == "EXAMPLE WIDGETS PTY LTD"
    assert ("BN", "WIDGETS DIRECT") in rec["names"]
    assert idx.get_by_abn("51824753556") is None
    assert [r["abn"] for r in idx.get_by_acn(ACN_CO)] == [ABN_CO]
    # The empty-ASIC charity is not findable by an empty ACN.
    assert idx.get_by_acn("") == []


def test_acn_query_uses_partial_index(built_index: Path):
    con = LocalIndex(built_index)._connect()
    sql = "SELECT * FROM records WHERE asic_number = ? AND asic_number <> ''"
    plan = " ".join(str(r[3]) for r in con.execute(f"EXPLAIN QUERY PLAN {sql}", (ACN_CO,)))
    con.close()
    assert "records_acn" in plan


def test_get_many(built_index: Path):
    found = LocalIndex(built_index).get_many([ABN_CO, ABN_IND, ABN_CO, "51824753556"])
    assert set(found) == {ABN_CO, ABN_IND}


def test_search_exact_ignores_legal_form(built_index: Path):
    out = LocalIndex(built_index).search("Example Widgets Proprietary Limited", mode="exact")
    [hit] = out["results"]
    assert hit["abn"] == ABN_CO and hit["match"] == "exact_name"


def test_search_tokens_prefix_and_grouping(built_index: Path):
    out = LocalIndex(built_index).search("widg", mode="tokens")
    [hit] = out["results"]  # three names, one ABN
    assert hit["abn"] == ABN_CO and hit["match"] == "all_tokens"
    assert len(hit["matched_names"]) == 3


def test_search_filters(built_index: Path):
    idx = LocalIndex(built_index)
    assert idx.search("widgets", state="NSW")["results"] == []
    assert idx.search("example", active_only=True)["results"][0]["abn"] == ABN_CO
    trust = idx.search("example family trust")["results"]
    assert [h["abn"] for h in trust] == [ABN_TRUST]
    assert idx.search("example family trust", active_only=True)["results"] == []
    bn_only = idx.search("widgets", name_types=["BN"])["results"]
    assert bn_only[0]["matched_names"] == [{"name_type": "BN", "name": "WIDGETS DIRECT"}]


def test_search_accent_insensitive(built_index: Path):
    hits = LocalIndex(built_index).search("societe")["results"]
    assert hits and hits[0]["abn"] == ABN_CHARITY


def test_search_without_fts(tmp_path: Path):
    src = write_full_extract(tmp_path / "x", ALL_RECORDS)
    build_index([src], tmp_path / "abr.sqlite", fts=False)
    hits = LocalIndex(tmp_path / "abr.sqlite").search("widgets direct", mode="tokens")["results"]
    assert hits[0]["abn"] == ABN_CO


def test_entity_types_derived_from_data(built_index: Path):
    codes = {e["code"]: e["description"] for e in LocalIndex(built_index).entity_types()}
    assert codes["PRV"] == "Australian Private Company" and codes["IND"] == "Individual/Sole Trader"


def test_zip_with_bad_member_is_isolated(tmp_path: Path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for seq in range(1, 21):
            body = extract_xml(ALL_RECORDS.get(seq, []), seq=seq)
            zf.writestr(f"20261028Public{seq:02d}.xml", body if seq != 20 else "<notxml")
    rep = build_index([z], tmp_path / "abr.sqlite", allow_partial=True)
    assert rep.missing_sequence_numbers == [20]
