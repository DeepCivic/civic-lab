"""Screening: subject in, explained potential matches out, from the local snapshots only.

Nothing here touches the network. The only clock use is the staleness warning, which never
changes what matches.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import store
from .match import (TIER_EXACT, Name, Query, alnum, best_by_record, evidence, make_name, norm, years)

Source = Literal["dfat", "abf"]
SubjectType = Literal["any", "individual", "organisation", "vessel", "sponsor"]
MAX_MATCHES = 10
MAX_BATCH = 100
RANK = {"low": 1, "medium": 2, "high": 3}
LABEL = {v: k for k, v in RANK.items()}

DISCLAIMER = ("Potential matches only. This is not a legal conclusion that a person, organisation or vessel is or is "
              "not sanctioned. A match needs human review, and 'no match' does not clear a subject. This is an "
              "unofficial copy of published data: confirm against the current DFAT and ABF publications before acting.")
ABF_CAVEATS = ["The ABF updates its register monthly. A sponsor sanctioned recently may not appear yet.",
               "A sponsor marked pending_review has an Administrative Review Tribunal review pending."]
MAX_AGE_DAYS = {"dfat": 7, "abf": 35}  # an ABF month, plus a few days; both can be set by the operator


class Subject(BaseModel):
    ref: str | None = Field(None, description="Your own reference, returned unchanged (useful in batches).")
    name: str | None = Field(None, description="Person, organisation, vessel or sponsor name.")
    aliases: list[str] = Field(default_factory=list, description="Other names to screen as well.")
    subject_type: SubjectType = Field("any", description="Narrows DFAT to individuals, entities or vessels. "
                                                         "'sponsor' screens individuals and entities, not vessels.")
    date_of_birth: str | None = Field(None, description="Year or full date. Only the year is compared.")
    country: str | None = Field(None, description="Nationality or country, as a country name.")
    address: str | None = None
    identifier: str | None = Field(None, description="Passport or other identifier number.")
    imo: str | None = Field(None, description="Vessel IMO number.")
    abn: str | None = None
    acn: str | None = None
    sanctioned_from: str | None = Field(None, description="ABF only: earliest sanction date (YYYY-MM-DD).")
    sanctioned_to: str | None = Field(None, description="ABF only: latest sanction date (YYYY-MM-DD).")


def _max_age(source: str) -> int:
    return int(os.getenv(f"SANCTIONS_{source.upper()}_MAX_AGE_DAYS", MAX_AGE_DAYS[source]))


def _digits(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _confidence(tier: int, identifier: bool, name_given: bool, corroborated: bool, conflicts: bool) -> str:
    if identifier:
        level = 3 if (tier or not name_given) else 2
    else:
        level = {TIER_EXACT: 2}.get(tier, 1) + (1 if corroborated else 0)
    return LABEL[max(1, min(3, level - (1 if conflicts else 0)))]


def _basis(ev: list[dict[str, Any]], conflicts: list[str]) -> str:
    kinds = sorted({e["field"] for e in ev})
    return f"agreeing on: {', '.join(kinds)}; " + (f"conflicts: {'; '.join(conflicts)}" if conflicts else "no conflicts found")


class Screener:
    def __init__(self, root: Path | None = None):
        self.root = root
        self._ds: dict[str, store.Dataset] = {}
        self._index: dict[str, dict[str, Any]] = {}

    # -- datasets -----------------------------------------------------------------------------

    def dataset(self, source: str) -> store.Dataset | None:
        """The current dataset, reloaded if another process has refreshed it since the last call."""
        ptr = store.pointer(self.root or store.data_dir(), source)
        if ptr is None:
            return None
        cached = self._ds.get(source)
        if cached and cached.version == f"{source}:{ptr['snapshot_id']}":
            ds = dataclasses.replace(cached, checked_at=dt.datetime.fromisoformat(ptr["checked_at"]))
        else:
            ds = store.load(source, self.root)
            self._index.pop(source, None)
        if ds is not None:
            self._ds[source] = ds
        return ds

    def _idx(self, ds: store.Dataset) -> dict[str, Any]:
        idx = self._index.get(ds.source)
        if idx is None:
            names: list[Name] = []
            for r in ds.records:
                if ds.source == "dfat":
                    for field, value in [("name", r["name"]), *[(a["kind"], a["name"]) for a in r["aliases"]]]:
                        if (n := make_name(r["id"], field, value)):
                            names.append(n)
                else:
                    for field, value in (("sponsor_name", r["sponsor_name"]), ("trading_name", r["trading_name"])):
                        if value and (n := make_name(r["id"], field, value)):
                            names.append(n)
            idx = {"names": names, "by_id": {r["id"]: r for r in ds.records}}
            if ds.source == "dfat":
                idx["alnum_info"] = {r["id"]: alnum(r["additional_information"]) for r in ds.records
                                     if r["additional_information"]}
            self._index[ds.source] = idx
        return idx

    @staticmethod
    def age_days(ds: store.Dataset, at: dt.datetime) -> int:
        return max(0, (at - ds.checked_at).days)

    def status(self, at: dt.datetime | None = None) -> dict[str, Any]:
        at = at or store.now()
        out: dict[str, Any] = {"data_dir": str(self.root or store.data_dir()), "datasets": {}}
        for source in store.SOURCES:
            ds = self.dataset(source)
            if ds is None:
                out["datasets"][source] = {"available": False,
                                           "next": f"run `sanctions-au refresh --source {source}`"}
                continue
            age = self.age_days(ds, at)
            out["datasets"][source] = {
                "available": True, "dataset_version": ds.version, "records": ds.meta["record_count"],
                "source_url": ds.meta.get("source_url"), "retrieved_at": ds.meta["retrieved_at"],
                "last_confirmed_at": ds.checked_at.isoformat(), "age_days": age,
                "stale": age > _max_age(source), "stale_after_days": _max_age(source),
                "source_sha256": ds.meta["source_sha256"],
                **({"list_date": ds.meta["list_date"]} if ds.meta.get("list_date") else {})}
        out["caveats"] = ABF_CAVEATS
        return out

    # -- screening ----------------------------------------------------------------------------

    def screen(self, subject: Subject, sources: str = "all", at: dt.datetime | None = None) -> dict[str, Any]:
        at = at or store.now()
        for label, value in (("sanctioned_from", subject.sanctioned_from), ("sanctioned_to", subject.sanctioned_to)):
            if value:
                try:
                    dt.date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(f"{label} must be YYYY-MM-DD, got {value!r}") from exc
        wanted = [s for s in store.SOURCES if sources in ("all", s)]
        result: dict[str, Any] = {"ref": subject.ref, "subject": subject.model_dump(exclude_none=True, exclude={"ref"})}
        for source in wanted:
            ds = self.dataset(source)
            if ds is None:
                result[source] = {"status": "dataset_unavailable",
                                  "next": f"run `sanctions-au refresh --source {source}`"}
            else:
                result[source] = {"dataset_version": ds.version, **(self._dfat if source == "dfat" else self._abf)(subject, ds)}
        statuses = [result[s]["status"] for s in wanted]
        result["overall"] = ("potential_match" if "potential_match" in statuses
                             else "no_match" if all(s in ("no_match", "not_applicable") for s in statuses)
                             else "incomplete")
        return result

    def screen_many(self, subjects: list[Subject], sources: str = "all", at: dt.datetime | None = None) -> dict[str, Any]:
        if not 1 <= len(subjects) <= MAX_BATCH:
            raise ValueError(f"send between 1 and {MAX_BATCH} subjects per call")
        at = at or store.now()
        results = [self.screen(s, sources, at) for s in subjects]
        counts: dict[str, int] = {}
        for r in results:
            counts[r["overall"]] = counts.get(r["overall"], 0) + 1
        return {"summary": {"subjects": len(results), **counts}, "results": results, **self.envelope(sources, at)}

    def envelope(self, sources: str, at: dt.datetime) -> dict[str, Any]:
        """What every response carries once: which datasets were used, how old they are, the caveats."""
        versions, warnings = {}, []
        for source in (s for s in store.SOURCES if sources in ("all", s)):
            ds = self.dataset(source)
            if ds is None:
                warnings.append(f"No {source.upper()} dataset is installed, so it was not screened. "
                                f"Run `sanctions-au refresh --source {source}`.")
                continue
            versions[source] = ds.version
            age = self.age_days(ds, at)
            if age > _max_age(source):
                warnings.append(f"{source.upper()} data was last confirmed {age} days ago (warning after "
                                f"{_max_age(source)}). Refresh it before relying on a 'no match'.")
        if sources in ("all", "abf"):
            warnings += ABF_CAVEATS
        return {"dataset_versions": versions, "warnings": warnings, "disclaimer": DISCLAIMER}

    def _finish(self, status_when_none: str, scored: list[dict[str, Any]], not_used: list[str]) -> dict[str, Any]:
        scored.sort(key=lambda m: (-RANK[m["confidence"]], m["record"]["name"].casefold(), m["record_id"]))
        return {"status": "potential_match" if scored else status_when_none,
                "matches": scored[:MAX_MATCHES], "total_matches": len(scored),
                "truncated": len(scored) > MAX_MATCHES, "not_used": not_used}

    def _queries(self, s: Subject) -> list[Query]:
        return [q for q in (Query(t) for t in [s.name, *s.aliases] if t) if q.usable]

    # -- DFAT ---------------------------------------------------------------------------------

    def _dfat(self, s: Subject, ds: store.Dataset) -> dict[str, Any]:
        idx = self._idx(ds)
        by_id = idx["by_id"]
        imo, ident = _digits(s.imo), alnum(s.identifier or "")
        queries = self._queries(s)
        not_used = [f for f, v in (("abn", s.abn), ("acn", s.acn), ("sanctioned_from", s.sanctioned_from),
                                   ("sanctioned_to", s.sanctioned_to)) if v]
        if not queries and not imo and len(ident) < 6:
            return {"status": "insufficient_information", "matches": [], "not_used": not_used,
                    "reason": "Needs a name of at least three letters, an IMO number, or an identifier of at "
                              "least six characters."}
        kinds = {"individual": {"Individual"}, "organisation": {"Entity"}, "vessel": {"Vessel"},
                 "sponsor": {"Individual", "Entity"}, "any": {"Individual", "Entity", "Vessel"}}[s.subject_type]
        allowed = {i for i, r in by_id.items() if r["type"] in kinds}

        hits: dict[str, list[tuple[int, str, Name, Query]]] = {}
        for q in queries:
            for rid, found in best_by_record(q, idx["names"], allowed).items():
                hits.setdefault(rid, []).extend((t, m, n, q) for t, m, n in found)
        by_identifier: dict[str, list[dict[str, Any]]] = {}
        if imo:
            for rid in allowed:
                if by_id[rid]["imo"] == imo:
                    by_identifier.setdefault(rid, []).append(evidence("imo", imo, imo, "same IMO number"))
        if len(ident) >= 6:
            for rid, text in idx["alnum_info"].items():
                if rid in allowed and ident in text:
                    by_identifier.setdefault(rid, []).append(evidence(
                        "identifier", s.identifier or "", "(inside additional_information)",
                        "the identifier appears in the record's additional information"))

        subj_years, country, addr_tokens = years(s.date_of_birth), norm(s.country or ""), set(norm(s.address or "").split())
        scored = []
        for rid in set(hits) | set(by_identifier):
            r = by_id[rid]
            found = sorted(hits.get(rid, []), key=lambda h: -h[0])
            tier = found[0][0] if found else 0
            ev = [evidence("name", q.text, n.display, f"{m}; matched the record's {n.field.replace('_', ' ')}")
                  for _, m, n, q in found[:3]] + by_identifier.get(rid, [])
            conflicts, notes, corroborated = [], [], False
            if subj_years:
                rec_years = years(r["date_of_birth"])
                if not r["date_of_birth"]:
                    notes.append("the record has no date of birth, so it was not compared")
                elif subj_years & rec_years:
                    corroborated = True
                    ev.append(evidence("date_of_birth", s.date_of_birth or "", r["date_of_birth"], "birth year is listed"))
                elif rec_years:
                    conflicts.append(f"birth year {sorted(subj_years)[0]} is not among those listed ({r['date_of_birth']})")
            elif s.date_of_birth:
                notes.append("no four-digit year found in date_of_birth, so it was not compared")
            if country:
                if r["citizenship"] and f" {country} " in f" {norm(r['citizenship'])} ":
                    corroborated = True
                    ev.append(evidence("country", s.country or "", r["citizenship"], "listed citizenship"))
                elif r["citizenship"]:
                    conflicts.append(f"country {s.country} is not the listed citizenship ({r['citizenship']})")
                else:
                    notes.append("the record lists no citizenship, so country was not compared")
            if addr_tokens:
                rec_tokens = set(norm(" ".join(filter(None, [r["address"], r["place_of_birth"]]))).split())
                shared = {t for t in addr_tokens & rec_tokens if len(t) >= 4}
                if len(shared) >= 2:
                    corroborated = True
                    ev.append(evidence("address", s.address or "", r["address"] or r["place_of_birth"] or "",
                                       f"shared words: {', '.join(sorted(shared))}"))
            name_mismatch = rid in by_identifier and bool(queries) and not found
            if name_mismatch:  # shown, but already priced in by _confidence, so not counted twice
                conflicts.append("the name supplied does not match any name on the record")
            confidence = _confidence(tier, rid in by_identifier, bool(queries), corroborated,
                                     len(conflicts) > int(name_mismatch))
            scored.append({"record_id": rid, "confidence": confidence, "confidence_basis": _basis(ev, conflicts),
                           "matched_on": ev, "conflicts": conflicts, "notes": notes,
                           "record": {k: r[k] for k in ("id", "name", "type", "date_of_birth", "citizenship", "imo",
                                                        "committees", "listing_information", "instrument_of_designation",
                                                        "control_date", "measures")} | {"aliases_total": len(r["aliases"])}})
        return self._finish("no_match", scored, not_used)

    # -- ABF ----------------------------------------------------------------------------------

    def _abf(self, s: Subject, ds: store.Dataset) -> dict[str, Any]:
        idx = self._idx(ds)
        by_id = idx["by_id"]
        if s.subject_type == "vessel":
            return {"status": "not_applicable", "matches": [], "reason": "The ABF register lists sponsors, not vessels."}
        abn, acn = _digits(s.abn), _digits(s.acn)
        queries = self._queries(s)
        not_used = [f for f, v in (("date_of_birth", s.date_of_birth), ("country", s.country), ("address", s.address),
                                   ("identifier", s.identifier), ("imo", s.imo)) if v]
        if not queries and len(abn) != 11 and len(acn) != 9:
            return {"status": "insufficient_information", "matches": [], "not_used": not_used,
                    "reason": "Needs a sponsor name of at least three letters, an 11-digit ABN or a 9-digit ACN."}
        notes_all = []
        if s.abn and len(abn) != 11:
            notes_all.append(f"abn {s.abn!r} is not 11 digits and was not used")
        if s.acn and len(acn) != 9:
            notes_all.append(f"acn {s.acn!r} is not 9 digits and was not used")

        def in_range(r: dict[str, Any]) -> bool:
            d = r["sanction_imposed_date"]
            return d is None or ((not s.sanctioned_from or d >= s.sanctioned_from) and (not s.sanctioned_to or d <= s.sanctioned_to))

        allowed = {i for i, r in by_id.items() if in_range(r)}
        hits: dict[str, list[tuple[int, str, Name, Query]]] = {}
        for q in queries:
            for rid, found in best_by_record(q, idx["names"], allowed).items():
                hits.setdefault(rid, []).extend((t, m, n, q) for t, m, n in found)
        ids: dict[str, dict[str, Any]] = {}
        for rid in allowed:
            reg = by_id[rid]["abn"] or ""
            if len(abn) == 11 and reg == abn:
                ids[rid] = evidence("abn", abn, reg, "same ABN")
            elif len(acn) == 9 and reg == acn:  # the register's ABN field holds 9 digits for some records
                ids[rid] = evidence("acn", acn, reg, "same digits as the register's ABN field, which holds only "
                                                     "9 digits here and is probably an ACN (not confirmed)")
        scored = []
        for rid in set(hits) | set(ids):
            r = by_id[rid]
            found = sorted(hits.get(rid, []), key=lambda h: -h[0])
            tier = found[0][0] if found else 0
            ev = [evidence("name", q.text, n.display, f"{m}; matched the record's {n.field.replace('_', ' ')}")
                  for _, m, n, q in found[:3]] + ([ids[rid]] if rid in ids else [])
            conflicts, notes = [], list(notes_all)
            if len(abn) == 11 and r["abn"] and len(r["abn"]) == 11 and r["abn"] != abn and rid not in ids:
                conflicts.append(f"ABN {abn} differs from the register's ABN {r['abn']}")
            name_mismatch = rid in ids and bool(queries) and not found
            if name_mismatch:
                conflicts.append("the name supplied does not match the sponsor or trading name on the record")
            if r["pending_review"]:
                notes.append("Administrative Review Tribunal review is pending for this sanction")
            if r["sanction_imposed_date"] is None and (s.sanctioned_from or s.sanctioned_to):
                notes.append("the record has no sanction date, so the date range could not exclude it")
            abn_hit = rid in ids and ids[rid]["field"] == "abn"
            acn_hit = rid in ids and ids[rid]["field"] == "acn"  # unconfirmed meaning, so it corroborates only
            confidence = _confidence(tier, abn_hit, bool(queries), acn_hit, len(conflicts) > int(name_mismatch))
            scored.append({"record_id": rid, "confidence": confidence, "confidence_basis": _basis(ev, conflicts),
                           "matched_on": ev, "conflicts": conflicts, "notes": notes,
                           "record": {**r, "name": r["sponsor_name"]}})
        return self._finish("no_match", scored, not_used)

    # -- records ------------------------------------------------------------------------------

    def record(self, source: str, record_id: str) -> dict[str, Any]:
        ds = self.dataset(source)
        if ds is None:
            raise store.DatasetError(f"No {source.upper()} dataset is installed. Run `sanctions-au refresh --source {source}`.")
        rec = self._idx(ds)["by_id"].get(record_id)
        if rec is None:
            raise ValueError(f"No {source.upper()} record {record_id!r} in {ds.version}. IDs are only stable within a "
                             "dataset version; screen again to get current ones.")
        return {"dataset_version": ds.version, "record": rec, "disclaimer": DISCLAIMER}
