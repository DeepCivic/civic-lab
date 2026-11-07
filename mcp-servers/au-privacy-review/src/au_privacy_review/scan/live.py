"""Opt-in live probe of a deployed URL.

privacy-review: ignore-file
 Disabled unless AU_PRIVACY_REVIEW_LIVE=1 (or the
server is started with --allow-live). Makes a small number of GET requests to the
target origin only: the page, robots-free privacy policy discovery from links on
that page. It does not execute JavaScript, submit forms, or follow third-party links.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urljoin, urlparse

import httpx

from . import detectors as D

UA = "au-privacy-review (static privacy probe; +https://github.com/DeepCivic/civic-lab)"
TRACKER_COOKIES = re.compile(r"^(?:_fbp|_fbc|_ga|_gid|_gcl_\w+|_ttp|_uetsid|_uetvid|_hjid|_hj\w+|ajs_\w+|mp_\w+|_clck|_clsk|li_\w+)$")


def live_enabled() -> bool:
    return os.environ.get("AU_PRIVACY_REVIEW_LIVE", "").lower() in {"1", "true", "yes", "on"}


class LiveDisabled(RuntimeError):
    pass


def probe(url: str, timeout: float = 15.0) -> dict:
    if not live_enabled():
        raise LiveDisabled("live probing is off. Start the server with AU_PRIVACY_REVIEW_LIVE=1 (or `au-privacy-review serve --allow-live`) to enable it.")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    findings: list[dict] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
        r = c.get(url)
        final = str(r.url)
        html = r.text if "html" in r.headers.get("content-type", "") else ""
        if p.scheme == "http" and not final.startswith("https://"):
            findings.append({"detector": "live-no-https", "entries": ["R-APP11-TRANSPORT"], "severity": "high",
                             "message": "Site served over plain HTTP without redirect to HTTPS."})
        if final.startswith("https://") and "strict-transport-security" not in {k.lower() for k in r.headers}:
            findings.append({"detector": "live-no-hsts", "entries": ["R-APP11-TRANSPORT"], "severity": "low",
                             "message": "No Strict-Transport-Security header."})
        set_cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else []
        names = [sc.split("=", 1)[0].strip() for sc in set_cookies]
        trackers = [n for n in names if TRACKER_COOKIES.match(n)]
        if trackers:
            findings.append({"detector": "live-tracking-cookie-before-consent", "entries": ["H-TRACKING-PIXEL-SENSITIVE", "H-CONSENT-DESIGN"],
                             "severity": "medium", "message": f"Tracking cookies set on first response, before any consent interaction: {', '.join(trackers)}."})
        for det in (d for d in D.PATTERNS if d.id in {"tracking-pixel", "session-replay", "hedged-notice-language", "consent-dark-patterns"}):
            hits = [rx.search(html) for rx in det._re]
            hits = [h for h in hits if h]
            if hits:
                sev = det.severity
                if det.id in {"tracking-pixel", "session-replay"} and D.SENSITIVE_CONTEXT.search(html[:200000]):
                    sev = "critical" if det.id == "tracking-pixel" else "high"
                findings.append({"detector": f"live-{det.id}", "entries": det.entries, "severity": sev, "message": det.message,
                                 "evidence": D.redact(hits[0].group(0))})
        forms_http = re.findall(r"<form[^>]+action\s*=\s*['\"](http://[^'\"]+)", html, re.I)
        if forms_http:
            findings.append({"detector": "live-form-http", "entries": ["R-APP11-TRANSPORT"], "severity": "high",
                             "message": f"Form posts over plain HTTP: {forms_http[0]}"})
        third_party = sorted({urlparse(s).netloc for s in re.findall(r"<script[^>]+src\s*=\s*['\"](https?://[^'\"]+)", html, re.I)
                              if urlparse(s).netloc and urlparse(s).netloc != urlparse(final).netloc})
        links = re.findall(r"<a[^>]+href\s*=\s*['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", html, re.I | re.S)
        policy_url = next((urljoin(final, h) for h, t in links if re.search(r"privacy", h + " " + t, re.I)), None)
        policy: dict = {"found": bool(policy_url), "url": policy_url}
        if not policy_url:
            findings.append({"detector": "live-privacy-policy-missing", "entries": ["R-APP1.3-NO-PRIVACY-POLICY"], "severity": "high",
                             "message": "No privacy policy link found on the page."})
        elif urlparse(policy_url).netloc == urlparse(final).netloc:
            pr = c.get(policy_url)
            text = re.sub(r"<[^>]+>", " ", pr.text)
            missing = [label for label, rx in (
                ("kinds of personal information", r"collect"), ("access and correction", r"access[^.]{0,80}correct|correct[^.]{0,80}access"),
                ("complaints", r"complain"), ("overseas disclosure", r"overseas|outside\s+(?:of\s+)?Australia|other\s+countries"),
                ("automated decisions (APP 1.7, from 10 December 2026)", r"automated\s+decision|computer\s+program"))
                if not re.search(rx, text, re.I)]
            policy.update({"status": pr.status_code, "missing_app_1_4_matters": missing})
            if missing:
                findings.append({"detector": "live-privacy-policy-contents", "entries": ["R-APP1.4-POLICY-CONTENTS", "R-APP1.7-AUTOMATED-DECISIONS"],
                                 "severity": "medium", "message": f"Keyword check: the privacy policy page may not cover: {', '.join(missing)}. Read the policy to confirm."})
    return {"url": url, "final_url": final, "status": r.status_code, "third_party_script_hosts": third_party,
            "cookies_on_first_response": names, "privacy_policy": policy, "findings": findings,
            "caveats": ["Single unauthenticated GET without JavaScript: scripts injected by tag managers, and cookies set client-side, are not seen.",
                        "Signals, not legal conclusions. Not legal advice."]}
