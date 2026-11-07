"""Optional client for the ABN Lookup JSON web services (live ABR data).

Enabled only when a GUID is configured (``ABR_GUID``; free registration at
https://abr.business.gov.au/Tools/WebServices). Endpoints:

* ``/json/AbnDetails.aspx?abn=&guid=``
* ``/json/AcnDetails.aspx?acn=&guid=``
* ``/json/MatchingNames.aspx?name=&maxResults=&guid=``

Service quirks handled here:

* Responses are JSONP (``callback({...})``) even when no callback is asked
  for; a plain JSON body is also accepted.
* Errors (including an unrecognised GUID or an unknown ABN) come back as
  HTTP 200 with a non-empty ``Message`` — they are surfaced as ``WebError``.
* The GUID is a credential: it is never included in errors or logs.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

BASE_URL = "https://abr.business.gov.au/json/"
_JSONP = re.compile(r"^\s*[A-Za-z_$][\w$]*\s*\((.*)\)\s*;?\s*$", re.S)
_GUID_RE = re.compile(r"guid=[^&\s]+", re.I)


class WebError(RuntimeError):
    """The ABR web service returned an error or could not be reached."""


def _redact(text: str, guid: str) -> str:
    text = _GUID_RE.sub("guid=REDACTED", text)
    return text.replace(guid, "REDACTED") if guid else text


def parse_jsonp(body: str) -> dict[str, Any]:
    m = _JSONP.match(body)
    payload = m.group(1) if m else body
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WebError(f"unparseable response from ABR web service: {exc}") from None
    if not isinstance(data, dict):
        raise WebError("unexpected response shape from ABR web service")
    return data


class AbrWebClient:
    def __init__(
        self,
        guid: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 15.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.guid = (guid if guid is not None else os.getenv("ABR_GUID", "")).strip()
        self.base_url = base_url or os.getenv("ABR_WEB_BASE_URL", BASE_URL)
        self.timeout = timeout
        self.retries = retries
        self._transport = transport

    def available(self) -> bool:
        return bool(self.guid)

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.guid:
            raise WebError("ABR web services are not configured (set ABR_GUID).")
        query = {**params, "guid": self.guid}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(
                    base_url=self.base_url, timeout=self.timeout, transport=self._transport,
                    headers={"User-Agent": "abr-mcp"}, follow_redirects=False,
                ) as client:
                    resp = client.get(endpoint, params=query)
                if resp.status_code >= 500:
                    raise WebError(f"ABR web service HTTP {resp.status_code}")
                if resp.status_code != 200:
                    # 3xx/4xx are not transient (e.g. a retired path redirects to an error page).
                    raise WebError(f"ABR web service HTTP {resp.status_code} for {endpoint}")
                data = parse_jsonp(resp.text)
                message = str(data.get("Message") or "").strip()
                if message:
                    raise WebError(f"ABR web service: {message}")
                return data
            except (httpx.TransportError, WebError) as exc:
                transient = isinstance(exc, httpx.TransportError) or "HTTP 5" in str(exc)
                last = exc
                if not transient or attempt == self.retries:
                    break
                time.sleep(0.5 * (2 ** attempt))
        raise WebError(_redact(str(last), self.guid)) from None

    def abn_details(self, abn: str) -> dict[str, Any]:
        return self._get("AbnDetails.aspx", {"abn": abn})

    def acn_details(self, acn: str) -> dict[str, Any]:
        return self._get("AcnDetails.aspx", {"acn": acn})

    def matching_names(self, name: str, max_results: int = 20) -> list[dict[str, Any]]:
        data = self._get("MatchingNames.aspx", {"name": name, "maxResults": max_results})
        names = data.get("Names") or []
        return [n for n in names if isinstance(n, dict)]
