"""Live tests against abr.business.gov.au. Opt-in: ``ABR_LIVE=1 pytest -m live``.

Without ``ABR_GUID`` these exercise the real error path (an unregistered GUID
is answered with HTTP 200 + ``Message``). With ``ABR_GUID`` set they also make
real lookups. The ABN used is the ATO's published example.
"""

import os

import pytest

from abr_mcp.index import LocalIndex
from abr_mcp.service import AbrService
from abr_mcp.web import AbrWebClient, WebError

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("ABR_LIVE") != "1", reason="set ABR_LIVE=1 to call the live ABR"),
]

DUMMY_GUID = "00000000-0000-0000-0000-000000000000"
REAL_GUID = os.getenv("ABR_GUID", "").strip()
needs_guid = pytest.mark.skipif(not REAL_GUID, reason="set ABR_GUID for real lookups")


@pytest.mark.parametrize("call", [
    lambda c: c.abn_details("51824753556"),
    lambda c: c.acn_details("004085616"),
    lambda c: c.matching_names("qantas", 2),
])
def test_unregistered_guid_is_reported_and_redacted(call):
    with pytest.raises(WebError) as exc:
        call(AbrWebClient(DUMMY_GUID))
    msg = str(exc.value)
    assert "not recognised as a Registered Party" in msg
    assert DUMMY_GUID not in msg


def test_service_surfaces_web_error_without_index(tmp_path):
    s = AbrService(LocalIndex(tmp_path / "none.sqlite"), AbrWebClient(DUMMY_GUID))
    with pytest.raises(WebError, match="Registered Party"):
        s.lookup_abn("51 824 753 556", source="web")
    # Invalid input never reaches the service.
    assert s.lookup_abn("51 824 753 557", source="web")["reason"] == "invalid_abn"


@needs_guid
def test_real_abn_details():
    out = AbrService(LocalIndex("/nonexistent"), AbrWebClient(REAL_GUID)).lookup_abn("51824753556", "web")
    assert out["found"] and out["record"]["abn"] == "51824753556"
    assert out["record"]["abn_status"] in ("ACT", "CAN")
    assert out["provenance"]["source"] == "abr_web_services"


@needs_guid
def test_real_name_search():
    out = AbrService(LocalIndex("/nonexistent"), AbrWebClient(REAL_GUID)).search_names(
        "qantas airways", limit=3, source="web")
    assert out["count"] >= 1 and all(len(r["abn"]) == 11 for r in out["results"])
