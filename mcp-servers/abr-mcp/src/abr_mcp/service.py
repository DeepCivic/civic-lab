"""Backend orchestration and response shaping.

Every response says where its data came from (``provenance``) and how fresh it
is. Lookups validate identifiers *before* touching any backend: an ABN failing
its checksum cannot be registered, so it is reported as invalid, not "not
found".

``source`` on each call:

* ``auto``  — local index if built, else the web service; on a local miss,
  fall back to the web service when configured (the extract is weekly, so a
  new ABN can be live but not yet in the index).
* ``local`` — bulk extract index only (offline, deterministic).
* ``web``   — live ABN Lookup web services only (needs ``ABR_GUID``).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .codes import (
    ABN_STATUS,
    DEFAULT_SEARCH_NAME_TYPES,
    DISCLAIMER,
    GST_STATUS,
    LICENCE,
    NAME_TYPE_RANK,
    NAME_TYPES,
    STATES,
    WEB_SERVICES_TERMS,
)
from .identifiers import acn_is_valid, format_abn, format_acn, validate_abn, validate_acn
from .index import IndexUnavailable, LocalIndex
from .web import AbrWebClient, WebError

SOURCES = ("auto", "local", "web")
MAX_BATCH_LOCAL = 1000
MAX_BATCH_WEB = 25

CAVEATS = {
    "snapshot": (
        "Bulk extract data is a weekly snapshot of *current* details as at the extract date; "
        "status, names and GST may have changed since. Use source='web' for live data."
    ),
    "trading_names": NAME_TYPES["TRD"],
    "location": (
        "State/postcode is the main business location recorded on the ABR, not a registered "
        "office or street address."
    ),
    "name_match": (
        "Name matches are candidates, not identity. Confirm by ABN; distinct entities can share "
        "names, and one entity can trade under many."
    ),
    "partial_index": (
        "The local index was built from a partial extract, so an ABN missing from it may still "
        "be registered."
    ),
}


def iso_date(value: str) -> str:
    """``yyyymmdd`` → ``yyyy-mm-dd``; ISO datetimes trimmed to the date; else verbatim."""
    v = (value or "").strip()
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return v[:10]
    return v


class AbrService:
    def __init__(self, index: LocalIndex | None = None, web: AbrWebClient | None = None) -> None:
        self.index = index or LocalIndex()
        self.web = web or AbrWebClient()

    # ── provenance ──────────────────────────────────────────────────────────

    def _local_meta(self) -> dict[str, str] | None:
        if not self.index.available():
            return None
        try:
            return self.index.meta()
        except Exception:
            return None

    def _local_provenance(self, meta: dict[str, str]) -> dict[str, Any]:
        dates = [d for d in meta.get("extract_dates", "").split(",") if d]
        extract = dates[-1] if dates else ""
        age = None
        if extract:
            try:
                age = (date.today() - date.fromisoformat(extract)).days
            except ValueError:
                age = None
        return {
            "source": "abr_bulk_extract",
            "extract_date": extract,
            "extract_age_days": age,
            "index_complete": meta.get("complete") == "1",
            **LICENCE,
        }

    @staticmethod
    def _web_provenance() -> dict[str, Any]:
        return {
            "source": "abr_web_services",
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **WEB_SERVICES_TERMS,
        }

    def _resolve(self, source: str) -> tuple[bool, bool]:
        """(use_local, use_web) for a requested source; raises on misconfiguration."""
        if source not in SOURCES:
            raise ValueError(f"source must be one of {', '.join(SOURCES)}")
        local_ok = self._local_meta() is not None
        web_ok = self.web.available()
        if source == "local" and not local_ok:
            raise IndexUnavailable(
                f"No usable local index at {self.index.path}. Build one with "
                "`abr-mcp update-index`, or use source='web'."
            )
        if source == "web" and not web_ok:
            raise WebError("ABR web services are not configured: set ABR_GUID.")
        if source == "auto" and not (local_ok or web_ok):
            raise IndexUnavailable(
                "No ABR backend is configured: set ABR_GUID for the live ABN Lookup web services "
                "(free GUID: https://abr.business.gov.au/Tools/WebServices) and/or build a local "
                "index with `abr-mcp update-index`."
            )
        return (source in ("auto", "local") and local_ok, source in ("auto", "web") and web_ok)

    # ── shaping ─────────────────────────────────────────────────────────────

    @staticmethod
    def _shape_local(rec: dict[str, Any]) -> dict[str, Any]:
        names = sorted(rec.get("names", []), key=lambda p: NAME_TYPE_RANK.get(p[0], 9))
        by_type: dict[str, list[str]] = {}
        for ntype, text in names:
            if ntype in ("MN", "LGL"):
                continue
            bucket = by_type.setdefault(ntype, [])
            if text not in bucket:
                bucket.append(text)
        acn = rec.get("asic_number", "")
        abn = rec["abn"]
        out: dict[str, Any] = {
            "abn": abn,
            "abn_formatted": format_abn(abn),
            "abn_status": rec["abn_status"],
            "abn_status_text": ABN_STATUS.get(rec["abn_status"], rec["abn_status"]),
            "abn_status_from": iso_date(rec["abn_status_from_date"]),
            "entity_name": rec["display_name"],
            "entity_name_type": rec["name_type"],
            "entity_type_code": rec["entity_type_ind"],
            "entity_type": rec["entity_type_text"],
            "business_names": by_type.pop("BN", []),
            "trading_names": by_type.pop("TRD", []),
            "other_names": by_type.pop("OTN", []),
            "state": rec["state"],
            "postcode": rec["postcode"],
            "gst": {
                "status": rec["gst_status"],
                "status_text": GST_STATUS.get(rec["gst_status"], rec["gst_status"]),
                "from": iso_date(rec["gst_status_from_date"]),
                "registered": rec["gst_status"] == "ACT",
            },
            "acn": acn,
            "record_last_updated": iso_date(rec["record_last_updated_date"]),
            "replaced": rec["replaced"],
        }
        by_type.pop("DGR", None)
        if by_type:
            out["unrecognised_name_types"] = by_type
        if rec["entity_type_ind"] == "IND":
            out["individual_name"] = {
                "title": rec["name_title"],
                "given_names": [g for g in (rec["given_name_1"], rec["given_name_2"]) if g],
                "family_name": rec["family_name"],
            }
        if acn:
            out["acn_formatted"] = format_acn(acn)
            out["acn_checksum_valid"] = acn_is_valid(acn)
            # Companies' ABNs are normally their ACN with a 2-digit prefix.
            out["abn_embeds_acn"] = abn[2:] == acn
        dgr = rec.get("dgr", [])
        out["dgr_endorsed"] = bool(dgr)
        if dgr:
            out["dgr"] = [
                {"fund_name": fund, "status": status, "from": iso_date(frm)}
                for frm, status, fund in dgr
            ]
        return out

    @staticmethod
    def _shape_web(data: dict[str, Any]) -> dict[str, Any]:
        abn = str(data.get("Abn") or "")
        status_text = str(data.get("AbnStatus") or "")
        code = {"active": "ACT", "cancelled": "CAN"}.get(status_text.lower(), status_text)
        gst_from = str(data.get("Gst") or "")
        acn = str(data.get("Acn") or "")
        biz = data.get("BusinessName") or []
        out: dict[str, Any] = {
            "abn": abn,
            "abn_formatted": format_abn(abn),
            "abn_status": code,
            "abn_status_text": status_text,
            "abn_status_from": iso_date(str(data.get("AbnStatusEffectiveFrom") or "")),
            "entity_name": str(data.get("EntityName") or ""),
            "entity_type_code": str(data.get("EntityTypeCode") or ""),
            "entity_type": str(data.get("EntityTypeName") or ""),
            "business_names": [str(b) for b in biz] if isinstance(biz, list) else [str(biz)],
            "state": str(data.get("AddressState") or ""),
            "postcode": str(data.get("AddressPostcode") or ""),
            "address_date": iso_date(str(data.get("AddressDate") or "")),
            "gst": {"from": iso_date(gst_from), "registered": bool(gst_from)},
            "acn": acn,
        }
        if acn:
            out["acn_formatted"] = format_acn(acn)
            out["acn_checksum_valid"] = acn_is_valid(acn)
            out["abn_embeds_acn"] = abn[2:] == acn
        return out

    # ── tools ───────────────────────────────────────────────────────────────

    def lookup_abn(self, abn: str, source: str = "auto") -> dict[str, Any]:
        v = validate_abn(abn)
        if not v["valid"]:
            return {"found": False, "reason": "invalid_abn", "validation": v}
        key = v["abn"]
        use_local, use_web = self._resolve(source)
        caveats: list[str] = []
        local_miss_note = None
        if use_local:
            meta = self._local_meta() or {}
            rec = self.index.get_by_abn(key)
            prov = self._local_provenance(meta)
            if rec is not None:
                shaped = self._shape_local(rec)
                caveats.append(CAVEATS["snapshot"])
                if shaped["trading_names"]:
                    caveats.append(CAVEATS["trading_names"])
                caveats.append(CAVEATS["location"])
                return {"found": True, "record": shaped, "provenance": prov, "caveats": caveats}
            local_miss_note = (
                "not in local bulk extract index"
                + ("" if prov["index_complete"] else " (index is partial)")
                + (f" as at {prov['extract_date']}" if prov["extract_date"] else "")
            )
            miss = {
                "found": False,
                "reason": "not_in_index" if prov["index_complete"] else "not_in_partial_index",
                "abn": key,
                "detail": local_miss_note + ". It may be newer than the extract, or not registered.",
                "provenance": prov,
                "caveats": [] if prov["index_complete"] else [CAVEATS["partial_index"]],
            }
            if not use_web:
                return miss
            try:
                data = self.web.abn_details(key)
            except WebError as exc:
                return {**miss, "web_fallback_error": str(exc)}
        else:
            data = self.web.abn_details(key)
        prov = self._web_provenance()
        if not data.get("Abn"):
            return {"found": False, "reason": "not_registered", "abn": key,
                    "detail": "ABN Lookup has no record of this ABN.", "provenance": prov,
                    **({"local_index": local_miss_note} if local_miss_note else {})}
        result = {"found": True, "record": self._shape_web(data), "provenance": prov,
                  "caveats": [CAVEATS["location"]]}
        if local_miss_note:
            result["local_index"] = local_miss_note
        return result

    def lookup_abns(self, abns: list[str], source: str = "local") -> dict[str, Any]:
        if source == "auto":
            source = "local" if self._local_meta() is not None else "web"
        limit = MAX_BATCH_LOCAL if source == "local" else MAX_BATCH_WEB
        if len(abns) > limit:
            raise ValueError(f"at most {limit} ABNs per call with source='{source}'")
        rows: list[dict[str, Any]] = []
        valid_keys = []
        for raw in abns:
            v = validate_abn(raw)
            rows.append({"input": v["input"], "abn": v["abn"], "valid": v["valid"],
                         **({} if v["valid"] else {"reason": v["reason"]})})
            if v["valid"]:
                valid_keys.append(v["abn"])
        self._resolve(source)
        if source == "local":
            meta = self._local_meta() or {}
            prov = self._local_provenance(meta)
            found = self.index.get_many(valid_keys)
            for row in rows:
                rec = found.get(row["abn"]) if row["valid"] else None
                row["found"] = rec is not None
                if rec:
                    row.update(
                        entity_name=rec["display_name"], abn_status=rec["abn_status"],
                        entity_type_code=rec["entity_type_ind"], entity_type=rec["entity_type_text"],
                        state=rec["state"], postcode=rec["postcode"], acn=rec["asic_number"],
                        gst_registered=rec["gst_status"] == "ACT",
                    )
        else:
            prov = self._web_provenance()
            for row in rows:
                if not row["valid"]:
                    row["found"] = False
                    continue
                try:
                    data = self.web.abn_details(row["abn"])
                except WebError as exc:
                    row.update(found=False, error=str(exc))
                    continue
                row["found"] = bool(data.get("Abn"))
                if row["found"]:
                    s = self._shape_web(data)
                    row.update(entity_name=s["entity_name"], abn_status=s["abn_status"],
                               entity_type_code=s["entity_type_code"], entity_type=s["entity_type"],
                               state=s["state"], postcode=s["postcode"], acn=s["acn"],
                               gst_registered=s["gst"]["registered"])
        summary = {
            "inputs": len(rows),
            "valid": sum(r["valid"] for r in rows),
            "found": sum(bool(r.get("found")) for r in rows),
        }
        caveats = [CAVEATS["snapshot"]] if source == "local" else []
        if source == "local" and not prov.get("index_complete"):
            caveats.append(CAVEATS["partial_index"])
        return {"summary": summary, "results": rows, "provenance": prov, "caveats": caveats}

    def lookup_acn(self, acn: str, source: str = "auto") -> dict[str, Any]:
        v = validate_acn(acn)
        if not v["valid"]:
            return {"found": False, "reason": "invalid_acn", "validation": v}
        key = v["acn"]
        use_local, use_web = self._resolve(source)
        if use_local:
            prov = self._local_provenance(self._local_meta() or {})
            recs = self.index.get_by_acn(key)
            if recs:
                return {"found": True, "records": [self._shape_local(r) for r in recs],
                        "provenance": prov, "caveats": [CAVEATS["snapshot"]]}
            miss = {"found": False, "reason": "no_abn_for_acn_in_index", "acn": key,
                    "detail": "No ABN in the local index lists this ACN. A company can hold an "
                              "ACN without an ABN.", "provenance": prov}
            if not use_web:
                return miss
            try:
                data = self.web.acn_details(key)
            except WebError as exc:
                return {**miss, "web_fallback_error": str(exc)}
        else:
            data = self.web.acn_details(key)
        prov = self._web_provenance()
        if not data.get("Abn"):
            return {"found": False, "reason": "no_abn_for_acn", "acn": key, "provenance": prov}
        return {"found": True, "records": [self._shape_web(data)], "provenance": prov}

    def search_names(
        self,
        name: str,
        *,
        mode: str = "auto",
        state: str | None = None,
        postcode: str | None = None,
        active_only: bool = False,
        name_types: list[str] | None = None,
        limit: int = 20,
        source: str = "auto",
    ) -> dict[str, Any]:
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        if mode not in ("auto", "exact", "tokens"):
            raise ValueError("mode must be auto, exact or tokens")
        if state and state.upper() not in STATES:
            raise ValueError(f"state must be one of {', '.join(STATES)}")
        limit = max(1, min(int(limit), 100))
        if name_types:
            types = [t.upper() for t in name_types]
            unknown = [t for t in types if t not in NAME_TYPES]
            if unknown:
                raise ValueError(f"unknown name type(s) {', '.join(unknown)}; use {', '.join(NAME_TYPES)}")
        else:
            # The ABR recommends avoiding trading names (not updated since 2012).
            types = list(DEFAULT_SEARCH_NAME_TYPES)
        include_trd = "TRD" in types
        scope = {"name_types_searched": types}
        if not include_trd:
            scope["trading_names_excluded"] = (
                "Trading names (TRD) are excluded by default: the ABR recommends avoiding them "
                "as they have not been updated since 2012. Pass name_types including 'TRD' to "
                "search them.")
        use_local, use_web = self._resolve(source)
        if use_local:
            out = self.index.search(name, mode=mode, state=state, postcode=postcode,
                                    active_only=active_only, name_types=types, limit=limit)
            for hit in out["results"]:
                hit["abn_formatted"] = format_abn(hit["abn"])
            res = {"query": name, "normalised_key": out["key"], "count": len(out["results"]),
                   "results": out["results"], **scope,
                   "provenance": self._local_provenance(self._local_meta() or {}),
                   "caveats": [CAVEATS["name_match"], CAVEATS["snapshot"]]}
            if not out["key"]:
                res["note"] = ("The name contains only legal-form words (e.g. PTY, LTD) or "
                               "punctuation, which matching ignores; add distinctive words.")
            if out["candidate_pool_truncated"]:
                res["note"] = ("Very common terms: only the best-ranked candidates were "
                               "considered. Add words, a state or a postcode to narrow.")
            if res["results"] or not use_web:
                return res
            try:
                names = self.web.matching_names(name, max_results=min(limit * 3, 200))
            except WebError as exc:
                return {**res, "web_fallback_error": str(exc)}
        else:
            names = self.web.matching_names(name, max_results=min(limit * 3, 200))
        results = []
        for n in names:
            if state and str(n.get("State", "")).upper() != state.upper():
                continue
            if postcode and str(n.get("Postcode", "")) != postcode:
                continue
            if active_only and n.get("IsCurrent") is False:
                continue
            if not include_trd and "trading" in str(n.get("NameType", "")).lower():
                continue
            abn = str(n.get("Abn", ""))
            results.append({
                "abn": abn, "abn_formatted": format_abn(abn), "name": n.get("Name", ""),
                "name_type": n.get("NameType", ""), "state": n.get("State", ""),
                "postcode": n.get("Postcode", ""), "score": n.get("Score"),
                "is_current": n.get("IsCurrent"),
            })
            if len(results) >= limit:
                break
        return {"query": name, "count": len(results), "results": results, **scope,
                "provenance": self._web_provenance(), "caveats": [CAVEATS["name_match"]],
                "note": "Web search filters (state/postcode/active_only) are applied client-side."}

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"local_index": {"path": str(self.index.path), "available": False},
                               "web_services": {"configured": self.web.available()}}
        if self.index.available():
            try:
                meta = self.index.meta()
                prov = self._local_provenance(meta)
                out["local_index"].update(
                    available=True,
                    complete=prov["index_complete"],
                    extract_date=prov["extract_date"],
                    extract_age_days=prov["extract_age_days"],
                    built_at=meta.get("built_at", ""),
                    records=int(meta.get("record_count", "0")),
                    names=int(meta.get("name_count", "0")),
                    duplicates_resolved=int(meta.get("duplicates_resolved", "0")),
                    full_text_search=meta.get("fts") == "1",
                    missing_sequence_numbers=meta.get("missing_sequence_numbers", ""),
                    warnings=meta.get("warnings", ""),
                )
                age = prov["extract_age_days"]
                if age is not None and age > 14:
                    out["local_index"]["stale_warning"] = (
                        f"Extract is {age} days old; the ABR publishes weekly. "
                        "Refresh with `abr-mcp update-index`."
                    )
            except IndexUnavailable as exc:
                out["local_index"]["error"] = str(exc)
        out["licence"] = LICENCE
        out["disclaimer"] = DISCLAIMER
        return out

    def codes(self) -> dict[str, Any]:
        out: dict[str, Any] = {"abn_status": ABN_STATUS, "gst_status": GST_STATUS,
                               "name_types": NAME_TYPES, "states": list(STATES)}
        if self._local_meta() is not None:
            out["entity_types"] = self.index.entity_types()
        else:
            out["entity_types_note"] = "Entity type codes are read from the local index; none is built."
        return out
