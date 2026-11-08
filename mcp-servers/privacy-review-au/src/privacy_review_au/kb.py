"""Load and query the compiled knowledge base (data/kb.json). Offline, read-only."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources


class KB:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.built = data.get("built")
        self._sources = {s["id"]: s for s in data["sources"]}
        self._entries = {e["id"]: e for e in data["rules"] + data["heuristics"]}

    @property
    def rules(self) -> list[dict]:
        return self.data["rules"]

    @property
    def heuristics(self) -> list[dict]:
        return self.data["heuristics"]

    def source(self, sid: str) -> dict | None:
        return self._sources.get(sid)

    def entry(self, eid: str) -> dict | None:
        return self._entries.get(eid)

    def sources(self) -> list[dict]:
        return self.data["sources"]

    def app(self, number: int) -> dict | None:
        return self.data["apps"].get(str(number))

    def register(self) -> list[dict]:
        return self.data["oaic_register"]

    def cited_by(self, sid: str) -> list[str]:
        return [e["id"] for e in self._entries.values()
                if sid in e.get("derived_from", []) or any(c["source"] == sid or c.get("quote_source") == sid for c in e["citations"])]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        terms = [t for t in re.findall(r"[\w.]+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        hits = []

        def score(text: str) -> int:
            low = text.lower()
            return sum(low.count(t) for t in terms) if all(t in low for t in terms) else 0

        for e in self._entries.values():
            blob = " ".join([e["id"], e["title"], " ".join(e["provisions"]), e.get("requirement", ""), e.get("concern", ""),
                             e.get("reasoning", ""), " ".join(e.get("signals", []))] + [c["quote"] for c in e["citations"]])
            if s := score(blob):
                hits.append({"type": e["kind"], "id": e["id"], "title": e["title"], "score": s})
        for s in self._sources.values():
            if sc := score(" ".join([s["id"], s["citation"], s.get("status", ""), s.get("notes", "")])):
                hits.append({"type": "source", "id": s["id"], "title": s["citation"], "score": sc})
        for r in self.register():
            blob = " ".join(str(r.get(k) or "") for k in ("title", "legislative_provision", "catchword_summary", "determination"))
            if sc := score(blob):
                hits.append({"type": "oaic_determination", "id": r.get("citation"), "title": r.get("title"), "score": sc,
                             "provisions": r.get("legislative_provision"), "url": r.get("url")})
        hits.sort(key=lambda h: (-h["score"], h["type"] != "rule", h["type"] != "heuristic"))
        return hits[:limit]


@lru_cache(maxsize=1)
def load() -> KB:
    with resources.files("privacy_review_au").joinpath("data/kb.json").open(encoding="utf-8") as f:
        return KB(json.load(f))
