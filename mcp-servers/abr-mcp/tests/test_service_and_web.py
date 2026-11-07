import asyncio
import json
from pathlib import Path

import httpx
import pytest
from conftest import ABN_CHARITY, ABN_CO, ABN_IND, ABN_TRUST, ACN_CO

from abr_mcp.index import IndexUnavailable, LocalIndex
from abr_mcp.service import AbrService
from abr_mcp.web import AbrWebClient, WebError, parse_jsonp

GUID = "00000000-aaaa-bbbb-cccc-123456789abc"
LIVE_ABN = "51824753556"

ABN_DETAILS = {
    "Abn": LIVE_ABN, "AbnStatus": "Active", "AbnStatusEffectiveFrom": "2000-07-01",
    "Acn": "", "AddressDate": "2020-01-01", "AddressPostcode": "2600", "AddressState": "ACT",
    "BusinessName": ["EXAMPLE TRADING"], "EntityName": "EXAMPLE LIVE ENTITY",
    "EntityTypeCode": "CGE", "EntityTypeName": "Commonwealth Government Entity",
    "Gst": "2000-07-01", "Message": "",
}


def transport(handler):
    calls = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    t = httpx.MockTransport(wrapped)
    t.calls = calls  # type: ignore[attr-defined]
    return t


def jsonp(payload: dict) -> httpx.Response:
    return httpx.Response(200, text=f"callback({json.dumps(payload)})")


def web_client(handler, guid=GUID):
    return AbrWebClient(guid, transport=transport(handler), retries=1)


def no_web():
    return AbrWebClient("")


# ── web client ───────────────────────────────────────────────────────────────


def test_parse_jsonp_and_plain_json():
    assert parse_jsonp('callback({"a": 1});') == {"a": 1}
    assert parse_jsonp(' cb123 ( {"a": [1]} ) ') == {"a": [1]}
    assert parse_jsonp('{"a": 2}') == {"a": 2}
    with pytest.raises(WebError):
        parse_jsonp("<html>oops</html>")


def test_message_is_an_error_and_guid_is_redacted():
    c = web_client(lambda r: jsonp({"Abn": "", "Message": f"The GUID entered ({GUID}) is not recognised"}))
    with pytest.raises(WebError) as exc:
        c.abn_details(LIVE_ABN)
    assert GUID not in str(exc.value) and "REDACTED" in str(exc.value)


def test_transport_errors_retry_then_redact():
    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    c = web_client(boom)
    with pytest.raises(WebError) as exc:
        c.abn_details(LIVE_ABN)
    assert GUID not in str(exc.value)
    assert len(c._transport.calls) == 2  # one retry


def test_redirect_is_not_followed_or_retried():
    c = web_client(lambda r: httpx.Response(302, headers={"Location": "/Error/NotFound"}))
    with pytest.raises(WebError, match="HTTP 302"):
        c.abn_details(LIVE_ABN)
    assert len(c._transport.calls) == 1


def test_request_shape():
    c = web_client(lambda r: jsonp(ABN_DETAILS))
    c.abn_details(LIVE_ABN)
    req = c._transport.calls[0]
    assert req.url.path.endswith("/json/AbnDetails.aspx")
    assert req.url.params["abn"] == LIVE_ABN and req.url.params["guid"] == GUID


# ── service: local ───────────────────────────────────────────────────────────


def svc(db: Path | None, web=None) -> AbrService:
    return AbrService(LocalIndex(db or "/nonexistent/abr.sqlite"), web or no_web())


def test_lookup_local_company(built_index: Path):
    out = svc(built_index).lookup_abn(f"{ABN_CO[:2]} {ABN_CO[2:5]} {ABN_CO[5:8]} {ABN_CO[8:]}")
    assert out["found"]
    r = out["record"]
    assert r["entity_name"] == "EXAMPLE WIDGETS PTY LTD"
    assert r["business_names"] == ["WIDGETS DIRECT"] and r["trading_names"] == ["Widgets & Co"]
    assert r["acn"] == ACN_CO and r["abn_embeds_acn"] and r["acn_checksum_valid"]
    assert r["gst"] == {"status": "ACT", "status_text": r["gst"]["status_text"],
                        "from": "2005-07-01", "registered": True}
    assert r["abn_status_from"] == "2005-07-01"
    assert out["provenance"]["source"] == "abr_bulk_extract"
    assert out["provenance"]["extract_date"] == "2026-10-28"
    assert "CC BY 3.0 AU" in out["provenance"]["licence"]
    assert any("Trading name" in c for c in out["caveats"])


def test_lookup_local_individual_and_dgr(built_index: Path):
    s = svc(built_index)
    ind = s.lookup_abn(ABN_IND)["record"]
    assert ind["individual_name"] == {"title": "MS", "given_names": ["JANE", "ANNE"],
                                      "family_name": "CITIZEN"}
    assert ind["gst"]["registered"] is False and ind["gst"]["status"] == "NON"
    charity = s.lookup_abn(ABN_CHARITY)["record"]
    assert charity["dgr_endorsed"] and len(charity["dgr"]) == 2
    assert "acn" in charity and charity["acn"] == ""
    trust = s.lookup_abn(ABN_TRUST)["record"]
    assert trust["abn_status"] == "CAN" and trust["abn_status_text"] == "Cancelled"


def test_invalid_abn_never_queries(built_index: Path):
    def fail(_):
        raise AssertionError("must not call the web service")

    out = svc(built_index, web_client(fail)).lookup_abn("51 824 753 557")
    assert out == {"found": False, "reason": "invalid_abn", "validation": out["validation"]}


def test_local_miss_complete_index(built_index: Path):
    out = svc(built_index).lookup_abn(LIVE_ABN)
    assert out["reason"] == "not_in_index" and "2026-10-28" in out["detail"]


def test_local_miss_falls_back_to_web(built_index: Path):
    out = svc(built_index, web_client(lambda r: jsonp(ABN_DETAILS))).lookup_abn(LIVE_ABN)
    assert out["found"] and out["provenance"]["source"] == "abr_web_services"
    assert out["record"]["abn_status"] == "ACT" and out["record"]["business_names"] == ["EXAMPLE TRADING"]
    assert "not in local" in out["local_index"]


def test_local_miss_with_web_failure_degrades(built_index: Path):
    def down(_):
        return httpx.Response(503)

    out = svc(built_index, web_client(down)).lookup_abn(LIVE_ABN)
    assert out["found"] is False and out["reason"] == "not_in_index"
    assert "503" in out["web_fallback_error"]


def test_source_local_never_uses_web(built_index: Path):
    def fail(_):
        raise AssertionError("no web")

    assert svc(built_index, web_client(fail)).lookup_abn(LIVE_ABN, "local")["found"] is False


def test_no_backend_is_a_clear_error():
    with pytest.raises(IndexUnavailable, match="No ABR backend"):
        svc(None).lookup_abn(LIVE_ABN)
    with pytest.raises(WebError, match="ABR_GUID"):
        svc(None).lookup_abn(LIVE_ABN, "web")


def test_web_only(tmp_path: Path):
    out = svc(None, web_client(lambda r: jsonp(ABN_DETAILS))).lookup_abn(LIVE_ABN)
    assert out["found"] and out["record"]["entity_name"] == "EXAMPLE LIVE ENTITY"


def test_web_not_registered():
    empty = {**ABN_DETAILS, "Abn": "", "EntityName": ""}
    out = svc(None, web_client(lambda r: jsonp(empty))).lookup_abn(LIVE_ABN)
    assert out["found"] is False and out["reason"] == "not_registered"


def test_batch_lookup_preserves_order_and_reports_invalid(built_index: Path):
    out = svc(built_index).lookup_abns([ABN_CO, "nonsense", LIVE_ABN, ABN_IND])
    assert out["summary"] == {"inputs": 4, "valid": 3, "found": 2}
    assert [r.get("found") for r in out["results"]] == [True, False, False, True]
    assert out["results"][1]["reason"] == "no_digits"
    assert out["results"][0]["entity_name"] == "EXAMPLE WIDGETS PTY LTD"


def test_batch_limits(built_index: Path):
    with pytest.raises(ValueError, match="at most 25"):
        svc(built_index, web_client(lambda r: jsonp(ABN_DETAILS))).lookup_abns([LIVE_ABN] * 26, "web")


def test_lookup_acn(built_index: Path):
    s = svc(built_index)
    out = s.lookup_acn(ACN_CO)
    assert out["found"] and out["records"][0]["abn"] == ABN_CO
    assert s.lookup_acn("004085617")["reason"] == "invalid_acn"
    assert s.lookup_acn("004085616")["reason"] == "no_abn_for_acn_in_index"


def test_search_names_service(built_index: Path):
    out = svc(built_index).search_names("example widgets")
    assert out["results"][0]["abn"] == ABN_CO and out["normalised_key"] == "EXAMPLE WIDGETS"
    assert any("candidates" in c for c in out["caveats"])
    with pytest.raises(ValueError):
        svc(built_index).search_names("x", state="XX")
    with pytest.raises(ValueError):
        svc(built_index).search_names("   ")
    empty = svc(built_index).search_names("Pty Ltd")
    assert empty["count"] == 0 and "legal-form" in empty["note"]


def test_search_web_client_side_filters():
    names = {"Message": "", "Names": [
        {"Abn": LIVE_ABN, "AbnStatus": "0000000001", "IsCurrent": True, "Name": "EXAMPLE",
         "NameType": "Entity Name", "Postcode": "2600", "Score": 100, "State": "ACT"},
        {"Abn": ABN_CO, "AbnStatus": "0000000002", "IsCurrent": False, "Name": "EXAMPLE CO",
         "NameType": "Business Name", "Postcode": "3000", "Score": 90, "State": "VIC"},
    ]}
    s = svc(None, web_client(lambda r: jsonp(names)))
    assert [h["abn"] for h in s.search_names("example", state="ACT")["results"]] == [LIVE_ABN]
    assert len(s.search_names("example", active_only=True)["results"]) == 1


def test_status_and_codes(built_index: Path):
    st = svc(built_index).status()
    assert st["local_index"]["available"] and st["local_index"]["complete"]
    assert st["local_index"]["records"] == 4
    assert st["web_services"]["configured"] is False
    codes = svc(built_index).codes()
    assert "TRD" in codes["name_types"] and any(e["code"] == "PUB" for e in codes["entity_types"])


def test_status_without_index():
    st = svc(None).status()
    assert st["local_index"]["available"] is False


# ── MCP surface ──────────────────────────────────────────────────────────────


def test_mcp_tools_registered_and_callable(built_index: Path, monkeypatch):
    from abr_mcp import server

    monkeypatch.setattr(server, "_service", svc(built_index))
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert tools == {"validate_abn", "validate_acn", "lookup_abn", "lookup_abns", "lookup_acn",
                     "search_names", "register_status", "explain_codes", "build_index"}
    result = asyncio.run(server.mcp.call_tool("lookup_abn", {"abn": ABN_CO}))
    text = json.dumps(result, default=str)
    assert "EXAMPLE WIDGETS PTY LTD" in text


def test_mcp_errors_keep_their_message(monkeypatch):
    """SDKs hide unexpected exceptions; ours must reach the client verbatim."""
    from abr_mcp import server

    monkeypatch.setattr(server, "_service", svc(None))
    with pytest.raises(Exception, match="ABR_GUID"):
        asyncio.run(server.mcp.call_tool("lookup_abn", {"abn": LIVE_ABN, "source": "web"}))
    with pytest.raises(Exception, match="No ABR backend"):
        asyncio.run(server.mcp.call_tool("search_names", {"name": "acme"}))


# ── ABR terms / guidance ─────────────────────────────────────────────────────


def test_trading_names_excluded_from_search_by_default(built_index: Path):
    s = svc(built_index)
    default = s.search_names("janes plumbing")
    assert default["count"] == 0
    assert "TRD" not in default["name_types_searched"]
    assert "not been updated since 2012" in default["trading_names_excluded"]
    opted_in = s.search_names("janes plumbing", name_types=["TRD"])
    assert [h["abn"] for h in opted_in["results"]] == [ABN_IND]
    assert "trading_names_excluded" not in opted_in
    # Lookups still show them, labelled legacy.
    assert s.lookup_abn(ABN_IND)["record"]["trading_names"] == ["JANES PLUMBING"]
    with pytest.raises(ValueError, match="unknown name type"):
        s.search_names("x", name_types=["XYZ"])


def test_web_search_drops_trading_names_by_default():
    names = {"Message": "", "Names": [
        {"Abn": LIVE_ABN, "IsCurrent": True, "Name": "EXAMPLE", "NameType": "Entity Name",
         "Postcode": "2600", "Score": 100, "State": "ACT"},
        {"Abn": ABN_CO, "IsCurrent": True, "Name": "EXAMPLE TRADING", "NameType": "Trading Name",
         "Postcode": "3000", "Score": 95, "State": "VIC"},
    ]}
    s = svc(None, web_client(lambda r: jsonp(names)))
    assert [h["abn"] for h in s.search_names("example")["results"]] == [LIVE_ABN]
    assert len(s.search_names("example", name_types=["MN", "TRD"])["results"]) == 2


def test_unofficial_disclaimer_is_surfaced(built_index: Path):
    from abr_mcp import server

    st = svc(built_index).status()
    assert "not affiliated with, endorsed or approved" in st["disclaimer"]
    assert "not affiliated with or endorsed" in server.INSTRUCTIONS.replace("\n", " ")


def test_web_responses_are_not_persisted(tmp_path: Path, monkeypatch):
    """Agreement: withdrawn data must be deletable; we never store web data."""
    monkeypatch.chdir(tmp_path)
    def handler(request):
        if request.url.path.endswith("MatchingNames.aspx"):
            return jsonp({"Message": "", "Names": []})
        return jsonp(ABN_DETAILS)

    s = svc(None, web_client(handler))
    s.lookup_abn(LIVE_ABN, "web")
    s.search_names("example", source="web")
    assert list(tmp_path.iterdir()) == []
