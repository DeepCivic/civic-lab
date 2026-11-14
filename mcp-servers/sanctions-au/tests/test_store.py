import datetime as dt
import json

import pytest
from conftest import DFAT_ROWS, dfat_row, make_xlsx

from sanctions_au import dfat, store
from sanctions_au.store import DatasetError

T0 = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.timezone.utc)


def _commit(root, tmp_path, rows, name="f.xlsx", **kw):
    path = make_xlsx(tmp_path / name, rows)
    records, _ = dfat.parse(path)
    return store.commit("dfat", path, records, {}, root=root, **kw)


def test_first_commit_is_traceable_and_read_only(tmp_path):
    root = tmp_path / "d"
    res = _commit(root, tmp_path, DFAT_ROWS, at=T0)
    assert res.outcome == "new" and res.version.startswith("dfat:20261101T090000Z-")
    snap = next((root / "snapshots" / "dfat").iterdir())
    meta = json.loads((snap / "meta.json").read_text())
    assert meta["record_count"] == 4 and len(meta["source_sha256"]) == 64 and meta["dataset_version"] == res.version
    assert all(f.stat().st_mode & 0o222 == 0 for f in snap.iterdir())  # mode bits: root can write anything
    ds = store.load("dfat", root)
    assert ds.version == res.version and len(ds.records) == 4


def test_identical_content_only_reconfirms(tmp_path):
    root = tmp_path / "d"
    _commit(root, tmp_path, DFAT_ROWS, at=T0)
    again = _commit(root, tmp_path, DFAT_ROWS, at=T0 + dt.timedelta(days=3))
    assert again.outcome == "unchanged" and len(list((root / "snapshots" / "dfat").iterdir())) == 1
    ds = store.load("dfat", root)
    assert ds.checked_at == T0 + dt.timedelta(days=3)


def test_changed_content_makes_a_new_version_and_keeps_the_old(tmp_path):
    root = tmp_path / "d"
    first = _commit(root, tmp_path, DFAT_ROWS, at=T0)
    second = _commit(root, tmp_path, [*DFAT_ROWS, dfat_row(9, "Newly Listed")], name="g.xlsx", at=T0 + dt.timedelta(days=1))
    assert second.outcome == "new" and second.version != first.version
    assert len(list((root / "snapshots" / "dfat").iterdir())) == 2
    assert store.load("dfat", root).version == second.version


def test_a_much_smaller_snapshot_is_refused_and_changes_nothing(tmp_path):
    root = tmp_path / "d"
    first = _commit(root, tmp_path, DFAT_ROWS, at=T0)
    with pytest.raises(DatasetError, match="broken download"):
        _commit(root, tmp_path, DFAT_ROWS[-1:], name="small.xlsx", at=T0 + dt.timedelta(days=1))
    assert store.load("dfat", root).version == first.version
    assert [p.name for p in (root / "snapshots" / "dfat").iterdir() if p.name.startswith(".")] == []
    forced = _commit(root, tmp_path, DFAT_ROWS[-1:], name="small.xlsx", force=True, at=T0 + dt.timedelta(days=1))
    assert forced.outcome == "new"


def test_a_damaged_snapshot_is_reported_not_screened(tmp_path):
    root = tmp_path / "d"
    _commit(root, tmp_path, DFAT_ROWS, at=T0)
    rec = next((root / "snapshots" / "dfat").iterdir()) / "records.jsonl"
    rec.chmod(0o644)
    rec.write_text(rec.read_text().replace("Freedonia", "Elsewhere"))
    with pytest.raises(DatasetError, match="integrity check"):
        store.load("dfat", root)


def test_missing_dataset_is_none(tmp_path):
    assert store.load("abf", tmp_path) is None
