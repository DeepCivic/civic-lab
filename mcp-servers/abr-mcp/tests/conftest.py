"""Synthetic bulk-extract fixtures.

All records are fabricated: names are invented and identifiers are generated
to pass their check digits. No real register data is committed.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from abr_mcp.identifiers import ABN_WEIGHTS, ACN_WEIGHTS


def make_acn(body8: str) -> str:
    total = sum(w * int(d) for w, d in zip(ACN_WEIGHTS, body8))
    return body8 + str((10 - total % 10) % 10)


def make_abn(body9: str) -> str:
    """Prefix a 9-digit body with the 2 digits that make a valid ABN."""
    for prefix in range(10, 100):
        digits = [int(c) for c in f"{prefix}{body9}"]
        digits[0] -= 1
        if sum(w * d for w, d in zip(ABN_WEIGHTS, digits)) % 89 == 0:
            return f"{prefix}{body9}"
    raise AssertionError("unreachable")


ACN_CO = make_acn("12345678")
ABN_CO = make_abn(ACN_CO)  # company ABN embeds its ACN
ABN_IND = make_abn("500000001")
ABN_TRUST = make_abn("500000002")
ABN_CHARITY = make_abn("500000003")


def abr_company(abn: str = ABN_CO, acn: str = ACN_CO, updated: str = "20260301",
                name: str = "EXAMPLE WIDGETS PTY LTD", status: str = "ACT") -> str:
    return (
        f'<ABR recordLastUpdatedDate="{updated}" replaced="N">'
        f'<ABN status="{status}" ABNStatusFromDate="20050701">{abn}</ABN>'
        "<EntityType><EntityTypeInd>PRV</EntityTypeInd>"
        "<EntityTypeText>Australian Private Company</EntityTypeText></EntityType>"
        f'<MainEntity><NonIndividualName type="MN"><NonIndividualNameText>{name}'
        "</NonIndividualNameText></NonIndividualName>"
        "<BusinessAddress><AddressDetails><State>VIC</State><Postcode>3000</Postcode>"
        "</AddressDetails></BusinessAddress></MainEntity>"
        f'<ASICNumber ASICNumberType="undetermined">{acn}</ASICNumber>'
        '<GST status="ACT" GSTStatusFromDate="20050701" />'
        '<OtherEntity><NonIndividualName type="BN"><NonIndividualNameText>WIDGETS DIRECT'
        "</NonIndividualNameText></NonIndividualName></OtherEntity>"
        '<OtherEntity><NonIndividualName type="TRD"><NonIndividualNameText>Widgets &amp; Co'
        "</NonIndividualNameText></NonIndividualName></OtherEntity>"
        "</ABR>"
    )


ABR_IND = (
    '<ABR recordLastUpdatedDate="20260215" replaced="N">'
    f'<ABN status="ACT" ABNStatusFromDate="20100401">{ABN_IND}</ABN>'
    "<EntityType><EntityTypeInd>IND</EntityTypeInd>"
    "<EntityTypeText>Individual/Sole Trader</EntityTypeText></EntityType>"
    '<LegalEntity><IndividualName type="LGL"><NameTitle>MS</NameTitle>'
    "<GivenName>JANE</GivenName><GivenName>ANNE</GivenName><FamilyName>CITIZEN</FamilyName>"
    "</IndividualName><BusinessAddress><AddressDetails><State>NSW</State>"
    "<Postcode>2000</Postcode></AddressDetails></BusinessAddress></LegalEntity>"
    '<GST status="NON" GSTStatusFromDate="19000101" />'
    '<OtherEntity><NonIndividualName type="TRD"><NonIndividualNameText>JANES PLUMBING'
    "</NonIndividualNameText></NonIndividualName></OtherEntity>"
    "</ABR>"
)

# Cancelled trust: no ASIC, no GST, empty State, no given names.
ABR_TRUST = (
    '<ABR recordLastUpdatedDate="20190501" replaced="Y">'
    f'<ABN status="CAN" ABNStatusFromDate="20190501">{ABN_TRUST}</ABN>'
    "<EntityType><EntityTypeInd>DIT</EntityTypeInd>"
    "<EntityTypeText>Discretionary Investment Trust</EntityTypeText></EntityType>"
    '<MainEntity><NonIndividualName type="MN">'
    "<NonIndividualNameText>The Trustee for Example Family Trust</NonIndividualNameText>"
    "</NonIndividualName><BusinessAddress><AddressDetails><State></State>"
    "<Postcode></Postcode></AddressDetails></BusinessAddress></MainEntity>"
    "</ABR>"
)

# Charity: empty ASICNumber, DGR with no name/status (self-closed) and a named fund.
ABR_CHARITY = (
    '<ABR recordLastUpdatedDate="20250101" replaced="N">'
    f'<ABN status="ACT" ABNStatusFromDate="20000101">{ABN_CHARITY}</ABN>'
    "<EntityType><EntityTypeInd>PUB</EntityTypeInd>"
    "<EntityTypeText>Australian Public Company</EntityTypeText></EntityType>"
    '<MainEntity><NonIndividualName type="MN"><NonIndividualNameText>'
    "Koala Rescue Société Limited</NonIndividualNameText></NonIndividualName>"
    "<BusinessAddress><AddressDetails><State>QLD</State><Postcode>4000</Postcode>"
    "</AddressDetails></BusinessAddress></MainEntity>"
    '<ASICNumber ASICNumberType="undetermined"></ASICNumber>'
    '<DGR DGRStatusFromDate="20010101" />'
    '<DGR status="ACT" DGRStatusFromDate="20120101"><NonIndividualName type="DGR">'
    "<NonIndividualNameText>KOALA RESCUE PUBLIC FUND</NonIndividualNameText>"
    "</NonIndividualName></DGR>"
    "</ABR>"
)


def extract_xml(records: list[str], seq: int = 1, declared: int | None = None,
                extract_time: str = "2026-10-28T12:00:00", error: str = "none") -> str:
    count = len(records) if declared is None else declared
    return (
        f'<?xml version="1.0"?><Transfer error="{error}">'
        f"<TransferInfo><FileSequenceNumber>{seq}</FileSequenceNumber>"
        f"<RecordCount>{count}</RecordCount><ExtractTime>{extract_time}</ExtractTime>"
        "</TransferInfo>\n" + "\n".join(records) + "</Transfer>"
    )


def write_full_extract(directory: Path, per_file: dict[int, list[str]] | None = None,
                       as_zip: bool = False) -> Path:
    """Write all 20 sequence files (most empty) so the build counts as complete."""
    directory.mkdir(parents=True, exist_ok=True)
    per_file = per_file or {}
    files = {
        f"20261028Public{seq:02d}.xml": extract_xml(per_file.get(seq, []), seq=seq)
        for seq in range(1, 21)
    }
    if as_zip:
        path = directory / "public_split_1_20.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, body in files.items():
                zf.writestr(name, body)
        return path
    for name, body in files.items():
        (directory / name).write_text(body, encoding="utf-8")
    return directory


ALL_RECORDS = {1: [abr_company(), ABR_IND], 2: [ABR_TRUST], 20: [ABR_CHARITY]}


@pytest.fixture()
def built_index(tmp_path: Path) -> Path:
    from abr_mcp.index import build_index

    src = write_full_extract(tmp_path / "extract", ALL_RECORDS)
    db = tmp_path / "abr.sqlite"
    build_index([src], db)
    return db
