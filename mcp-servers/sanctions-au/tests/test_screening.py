import datetime as dt
import json
import socket

import pytest

from sanctions_au import store
from sanctions_au.service import MAX_BATCH, Screener, Subject


def screen(root, sources="all", **subject):
    return Screener(root).screen(Subject(**subject), sources)


def top(result, source="dfat"):
    return result[source]["matches"][0]


def test_name_alone_never_reaches_high(root):
    m = top(screen(root, name="Kellan Dresdorf"))
    assert m["record"]["name"] == "Kellan DRESDORF" and m["confidence"] == "medium"
    assert m["matched_on"][0]["method"].startswith("same name")


def test_corroboration_raises_and_a_conflict_lowers(root):
    agree = top(screen(root, name="Kellan Dresdorf", date_of_birth="1971-06-02", country="Freedonia"))
    assert agree["confidence"] == "high" and {e["field"] for e in agree["matched_on"]} >= {"name", "date_of_birth", "country"}
    clash = top(screen(root, name="Kellan Dresdorf", date_of_birth="1990"))
    assert clash["confidence"] == "low" and "birth year 1990" in clash["conflicts"][0]
    wrong_country = top(screen(root, name="Kellan Dresdorf", country="Ruritania"))
    assert wrong_country["confidence"] == "low" and "Freedonia" in wrong_country["conflicts"][0]


@pytest.mark.parametrize("name, method", [
    ("Dresdorf Kellan", "different order"),
    ("KELLAN  dresdorf!", "ignoring case"),
    ("Kel Dresdorff", "ignoring case"),          # the listed alias, exactly
    ("Келлан Дрездорф", "ignoring case"),         # original script
    ("Orlov Maritime Holdings Pty Ltd", "company-type words"),
    ("Kellen Dresdorf", "similar spelling"),
])
def test_name_tiers_say_why(root, name, method):
    assert method in top(screen(root, name=name))["matched_on"][0]["method"]


def test_an_alias_is_screened_as_a_name(root):
    assert screen(root, name="Somebody Else", aliases=["Kellan Dresdorf"])["dfat"]["status"] == "potential_match"


def test_identifiers_are_decisive_and_a_renamed_vessel_stays_medium(root):
    vessel = top(screen(root, name="Renamed Vessel", imo="9999991", subject_type="vessel"))
    assert vessel["confidence"] == "medium" and "name supplied does not match" in vessel["conflicts"][0]
    assert top(screen(root, imo="9999991"))["confidence"] == "high"
    passport = top(screen(root, identifier="FX 1234567"))
    assert passport["record"]["name"] == "Kellan DRESDORF" and passport["confidence"] == "high"


def test_subject_type_narrows_dfat(root):
    assert screen(root, name="Kellan Dresdorf", subject_type="organisation")["dfat"]["status"] == "no_match"
    assert screen(root, name="Kellan Dresdorf", subject_type="individual")["dfat"]["status"] == "potential_match"


def test_abf_matches_by_name_abn_and_flags_pending_review(root):
    by_name = screen(root, "abf", name="Brackenridge Hospitality")
    m = top(by_name, "abf")
    assert m["record"]["pending_review"] and any("Tribunal" in n for n in m["notes"])
    by_abn = top(screen(root, "abf", name="Quillfeather Staffing", abn="11 000 000 000"), "abf")
    assert by_abn["confidence"] == "high"
    trading = top(screen(root, "abf", name="QF Staffing"), "abf")
    assert "trading name" in trading["matched_on"][0]["method"]
    conflict = top(screen(root, "abf", name="Quillfeather Staffing", abn="99 000 000 000"), "abf")
    assert conflict["confidence"] == "low" and "differs" in conflict["conflicts"][0]


def test_abf_date_range_and_undated_records(root):
    assert screen(root, "abf", name="Quillfeather Staffing", sanctioned_from="2021-01-01")["abf"]["status"] == "no_match"
    undated = top(screen(root, "abf", name="Dresdorf Kellan", sanctioned_from="2021-01-01"), "abf")
    assert any("no sanction date" in n for n in undated["notes"])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        screen(root, name="x y z", sanctioned_from="last year")


def test_abf_nine_digit_register_value_is_only_a_corroborating_acn_hit(root):
    m = top(screen(root, "abf", acn="123 456 780"), "abf")
    assert m["record"]["name"] == "Nine Digit Holdings Pty Ltd" and "probably an ACN" in m["matched_on"][0]["method"]
    assert m["confidence"] == "medium"


def test_combined_result_separates_the_sources(root):
    r = screen(root, name="Kellan Dresdorf")
    assert r["dfat"]["status"] == "potential_match" and r["abf"]["status"] == "potential_match"
    assert r["overall"] == "potential_match" and r["dfat"]["dataset_version"].startswith("dfat:")
    clear = screen(root, name="Nobody Atall Known")
    assert clear["overall"] == "no_match" and clear["dfat"]["matches"] == [] == clear["abf"]["matches"]


def test_insufficient_information_and_not_applicable(root):
    r = screen(root, name="Al")
    assert r["dfat"]["status"] == r["abf"]["status"] == "insufficient_information" and r["overall"] == "incomplete"
    only_imo = screen(root, imo="9999991")
    assert only_imo["abf"]["status"] == "insufficient_information"
    assert screen(root, name="Northern Quill", subject_type="vessel")["abf"]["status"] == "not_applicable"


def test_a_missing_dataset_is_never_a_clean_result(tmp_path):
    r = Screener(tmp_path / "empty").screen(Subject(name="Kellan Dresdorf"))
    assert r["dfat"]["status"] == r["abf"]["status"] == "dataset_unavailable" and r["overall"] == "incomplete"
    assert "sanctions-au refresh" in r["dfat"]["next"]


def test_envelope_reports_versions_staleness_and_the_abf_lag(root):
    s = Screener(root)
    fresh = s.envelope("all", store.now())
    assert set(fresh["dataset_versions"]) == {"dfat", "abf"} and any("monthly" in w for w in fresh["warnings"])
    assert not any("last confirmed" in w for w in fresh["warnings"])
    old = s.envelope("all", store.now() + dt.timedelta(days=10))
    assert any(w.startswith("DFAT data was last confirmed 10 days ago") for w in old["warnings"])
    assert not any(w.startswith("ABF data was last confirmed") for w in old["warnings"])
    assert "dfat" not in s.envelope("abf", store.now())["dataset_versions"]
    assert "legal conclusion" in fresh["disclaimer"]


def test_stale_threshold_is_configurable(root, monkeypatch):
    monkeypatch.setenv("SANCTIONS_DFAT_MAX_AGE_DAYS", "20")
    assert not any("DFAT data was last" in w for w in Screener(root).envelope("all", store.now() + dt.timedelta(days=10))["warnings"])


def test_batch_keeps_order_refs_and_limits(root):
    s = Screener(root)
    out = s.screen_many([Subject(ref="a", name="Kellan Dresdorf"), Subject(ref="b", name="Nobody Atall Known")])
    assert [r["ref"] for r in out["results"]] == ["a", "b"]
    assert out["summary"] == {"subjects": 2, "potential_match": 1, "no_match": 1}
    assert "dataset_versions" in out and "results" in out
    with pytest.raises(ValueError):
        s.screen_many([])
    with pytest.raises(ValueError):
        s.screen_many([Subject(name="Kellan Dresdorf")] * (MAX_BATCH + 1))


def test_same_input_gives_the_same_result_and_no_network_is_used(root, monkeypatch):
    s = Screener(root)
    first = json.dumps(s.screen(Subject(name="Kellan Dresdorf", date_of_birth="1971")), sort_keys=True)

    def refuse(*a, **k):
        raise AssertionError("screening opened a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert json.dumps(Screener(root).screen(Subject(name="Kellan Dresdorf", date_of_birth="1971")), sort_keys=True) == first


def test_a_refresh_by_another_process_is_picked_up(root, tmp_path):
    s = Screener(root)
    assert s.screen(Subject(name="Newly Listed Person"))["dfat"]["status"] == "no_match"
    from conftest import DFAT_ROWS, dfat_row, make_xlsx
    from sanctions_au import dfat
    path = make_xlsx(tmp_path / "new.xlsx", [*DFAT_ROWS, dfat_row(9, "Newly Listed Person")])
    store.commit("dfat", path, dfat.parse(path)[0], {}, root=root, at=store.now() + dt.timedelta(seconds=5))
    assert s.screen(Subject(name="Newly Listed Person"))["dfat"]["status"] == "potential_match"


def test_get_record_returns_everything_and_explains_a_bad_id(root):
    s = Screener(root)
    rid = top(s.screen(Subject(name="Kellan Dresdorf")))["record_id"]
    rec = s.record("dfat", rid)
    assert len(rec["record"]["aliases"]) == 2 and rec["dataset_version"].startswith("dfat:")
    with pytest.raises(ValueError, match="only stable within a dataset version"):
        s.record("dfat", "nope")
