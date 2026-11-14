import pytest
from conftest import ABF_ROWS, DFAT_ROWS, abf_payload, dfat_row, make_xlsx

from sanctions_au import abf, dfat
from sanctions_au.store import DatasetError
from sanctions_au.xlsx import XlsxError, read_first_sheet


def test_xlsx_reads_strings_numbers_and_booleans(tmp_path):
    name, rows = read_first_sheet(make_xlsx(tmp_path / "a.xlsx", DFAT_ROWS))
    assert name.startswith("Consolidated List")
    header = rows[0]
    assert rows[1][header.index("Reference")] == 1 and rows[1][header.index("Travel Ban")] is True


def test_xlsx_rejects_non_workbook(tmp_path):
    (tmp_path / "x.xlsx").write_bytes(b"not a zip")
    with pytest.raises(XlsxError):
        read_first_sheet(tmp_path / "x.xlsx")


def test_dfat_groups_aliases_under_one_listing(tmp_path):
    records, facts = dfat.parse(make_xlsx(tmp_path / "a.xlsx", DFAT_ROWS))
    assert len(records) == 4 and facts["list_date"] == "2026-11-13" and facts["name_rows"] == 6
    kellan = next(r for r in records if r["id"] == "1")
    assert kellan["name"] == "Kellan DRESDORF" and kellan["citizenship"] == "Freedonia"
    assert [(a["kind"], a["strength"]) for a in kellan["aliases"]] == [("alias", "strong"), ("original_script", None)]
    assert kellan["control_date"] == "2025-01-01" and kellan["measures"]["travel_ban"] is True
    assert next(r for r in records if r["type"] == "Vessel")["imo"] == "9999991"


def test_dfat_refuses_a_changed_layout(tmp_path):
    with pytest.raises(DatasetError, match="columns are missing: Citizenship"):
        dfat.parse(make_xlsx(tmp_path / "a.xlsx", DFAT_ROWS, header=[h for h in dfat.REQUIRED if h != "Citizenship"]))


@pytest.mark.parametrize("rows, message", [
    ([dfat_row("1a", "Only An Alias", name_type="Alias")], "no primary name"),
    ([dfat_row(1, "A Person", name_type="Nickname")], "unrecognised"),
    ([dfat_row(1, "A Person"), dfat_row(1, "Another", name_type="Primary Name")], "two primary names"),
    ([dfat_row("x9", "A Person")], "does not start with a number"),
])
def test_dfat_refuses_rows_it_does_not_understand(tmp_path, rows, message):
    with pytest.raises(DatasetError, match=message):
        dfat.parse(make_xlsx(tmp_path / "a.xlsx", rows))


def test_abf_normalises_and_flags_pending_review():
    records = abf.parse(abf_payload())
    by_name = {r["sponsor_name"]: r for r in records}
    pending = by_name["Brackenridge Hospitality Pty Ltd"]
    assert pending["pending_review"] and pending["state"] == "NSW"
    assert pending["infringement_notice_status"] == "unpaid" and pending["obligations_breached"] == ["2.86"]
    first = by_name["Quillfeather Staffing Pty Ltd"]
    assert not first["pending_review"] and first["sanction_imposed_date"] == "2020-01-15"
    assert first["sanction_end_date"] == "2025-01-15" and first["obligations_breached"] == ["2.79", "2.82"]
    assert by_name["Dresdorf, Kellan"]["sanction_imposed_date"] is None


def test_abf_record_id_follows_content():
    a = {r["sponsor_name"]: r["id"] for r in abf.parse(abf_payload())}
    edited = [dict(ABF_ROWS[0], postcode="3001"), *ABF_ROWS[1:]]
    b = {r["sponsor_name"]: r["id"] for r in abf.parse(abf_payload(edited))}
    assert a["Brackenridge Hospitality Pty Ltd"] == b["Brackenridge Hospitality Pty Ltd"]
    assert a["Quillfeather Staffing Pty Ltd"] != b["Quillfeather Staffing Pty Ltd"]


@pytest.mark.parametrize("raw", [b"<html>", b'{"d": {"success": false, "data": []}}',
                                 b'{"d": {"success": true, "data": [{"sponsorname": "x"}]}}'])
def test_abf_refuses_an_unexpected_response(raw):
    with pytest.raises(DatasetError):
        abf.parse(raw)


def test_abf_fetch_makes_the_pages_own_two_requests():
    import httpx
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, text='<input type="hidden" name="__REQUESTDIGEST" id="__REQUESTDIGEST" value="0xABC,14 Nov 2026" />')
        return httpx.Response(200, content=abf_payload())

    with httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": abf.USER_AGENT}) as client:
        assert abf.parse(abf.fetch(client))
    assert [r.method for r in seen] == ["GET", "POST"] and len(seen) == 2
    assert seen[1].headers["x-requestdigest"] == "0xABC,14 Nov 2026" and seen[1].content == b"{}"
    assert "sanctions-au" in seen[1].headers["user-agent"]


def test_abf_fetch_stops_if_the_page_no_longer_carries_a_digest():
    import httpx
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html></html>"))) as client:
        with pytest.raises(DatasetError, match="request digest"):
            abf.fetch(client)
