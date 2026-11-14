"""ABF Register of Sanctioned Sponsors.

The register page fills its table from a first-party endpoint, GetSanctionsData, which the page's
own script calls with a request digest that the page embeds. That endpoint is undocumented and
may change without notice, so parsing is strict: a response whose shape is not recognised fails
the refresh and leaves the previous dataset in place.

The register has no record identifier, so a record's id is a hash of its published fields. It
stays the same while the record is unchanged and changes when the ABF edits it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

import httpx

from .store import DatasetError

PAGE_URL = "https://www.abf.gov.au/about-us/what-we-do/sponsor-sanctions/register-of-sanctioned-sponsors"
ENDPOINT_URL = "https://www.abf.gov.au/_layouts/15/api/Data.aspx/GetSanctionsData"
USER_AGENT = "sanctions-au (+https://github.com/DeepCivic/civic-lab)"
MAX_BYTES = 50_000_000

REQUIRED = ["sponsorname", "tradingname", "abn", "state", "postcode", "sanctionimposed", "sanctionimposeddate",
            "sanctionenddate", "obligationbreached", "sanctioninfribreachnotice", "sanctioninfrinoticedate",
            "sanctioninfrinoticeamount", "amountstatus"]


def fetch(client: httpx.Client) -> bytes:
    """Load the page, take its request digest, and make the one call the page itself makes."""
    page = client.get(PAGE_URL)
    page.raise_for_status()
    m = re.search(r'id="__REQUESTDIGEST"[^>]*value="([^"]+)"', page.text) or \
        re.search(r'value="([^"]+)"[^>]*id="__REQUESTDIGEST"', page.text)
    if not m:
        raise DatasetError("ABF page no longer carries a request digest; the register page may have changed")
    resp = client.post(ENDPOINT_URL, content=b"{}", headers={
        "Content-Type": "application/json", "Accept": "application/json;odata=verbose",
        "X-RequestDigest": m.group(1)})
    resp.raise_for_status()
    if len(resp.content) > MAX_BYTES:
        raise DatasetError("ABF response is implausibly large; refusing it")
    return resp.content


def _s(v: object) -> str | None:
    text = str(v).strip() if v is not None else ""
    return text or None


def _ymd(v: str | None) -> str | None:
    return f"{v[:4]}-{v[4:6]}-{v[6:]}" if v and re.fullmatch(r"\d{8}", v) else None


def _dmy(v: str | None) -> str | None:
    try:
        return dt.datetime.strptime(v, "%d-%b-%Y").date().isoformat() if v else None
    except ValueError:
        return None


def parse(raw: bytes) -> list[dict[str, Any]]:
    try:
        body = json.loads(raw)["d"]
        rows = body["data"]
        ok = body["success"]
    except (ValueError, KeyError, TypeError) as exc:
        raise DatasetError(f"ABF response is not the expected shape: {exc!r}") from exc
    if ok is not True or not isinstance(rows, list) or not rows:
        raise DatasetError("ABF response reports failure or holds no records")
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or any(k not in row for k in REQUIRED):
            raise DatasetError(f"ABF record {i} is missing expected fields; the register layout may have changed")
        name = _s(row["sponsorname"]) or ""
        pending = name.endswith("*")  # the page's footnote: "* Administrative Review Tribunal review pending"
        status = re.search(r"alt='([^']*)'", _s(row["amountstatus"]) or "")
        digest = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        obligations = _s(row["obligationbreached"])
        out.append({
            "id": digest,
            "sponsor_name": name.rstrip("*").strip(),
            "pending_review": pending,
            "trading_name": _s(row["tradingname"]),
            "abn": _s(row["abn"]),
            "state": (_s(row["state"]) or "").upper() or None,
            "postcode": _s(row["postcode"]),
            "sanction_imposed": _s(row["sanctionimposed"]),
            "sanction_imposed_date": _ymd(_s(row["sanctionimposeddate"])),
            "sanction_end_date": _dmy(_s(row["sanctionenddate"])),
            "obligations_breached": [o.strip() for o in obligations.split(",")] if obligations else [],
            "infringement_notice_breaches": _s(row["sanctioninfribreachnotice"]),
            "infringement_notice_date": _s(row["sanctioninfrinoticedate"]),
            "infringement_notice_amount": _s(row["sanctioninfrinoticeamount"]),
            "infringement_notice_status": status.group(1).lower() if status else None,
        })
    return out
