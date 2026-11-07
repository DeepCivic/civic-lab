"""Local SQLite index over the ABN Lookup bulk extract.

Build guarantees (``build_index``):

* **Atomic.** The index is built to a temporary file beside the target and
  moved into place only after every check passes. A failed or interrupted
  build never replaces a working index.
* **Verified per file.** Each XML file's parsed record count must equal its
  declared ``TransferInfo/RecordCount`` (catches truncated downloads), and
  ``Transfer/@error`` must be clear. A failing file is removed from the build
  and, unless ``allow_partial`` is set, fails the build.
* **Complete or labelled partial.** The extract is 20 files numbered 1–20. A
  build missing any sequence number fails unless ``allow_partial``; a partial
  index is recorded as such so a miss is reported as "not in this partial
  index", never as "not registered".
* **One row per ABN.** If an ABN appears more than once, the record with the
  latest ``recordLastUpdatedDate`` wins (then the later file).

Queries open the index read-only, one connection per call, so a rebuild can
swap the file underneath a running server safely.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .bulk import RECORD_FIELDS, AbrRecord, TransferInfo, discover_sources, iter_extract
from .codes import BULK_EXTRACT_SCHEMA_VERSION
from .names import fts_query, name_key

INDEX_FORMAT = "1"
EXPECTED_FILES = 20
_BATCH = 20_000

_SCHEMA = f"""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    file_sequence_number TEXT NOT NULL,
    extract_time TEXT NOT NULL,
    record_count_declared TEXT NOT NULL,
    records_parsed INTEGER NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL
);
CREATE TABLE records (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    {", ".join(f"{f} TEXT NOT NULL" for f in RECORD_FIELDS)}
);
CREATE TABLE names (
    id INTEGER PRIMARY KEY,
    rec_id INTEGER NOT NULL,
    name_type TEXT NOT NULL,
    name_text TEXT NOT NULL,
    name_key TEXT NOT NULL
);
CREATE TABLE dgr (
    rec_id INTEGER NOT NULL,
    status_from_date TEXT NOT NULL,
    status TEXT NOT NULL,
    fund_name TEXT NOT NULL
);
"""

_POST_LOAD = """
CREATE INDEX records_abn ON records(abn);
CREATE INDEX records_acn ON records(asic_number) WHERE asic_number <> '';
CREATE INDEX names_rec ON names(rec_id);
CREATE INDEX names_key ON names(name_key);
CREATE INDEX dgr_rec ON dgr(rec_id);
"""


class BuildError(RuntimeError):
    """The build did not produce a trustworthy index; nothing was replaced."""


@dataclass
class SourceReport:
    label: str
    status: str  # loaded | failed | skipped_duplicate
    file_sequence_number: str = ""
    extract_time: str = ""
    record_count_declared: str = ""
    records_parsed: int = 0
    error: str = ""


@dataclass
class BuildReport:
    db_path: Path
    sources: list[SourceReport] = field(default_factory=list)
    record_count: int = 0
    name_count: int = 0
    duplicates_resolved: int = 0
    missing_sequence_numbers: list[int] = field(default_factory=list)
    extract_dates: list[str] = field(default_factory=list)
    complete: bool = False
    fts: bool = False
    seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


def default_index_path() -> Path:
    """``$ABR_INDEX_PATH``, else a per-user data directory."""
    env = (os.getenv("ABR_INDEX_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "abr-mcp" / "abr.sqlite"


def fts5_available() -> bool:
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        con.close()
        return True
    except sqlite3.Error:
        return False


def _delete_source(con: sqlite3.Connection, source_id: int) -> None:
    sub = "SELECT id FROM records WHERE source_id = ?"
    con.execute(f"DELETE FROM names WHERE rec_id IN ({sub})", (source_id,))
    con.execute(f"DELETE FROM dgr WHERE rec_id IN ({sub})", (source_id,))
    con.execute("DELETE FROM records WHERE source_id = ?", (source_id,))


def build_index(
    inputs: Iterable[str | os.PathLike[str]],
    db_path: str | os.PathLike[str] | None = None,
    *,
    fts: bool = True,
    allow_partial: bool = False,
    progress: Callable[[str], None] | None = None,
    extra_meta: dict[str, str] | None = None,
) -> BuildReport:
    """Build (or rebuild) the local index from bulk extract files/zips/dirs."""
    started = time.monotonic()
    target = Path(db_path) if db_path else default_index_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.building-{os.getpid()}")
    tmp.unlink(missing_ok=True)
    say = progress or (lambda _msg: None)

    sources = discover_sources(list(inputs))
    if not sources:
        raise BuildError("No .xml or .zip bulk extract files found in the given inputs.")
    if fts and not fts5_available():
        raise BuildError("This Python's SQLite lacks FTS5; rebuild with --no-fts.")

    report = BuildReport(db_path=target, fts=fts)
    # Index and FTS builds spill multi-GB sorts to SQLite's temp dir; keep them
    # beside the index rather than in a (often small, RAM-backed) /tmp.
    os.environ.setdefault("SQLITE_TMPDIR", str(target.parent))
    con = sqlite3.connect(tmp)
    try:
        con.executescript(
            "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; "
            "PRAGMA locking_mode=EXCLUSIVE; PRAGMA cache_size=-262144; "
            "PRAGMA temp_store=FILE;"
        )
        con.executescript(_SCHEMA)
        rec_sql = (
            f"INSERT INTO records (id, source_id, {', '.join(RECORD_FIELDS)}) "
            f"VALUES (?, ?, {', '.join('?' for _ in RECORD_FIELDS)})"
        )
        next_rec = 1
        loaded: dict[str, str] = {}  # file_sequence_number -> extract_time

        for source_id, src in enumerate(sources, start=1):
            rep = SourceReport(label=src.label, status="failed")
            report.sources.append(rep)
            say(f"reading {src.label}")
            recs: list[tuple[Any, ...]] = []
            names: list[tuple[Any, ...]] = []
            dgrs: list[tuple[Any, ...]] = []

            def flush() -> None:
                con.executemany(rec_sql, recs)
                con.executemany(
                    "INSERT INTO names (rec_id, name_type, name_text, name_key) VALUES (?,?,?,?)",
                    names,
                )
                con.executemany(
                    "INSERT INTO dgr (rec_id, status_from_date, status, fund_name) VALUES (?,?,?,?)",
                    dgrs,
                )
                recs.clear(), names.clear(), dgrs.clear()

            skipped = False
            try:
                with src.open() as stream:
                    for item in iter_extract(stream):
                        if isinstance(item, TransferInfo):
                            rep.file_sequence_number = item.file_sequence_number
                            rep.extract_time = item.extract_time
                            rep.record_count_declared = item.record_count
                            if item.error.lower() not in ("", "none", "false"):
                                raise ValueError(f"Transfer error attribute is {item.error!r}")
                            seq = item.file_sequence_number
                            if seq and loaded.get(seq) == item.extract_time:
                                rep.status = "skipped_duplicate"
                                rep.error = f"file sequence {seq} of this extract already loaded"
                                skipped = True
                                break
                            continue
                        assert isinstance(item, AbrRecord)
                        rid = next_rec
                        next_rec += 1
                        r = item.record
                        recs.append((rid, source_id, *(r[f] for f in RECORD_FIELDS)))
                        for ntype, text in item.names:
                            names.append((rid, ntype, text, name_key(text)))
                        for d in item.dgr:
                            dgrs.append((rid, *d))
                        rep.records_parsed += 1
                        if len(recs) >= _BATCH:
                            flush()
                if not skipped:
                    flush()
                    declared = rep.record_count_declared
                    if not declared.isdigit():
                        raise ValueError("TransferInfo has no RecordCount to verify against")
                    if int(declared) != rep.records_parsed:
                        raise ValueError(
                            f"parsed {rep.records_parsed} records but TransferInfo declares "
                            f"{declared} (truncated or corrupt file?)"
                        )
                    rep.status = "loaded"
                    loaded[rep.file_sequence_number] = rep.extract_time
                    say(f"  {rep.records_parsed:,} records")
            except Exception as exc:
                # Malformed XML (ET.ParseError), truncated zip (EOFError /
                # BadZipFile), wrong root, count mismatch: isolate to this file.
                recs.clear(), names.clear(), dgrs.clear()
                _delete_source(con, source_id)
                rep.status = "failed"
                rep.error = f"{type(exc).__name__}: {exc}"
                say(f"  FAILED: {rep.error}")
            con.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)",
                (source_id, rep.label, rep.file_sequence_number, rep.extract_time,
                 rep.record_count_declared, rep.records_parsed, rep.status, rep.error),
            )
            con.commit()

        failed = [s for s in report.sources if s.status == "failed"]
        seqs = {int(s) for s in loaded if s.isdigit()}
        report.missing_sequence_numbers = [n for n in range(1, EXPECTED_FILES + 1) if n not in seqs]
        report.extract_dates = sorted({t[:10] for t in loaded.values() if t})
        report.complete = not failed and not report.missing_sequence_numbers
        if len(report.extract_dates) > 1:
            report.warnings.append(
                f"files come from different extracts: {', '.join(report.extract_dates)}"
            )

        if failed and not allow_partial:
            raise BuildError(
                "Some files failed and were not loaded: "
                + "; ".join(f"{s.label}: {s.error}" for s in failed)
                + ". Fix or re-download them, or pass --allow-partial."
            )
        if report.missing_sequence_numbers and not allow_partial:
            raise BuildError(
                "The extract is incomplete: missing file sequence number(s) "
                + ", ".join(map(str, report.missing_sequence_numbers))
                + f" of 1–{EXPECTED_FILES}. Supply all files, or pass --allow-partial "
                "(lookups will then say 'not in this partial index' rather than 'not registered')."
            )
        if not loaded:
            raise BuildError("No records were loaded.")

        say("indexing")
        con.executescript(_POST_LOAD)
        report.duplicates_resolved = _dedupe(con)
        if fts:
            say("building full-text name index")
            con.executescript(
                "CREATE VIRTUAL TABLE names_fts USING fts5("
                "name_key, content='names', content_rowid='id', tokenize='unicode61');"
                "INSERT INTO names_fts(names_fts) VALUES('rebuild');"
            )
        con.executescript(
            "CREATE TABLE entity_types AS SELECT entity_type_ind AS code, "
            "entity_type_text AS description, count(*) AS records FROM records "
            "GROUP BY 1, 2 ORDER BY 1;"
        )
        report.record_count = con.execute("SELECT count(*) FROM records").fetchone()[0]
        report.name_count = con.execute("SELECT count(*) FROM names").fetchone()[0]
        report.seconds = round(time.monotonic() - started, 1)

        meta = {
            "index_format": INDEX_FORMAT,
            "bulk_extract_schema_version": BULK_EXTRACT_SCHEMA_VERSION,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "built_by": f"abr-mcp {__version__}",
            "record_count": str(report.record_count),
            "name_count": str(report.name_count),
            "duplicates_resolved": str(report.duplicates_resolved),
            "extract_dates": ",".join(report.extract_dates),
            "complete": "1" if report.complete else "0",
            "missing_sequence_numbers": ",".join(map(str, report.missing_sequence_numbers)),
            "fts": "1" if fts else "0",
            "warnings": " | ".join(report.warnings),
            **(extra_meta or {}),
        }
        con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
        con.commit()
        say("analysing")
        con.execute("ANALYZE")
        con.execute("PRAGMA journal_mode=DELETE")
        con.commit()
        con.close()
        con = None  # type: ignore[assignment]
        os.replace(tmp, target)
        return report
    except BaseException:
        if con is not None:
            con.close()
        tmp.unlink(missing_ok=True)
        raise


def _dedupe(con: sqlite3.Connection) -> int:
    dup_abns = [row[0] for row in con.execute(
        "SELECT abn FROM records GROUP BY abn HAVING count(*) > 1"
    )]
    losers: list[int] = []
    for abn in dup_abns:
        ids = [row[0] for row in con.execute(
            "SELECT id FROM records WHERE abn = ? "
            "ORDER BY record_last_updated_date DESC, id DESC", (abn,)
        )]
        losers.extend(ids[1:])
    for i in range(0, len(losers), 500):
        chunk = losers[i:i + 500]
        marks = ",".join("?" * len(chunk))
        con.execute(f"DELETE FROM names WHERE rec_id IN ({marks})", chunk)
        con.execute(f"DELETE FROM dgr WHERE rec_id IN ({marks})", chunk)
        con.execute(f"DELETE FROM records WHERE id IN ({marks})", chunk)
    con.commit()
    return len(losers)


# ── Query side ────────────────────────────────────────────────────────────────


class IndexUnavailable(RuntimeError):
    pass


class LocalIndex:
    """Read-only access to a built index."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path else default_index_path()

    def available(self) -> bool:
        return self.path.is_file()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise IndexUnavailable(f"No ABR index at {self.path}. Run: abr-mcp update-index")
        con = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def meta(self) -> dict[str, str]:
        with closing(self._connect()) as con:
            meta = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM meta")}
        if meta.get("index_format") != INDEX_FORMAT:
            raise IndexUnavailable(
                f"Index format {meta.get('index_format')!r} is not supported by this version "
                f"(expects {INDEX_FORMAT}); rebuild the index."
            )
        return meta

    def sources(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            return [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY id")]

    def entity_types(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            return [dict(r) for r in con.execute("SELECT * FROM entity_types")]

    @staticmethod
    def _attach(con: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            d = dict(row)
            rid = d.pop("id")
            d.pop("source_id", None)
            d["names"] = [
                (n["name_type"], n["name_text"])
                for n in con.execute(
                    "SELECT name_type, name_text FROM names WHERE rec_id = ? ORDER BY id", (rid,)
                )
            ]
            d["dgr"] = [
                (g["status_from_date"], g["status"], g["fund_name"])
                for g in con.execute(
                    "SELECT status_from_date, status, fund_name FROM dgr WHERE rec_id = ? ORDER BY rowid",
                    (rid,),
                )
            ]
            out.append(d)
        return out

    def get_by_abn(self, abn: str) -> dict[str, Any] | None:
        with closing(self._connect()) as con:
            rows = con.execute("SELECT * FROM records WHERE abn = ? LIMIT 1", (abn,)).fetchall()
            found = self._attach(con, rows)
        return found[0] if found else None

    def get_many(self, abns: list[str]) -> dict[str, dict[str, Any]]:
        """Records (without name lists) for many ABNs, keyed by ABN."""
        out: dict[str, dict[str, Any]] = {}
        uniq = sorted(set(abns))
        with closing(self._connect()) as con:
            for i in range(0, len(uniq), 500):
                chunk = uniq[i:i + 500]
                marks = ",".join("?" * len(chunk))
                for row in con.execute(f"SELECT * FROM records WHERE abn IN ({marks})", chunk):
                    d = dict(row)
                    d.pop("id"), d.pop("source_id", None)
                    out[d["abn"]] = d
        return out

    def get_by_acn(self, acn: str) -> list[dict[str, Any]]:
        if not acn:
            return []
        with closing(self._connect()) as con:
            rows = con.execute(
                # The redundant `<> ''` lets SQLite use the partial ACN index.
                "SELECT * FROM records WHERE asic_number = ? AND asic_number <> '' "
                "ORDER BY abn_status = 'ACT' DESC, abn",
                (acn,),
            ).fetchall()
            return self._attach(con, rows)

    def search(
        self,
        name: str,
        *,
        mode: str = "auto",
        state: str | None = None,
        postcode: str | None = None,
        active_only: bool = False,
        name_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Name search, one result per ABN, exact-key matches first."""
        key = name_key(name)
        filters, params = [], []
        if state:
            filters.append("r.state = ?"), params.append(state.upper())
        if postcode:
            filters.append("r.postcode = ?"), params.append(postcode)
        if active_only:
            filters.append("r.abn_status = 'ACT'")
        if name_types:
            types = [t.upper() for t in name_types]
            filters.append(f"n.name_type IN ({','.join('?' * len(types))})")
            params.extend(types)
        where = "".join(f" AND {f}" for f in filters)
        cols = (
            "r.abn, r.abn_status, r.entity_type_ind, r.entity_type_text, r.display_name, "
            "r.state, r.postcode, n.name_type, n.name_text"
        )
        results: dict[str, dict[str, Any]] = {}
        truncated = False

        def add(rows: Iterable[sqlite3.Row], match: str) -> None:
            for row in rows:
                hit = results.get(row["abn"])
                if hit is None:
                    if len(results) >= limit:
                        continue
                    hit = {k: row[k] for k in (
                        "abn", "abn_status", "entity_type_ind", "entity_type_text",
                        "display_name", "state", "postcode")}
                    hit["match"] = match
                    hit["matched_names"] = []
                    results[row["abn"]] = hit
                pair = {"name_type": row["name_type"], "name": row["name_text"]}
                if pair not in hit["matched_names"]:
                    hit["matched_names"].append(pair)

        with closing(self._connect()) as con:
            fts = con.execute("SELECT value FROM meta WHERE key='fts'").fetchone()
            has_fts = bool(fts and fts[0] == "1")
            if key and mode in ("auto", "exact"):
                add(con.execute(
                    f"SELECT {cols} FROM names n JOIN records r ON r.id = n.rec_id "
                    f"WHERE n.name_key = ?{where} "
                    "ORDER BY r.abn_status = 'ACT' DESC, n.name_type IN ('MN','LGL') DESC, r.abn "
                    f"LIMIT ?", (key, *params, limit * 5),
                ), "exact_name")
            if key and mode in ("auto", "tokens") and len(results) < limit:
                q = fts_query(name)
                if has_fts and q:
                    pool = 20_000 if filters else max(2_000, limit * 50)
                    rows = con.execute(
                        f"SELECT {cols} FROM (SELECT rowid AS nid, rank FROM names_fts "
                        f"WHERE names_fts MATCH ? ORDER BY rank LIMIT ?) f "
                        f"JOIN names n ON n.id = f.nid JOIN records r ON r.id = n.rec_id "
                        f"WHERE 1=1{where} "
                        "ORDER BY f.rank, r.abn_status = 'ACT' DESC LIMIT ?",
                        (q, pool, *params, limit * 5),
                    ).fetchall()
                    pool_hits = con.execute(
                        "SELECT count(*) FROM (SELECT 1 FROM names_fts WHERE names_fts MATCH ? LIMIT ?)",
                        (q, pool + 1),
                    ).fetchone()[0]
                    truncated = pool_hits > pool
                    add(rows, "all_tokens")
                elif not has_fts:
                    like = "%" + "%".join(key.split(" ")) + "%"
                    add(con.execute(
                        f"SELECT {cols} FROM names n JOIN records r ON r.id = n.rec_id "
                        f"WHERE n.name_key LIKE ?{where} LIMIT ?", (like, *params, limit * 5),
                    ), "all_tokens")
        return {"key": key, "results": list(results.values()), "candidate_pool_truncated": truncated}
