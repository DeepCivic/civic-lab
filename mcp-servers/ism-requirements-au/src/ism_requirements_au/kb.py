"""Load and query the compiled knowledge base (data/kb.json). Offline, read-only."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

CLASSIFICATIONS = {
    "NC": ("non-classified", "non classified", "unclassified", "nc"),
    "OS": ("official: sensitive", "official sensitive", "official-sensitive", "official", "os"),
    "P": ("protected", "p"),
    "S": ("secret", "s"),
    "TS": ("top secret", "top-secret", "ts"),
}
CLASSIFICATION_NAMES = {"NC": "NON-CLASSIFIED", "OS": "OFFICIAL: Sensitive", "P": "PROTECTED", "S": "SECRET", "TS": "TOP SECRET"}
E8_LEVELS = ["ML1", "ML2", "ML3"]


def classification_tag(value: str) -> str:
    v = re.sub(r"\s+", " ", value.strip().lower())
    for tag, names in CLASSIFICATIONS.items():
        if v in names:
            return tag
    raise ValueError(f"unknown classification {value!r}; use one of: NON-CLASSIFIED, OFFICIAL: Sensitive, PROTECTED, SECRET, TOP SECRET")


class KB:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.built = data["built"]
        self.release = data["ism_release"]
        self.oscal = data["oscal_version"]
        self.phases: list[str] = data["phases"]
        self._rules = {e["id"]: e for e in data["rules"] + data["heuristics"]}
        self._pre = {p["id"]: p for p in data["preconditions"]}
        self._obl = {o["id"]: o for o in data["obligations"]}

    # ---- controls
    def has_control(self, cid: str) -> bool:
        return cid.upper() in self.data["controls"]

    def control(self, cid: str) -> dict | None:
        raw = self.data["controls"].get(cid.upper())
        if raw is None:
            return None
        sec = self.data["sections"][raw["g"]]
        return {"id": cid.upper(), "kind": "principle" if raw["k"] == "p" else "control", "statement": raw["s"],
                "revision": raw.get("r"), "updated": raw.get("u"), "applicability": [a for a in raw["a"].split(",") if a],
                "guideline": sec["guideline"], "section": sec["section"], "topic": raw["t"], "e8": raw.get("e", []),
                "essentials": raw.get("x", []), "aescsf": raw.get("z", []), **({"label": raw["l"]} if raw.get("l") else {})}

    def control_ids(self) -> list[str]:
        return list(self.data["controls"])

    def controls(self, kind: str = "control"):
        for cid in self.data["controls"]:
            c = self.control(cid)
            if kind == "any" or c["kind"] == kind:
                yield c

    def applies(self, c: dict, tag: str, e8_target: str | None = None) -> bool:
        """Does the control apply at this classification, or via the Essential Eight mandate?"""
        if tag in c["applicability"]:
            return True
        if e8_target and c["e8"]:
            return E8_LEVELS.index(min(c["e8"], key=E8_LEVELS.index)) <= E8_LEVELS.index(e8_target)
        return False

    def e8_min(self, cid: str) -> str | None:
        e = self.data["controls"].get(cid.upper(), {}).get("e", [])
        return min(e, key=E8_LEVELS.index) if e else None

    def section_scope(self, c: dict) -> str:
        for s in self.data["sections"]:
            if s["guideline"] == c["guideline"]:
                return s["scope"]
        return "always"

    # ---- authored layers
    def entry(self, eid: str) -> dict | None:
        return self._rules.get(eid)

    @property
    def rules(self) -> list[dict]:
        return self.data["rules"]

    @property
    def heuristics(self) -> list[dict]:
        return self.data["heuristics"]

    @property
    def preconditions(self) -> list[dict]:
        return self.data["preconditions"]

    def precondition(self, pid: str) -> dict | None:
        return self._pre.get(pid)

    @property
    def obligations(self) -> list[dict]:
        return self.data["obligations"]

    def obligation(self, oid: str) -> dict | None:
        return self._obl.get(oid)

    @property
    def essentials(self) -> dict:
        return self.data["essentials"]

    def rules_for_control(self, cid: str) -> list[str]:
        return [e["id"] for e in self._rules.values() if cid.upper() in e["controls"]]

    def sources(self) -> list[dict]:
        return self.data["sources"]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        terms = [t for t in re.findall(r"[\w.-]+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        hits = []
        for cid in self.data["controls"]:
            raw = self.data["controls"][cid]
            sec = self.data["sections"][raw["g"]]
            blob = f"{cid} {raw['s']} {raw['t']} {sec['section']}".lower()
            if all(t in blob for t in terms):
                hits.append((sum(blob.count(t) for t in terms) + (5 if cid.lower() in terms else 0), cid))
        hits.sort(key=lambda h: (-h[0], h[1]))
        return [{"id": cid, "topic": self.data["controls"][cid]["t"], "statement": self.data["controls"][cid]["s"]} for _, cid in hits[:limit]]


@lru_cache(maxsize=1)
def load() -> KB:
    with resources.files("ism_requirements_au").joinpath("data/kb.json").open(encoding="utf-8") as f:
        return KB(json.load(f))
