"""GLEIF (Legal Entity Identifier) client: the LEI lookups of the gleif-mcp-server, rebuilt in Python.

Unlike screening, this talks to api.gleif.org, so it sends what you ask about off the machine. The
server therefore leaves it off unless SANCTIONS_ENABLE_GLEIF=1. See docs/gleif-upstream-notes.md for
where this deliberately differs from the Go server it replaces, and why.
"""

from __future__ import annotations

import copy
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

BASE_URL = "https://api.gleif.org/api/v1"
USER_AGENT = "sanctions-au (+https://github.com/DeepCivic/civic-lab)"
MAX_BATCH = 100
AUTOCOMPLETE_MAX = 10
MAX_BODY = 10_000_000

LEI_RE = re.compile(r"^[A-Z0-9]{4}[A-Z0-9]{2}[A-Z0-9]{12}[0-9]{2}$")
BIC_RE = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
ISSUER_RE = re.compile(r"^[A-Z0-9]{4,32}$")

# What each relationship tool asks GLEIF for. The parent endpoints return one record, the
# children ones a list; both shapes are handled.
RELATIONSHIPS = {
    "direct-parent": "direct-parent-relationship", "ultimate-parent": "ultimate-parent-relationship",
    "ultimate": "ultimate-parent-relationship", "children": "direct-child-relationships",
    "direct-children": "direct-child-relationships", "fund-manager": "fund-manager-relationship",
    "umbrella-fund": "umbrella-fund-relationship", "sub-funds": "sub-fund-relationships",
}
# The two reporting-exception resources GLEIF serves. There is no combined endpoint.
EXCEPTION_ENDPOINTS = ("direct-parent-reporting-exception", "ultimate-parent-reporting-exception")


class GleifError(ValueError):
    """An expected failure, safe to show the caller. Never carries a raw response body."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(f"{code}: {message}")
        self.code, self.retryable = code, retryable


def _parse(raw: str, label: str, pattern: re.Pattern[str], reason: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        raise GleifError("invalid_format", f"{label} is required")
    if not pattern.match(s):
        raise GleifError("invalid_format", f"invalid {label}: {reason}")
    return s


def parse_lei(raw: str) -> str:
    return _parse(raw, "LEI", LEI_RE, "must be 20 alphanumeric characters")


def parse_bic(raw: str) -> str:
    return _parse(raw, "BIC", BIC_RE, "must be 8 or 11 characters: 4 letters, 2 letters, 2 alphanumeric, optional 3 alphanumeric")


def parse_isin(raw: str) -> str:
    return _parse(raw, "ISIN", ISIN_RE, "must be 2 letters then 10 alphanumeric characters")


def parse_country(raw: str) -> str:
    return _parse(raw, "country", COUNTRY_RE, "must be a 2-letter ISO 3166-1 alpha-2 code")


def parse_issuer_id(raw: str) -> str:
    return _parse(raw, "issuer_id", ISSUER_RE, "must be 4-32 alphanumeric characters")


def check_digits_ok(lei: str) -> bool:
    """ISO 17442 / ISO 7064 mod 97-10: letters become 10-35, and the whole number mod 97 must be 1."""
    if len(lei) != 20 or not lei.isalnum():
        return False
    return int("".join(str(int(c, 36)) for c in lei)) % 97 == 1


class _Cache:
    """A small TTL cache. Values are copied in and out, so a caller that edits a result cannot
    change what the next caller sees."""

    def __init__(self, clock: Callable[[], float], max_entries: int = 10_000):
        self._clock, self._max, self._d, self._lock = clock, max_entries, {}, threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            hit = self._d.get(key)
            if hit is None or hit[0] < self._clock():
                self._d.pop(key, None)
                return None
            return copy.deepcopy(hit[1])

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            if len(self._d) >= self._max:
                self._d.pop(next(iter(self._d)))
            self._d[key] = (self._clock() + ttl, copy.deepcopy(value))


def simple(rec: dict[str, Any]) -> dict[str, Any]:
    ent, reg = rec.get("entity", {}), rec.get("registration", {})
    addr = ent.get("legalAddress") or {}
    return {"lei": rec["lei"], "legalName": (ent.get("legalName") or {}).get("name"), "country": addr.get("country"),
            "city": addr.get("city"), "status": ent.get("status"), "regStatus": reg.get("status")}


class Client:
    def __init__(self, *, base_url: str = BASE_URL, transport: httpx.BaseTransport | None = None,
                 rate_per_minute: float = 50, burst: int = 10, retries: int = 3, retry_delay: float = 1.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        # Redirects are refused: api.gleif.org does not redirect, so one would mean a wrong base URL
        # or a hostile response trying to point a lookup at somewhere internal.
        self._http = httpx.Client(base_url=base_url, transport=transport, follow_redirects=False,
                                  timeout=httpx.Timeout(30.0), headers={"Accept": "application/vnd.api+json",
                                                                        "User-Agent": USER_AGENT})
        self._clock, self._sleep, self._retries, self._retry_delay = clock, sleep, retries, retry_delay
        self._rate, self._burst, self._tokens, self._last = rate_per_minute / 60.0, float(burst), float(burst), clock()
        self._lock = threading.Lock()
        self._cache = _Cache(clock)

    # -- transport ----------------------------------------------------------------------------

    def _take_token(self) -> None:
        """Stay inside GLEIF's 60 requests a minute (50 here), waiting rather than failing."""
        while True:
            with self._lock:
                now = self._clock()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self._rate
            self._sleep(wait)

    def _once(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self._take_token()
        try:
            resp = self._http.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise GleifError("timeout", "the GLEIF API timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise GleifError("network_error", f"could not reach the GLEIF API ({type(exc).__name__})", retryable=True) from exc
        code = resp.status_code
        if code == 404:
            raise GleifError("not_found", "not found in the GLEIF database")
        if code == 429:
            raise GleifError("rate_limited", "the GLEIF API rate limit was hit; retry shortly", retryable=True)
        if code >= 500:
            raise GleifError("server_error", f"the GLEIF API returned HTTP {code}", retryable=True)
        if code != 200 or len(resp.content) > MAX_BODY:
            raise GleifError("server_error", f"the GLEIF API returned an unexpected response (HTTP {code})")
        try:
            body = resp.json()
        except ValueError as exc:
            raise GleifError("server_error", "the GLEIF API returned a response that is not JSON") from exc
        if not isinstance(body, dict):
            raise GleifError("server_error", "the GLEIF API returned an unexpected response shape")
        return body

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(self._retries + 1):
            try:
                return self._once(path, params)
            except GleifError as exc:
                if not exc.retryable or attempt == self._retries:
                    raise
                self._sleep(self._retry_delay * 2 ** attempt)
        raise AssertionError("unreachable")

    # -- records ------------------------------------------------------------------------------

    @staticmethod
    def _record(item: dict[str, Any]) -> dict[str, Any]:
        a = item.get("attributes") or {}
        return {"lei": item.get("id") or a.get("lei"), "entity": a.get("entity") or {}, "registration": a.get("registration") or {}}

    def get_lei(self, raw: str) -> dict[str, Any]:
        lei = parse_lei(raw)
        if (hit := self._cache.get(f"lei:{lei}")) is not None:
            return hit
        rec = self._record(self.get(f"/lei-records/{lei}")["data"])
        self._cache.set(f"lei:{lei}", rec, 3600)
        return rec

    def validate(self, raw: str) -> dict[str, Any]:
        """Never raises for a bad LEI: that is the answer. Only a definitive 'not found' is cached,
        so a GLEIF outage cannot make a good LEI look invalid for a day."""
        lei = (raw or "").strip().upper()
        base = {"lei": lei, "valid": False}
        if not LEI_RE.match(lei):
            return {**base, "format_valid": False, "registry_checked": False,
                    "message": "Invalid LEI format: must be 20 alphanumeric characters"}
        if not check_digits_ok(lei):
            return {**base, "format_valid": False, "registry_checked": False,
                    "message": "Invalid check digits: LEI fails ISO 17442 validation"}
        if (hit := self._cache.get(f"validation:{lei}")) is not None:
            return hit
        try:
            rec = self.get_lei(lei)
        except GleifError as exc:
            if exc.code == "not_found":
                out = {**base, "format_valid": True, "registry_checked": True, "message": "LEI not found in GLEIF database"}
                self._cache.set(f"validation:{lei}", out, 86400)
                return out
            return {**base, "format_valid": True, "registry_checked": False,
                    "message": f"Format and check digits are valid, but the registry could not be checked: {exc}"}
        status = rec["registration"].get("status")
        out = {"lei": lei, "valid": True, "format_valid": True, "registry_checked": True, "status": status,
               "entityStatus": rec["entity"].get("status"), "nextRenewal": (rec["registration"].get("nextRenewalDate") or "")[:10] or None,
               "message": f"Valid LEI, registration status: {status}"}
        self._cache.set(f"validation:{lei}", out, 86400)
        return out

    def batch(self, raws: list[str]) -> dict[str, Any]:
        leis = list(dict.fromkeys(parse_lei(r) for r in raws if r and r.strip()))
        if not leis:
            raise GleifError("invalid_format", "pass one or more LEI codes")
        if len(leis) > MAX_BATCH:
            raise GleifError("invalid_format", f"at most {MAX_BATCH} LEIs per request")
        found: dict[str, dict[str, Any]] = {}
        todo = []
        for lei in leis:
            hit = self._cache.get(f"lei:{lei}")
            (found.__setitem__(lei, hit) if hit is not None else todo.append(lei))
        if todo:
            body = self.get("/lei-records", {"filter[lei]": ",".join(todo), "page[size]": MAX_BATCH})
            for item in body.get("data", []):
                rec = self._record(item)
                found[rec["lei"]] = rec
                self._cache.set(f"lei:{rec['lei']}", rec, 3600)
        results = [simple(found[lei]) for lei in leis if lei in found]
        missing = [lei for lei in leis if lei not in found]
        return {"requested": len(leis), "found": len(results), "results": results, **({"notFound": missing} if missing else {})}

    # -- search -------------------------------------------------------------------------------

    @staticmethod
    def _page(body: dict[str, Any]) -> dict[str, Any] | None:
        p = (body.get("meta") or {}).get("pagination")
        return {"currentPage": p["currentPage"], "perPage": p["perPage"], "total": p["total"], "lastPage": p["lastPage"]} if p else None

    def _search(self, params: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        body = self.get("/lei-records", params)
        return [self._record(i) for i in body.get("data", [])], self._page(body)

    def search_entity(self, query: str, limit: int = 20, page: int = 1, fuzzy: bool = True) -> dict[str, Any]:
        if not (query or "").strip():
            raise GleifError("invalid_format", "query is required")
        limit, page = (limit if 1 <= limit <= MAX_BATCH else 20), max(page, 1)
        field = "filter[fulltext]" if fuzzy else "filter[entity.legalName]"
        recs, pg = self._search({field: query.strip(), "page[size]": limit, "page[number]": page})
        out: dict[str, Any] = {"count": len(recs), "results": [simple(r) for r in recs]}
        if pg:
            out["pagination"], out["hasMore"] = pg, pg["currentPage"] < pg["lastPage"]
        return out

    @staticmethod
    def _by_id(recs: list[dict[str, Any]], empty: str) -> dict[str, Any]:
        return {"found": bool(recs), "count": len(recs), "results": [simple(r) for r in recs], **({} if recs else {"message": empty})}

    def search_by_bic(self, raw: str) -> dict[str, Any]:
        bic = parse_bic(raw)
        # GLEIF stores BICs in their 11-character form, so an 8-character code finds nothing as given
        # (checked live: CHASUS33 returns 0 results, CHASUS33XXX returns the bank). Try the primary-office form first.
        tries = [bic + "XXX", bic] if len(bic) == 8 else [bic]
        for attempt in tries:
            recs, _ = self._search({"filter[bic]": attempt})
            if recs:
                break
        return self._by_id(recs, "No LEI found for this BIC code")

    def search_by_isin(self, raw: str) -> dict[str, Any]:
        recs, _ = self._search({"filter[isin]": parse_isin(raw)})
        return self._by_id(recs, "No issuer LEI found for this ISIN")

    def search_by_country(self, raw: str, limit: int = 20) -> dict[str, Any]:
        country = parse_country(raw)
        recs, _ = self._search({"filter[entity.legalAddress.country]": country,
                                "page[size]": limit if 1 <= limit <= MAX_BATCH else 20})
        return {"country": country, "count": len(recs), "results": [
            {k: s[k] for k in ("lei", "legalName", "city", "status")} for s in map(simple, recs)]}

    def autocomplete(self, prefix: str, limit: int = AUTOCOMPLETE_MAX) -> dict[str, Any]:
        if len((prefix or "").strip()) < 2:
            raise GleifError("invalid_format", "prefix must be at least 2 characters")
        limit = limit if 1 <= limit <= AUTOCOMPLETE_MAX else AUTOCOMPLETE_MAX
        try:
            data = self.get("/autocompletions", {"field": "fulltext", "q": prefix.strip()}).get("data", [])
            sugg = [{"lei": ((((d.get("relationships") or {}).get("lei-records") or {}).get("data")) or {}).get("id"),
                     "value": (d.get("attributes") or {}).get("value")} for d in data]
        except GleifError:  # the typo-tolerant search is a different, weaker answer, but better than none
            recs, _ = self._search({"filter[fulltext]": prefix.strip(), "page[size]": limit})
            sugg = [{"lei": r["lei"], "value": (r["entity"].get("legalName") or {}).get("name"),
                     "country": (r["entity"].get("legalAddress") or {}).get("country")} for r in recs]
        return {"prefix": prefix, "suggestions": sugg[:limit]}

    # -- relationships, issuers, exceptions ---------------------------------------------------

    def relationships(self, raw: str, kind: str = "direct-parent") -> dict[str, Any]:
        lei = parse_lei(raw)
        endpoint = RELATIONSHIPS.get((kind or "direct-parent").lower())
        if endpoint is None:
            raise GleifError("invalid_format", f"type must be one of: {', '.join(sorted(set(RELATIONSHIPS)))}")
        try:
            body = self.get(f"/lei-records/{lei}/{endpoint}", {"page[size]": MAX_BATCH} if endpoint.endswith("s") else None)
        except GleifError as exc:
            if exc.code == "not_found":
                raise GleifError("not_found", f"no {kind} relationship on file for {lei}, or the LEI does not exist. "
                                              "A record with no parent usually files a reporting exception instead: "
                                              "see get_reporting_exceptions.") from exc
            raise
        data = body.get("data")
        items = data if isinstance(data, list) else ([data] if data else [])
        rels = []
        for item in items:
            r = (item.get("attributes") or {}).get("relationship") or {}
            rels.append({"startNode": r.get("startNode"), "endNode": r.get("endNode"), "relationshipType": r.get("type"),
                         "relationshipStatus": r.get("status"),
                         "relationshipPeriods": [{"startDate": p.get("startDate"), "endDate": p.get("endDate"),
                                                  "periodType": p.get("type")} for p in r.get("periods") or []],
                         **({"relationshipQualifier": r["qualifiers"]} if r.get("qualifiers") else {})})
        out: dict[str, Any] = {"lei": lei, "type": kind, "relationships": rels}
        if (pg := self._page(body)) and pg["total"] > len(rels):
            out["total"], out["truncated"] = pg["total"], True
        return out

    def issuer(self, raw: str) -> dict[str, Any]:
        iid = parse_issuer_id(raw)
        item = self.get(f"/lei-issuers/{iid}")["data"]
        return self._issuer(item)

    @staticmethod
    def _issuer(item: dict[str, Any]) -> dict[str, Any]:
        a = item.get("attributes") or {}
        return {"id": item.get("id"), "name": a.get("name"), "marketingName": a.get("marketingName"),
                "website": a.get("website"), "accreditationDate": a.get("accreditationDate")}

    def issuers(self, limit: int = 100) -> dict[str, Any]:
        limit = limit if 1 <= limit <= 1000 else 100
        items: list[dict[str, Any]] = []
        total, page = 0, 1
        while True:  # GLEIF serves at most 200 a page
            body = self.get("/lei-issuers", {"page[size]": min(limit, 200), "page[number]": page})
            items += [self._issuer(i) for i in body.get("data") or []]
            pg = self._page(body)
            total = pg["total"] if pg else len(items)
            if len(items) >= limit or not pg or pg["currentPage"] >= pg["lastPage"] or not body.get("data"):
                break
            page += 1
        return {"count": len(items[:limit]), "total": total, "issuers": items[:limit], **({"truncated": True} if total > limit else {})}

    def reporting_exceptions(self, raw: str) -> dict[str, Any]:
        """The reporting exceptions an entity has filed for not naming a direct and/or ultimate parent.

        GLEIF serves these as two separate single resources; there is no combined path. A 404 on one
        means that kind is not filed, and is skipped. Any other error is returned. With neither filed
        the call is `not_found`, which cannot tell an unknown LEI from a known one that files none.
        """
        lei = parse_lei(raw)
        found = []
        for endpoint in EXCEPTION_ENDPOINTS:
            try:
                item = self.get(f"/lei-records/{lei}/{endpoint}").get("data")
            except GleifError as exc:
                if exc.code == "not_found":
                    continue
                raise
            if isinstance(item, dict) and item.get("attributes"):
                a = item["attributes"]
                found.append({"exceptionCategory": a.get("category"), "exceptionReason": a.get("reason"),
                              "exceptionReference": a.get("reference")})
        if not found:
            raise GleifError("not_found", f"no reporting exception is on file for {lei}. Either the LEI does not exist, "
                                          "or it exists and files none (for example because it reports a parent).")
        return {"lei": lei, "count": len(found), "exceptions": found}
