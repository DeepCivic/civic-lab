"""Regenerate ``_phrase_data.py`` from Harper's phrase_set_corrections source.

Usage:
    python tools/generate_phrase_data.py /path/to/harper/harper-core/src/linting/phrase_set_corrections/mod.rs

Extracts both the 1-to-1 and many-to-many phrase mappings and writes them to
src/australian_writing/_phrase_data.py. Harper is Apache-2.0 licensed; see NOTICE.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "australian_writing" / "_phrase_data.py"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def extract(src: str) -> dict[str, list[str]]:
    one_start = src.index("add_1_to_1_mappings!(group")
    many_start = src.index("add_many_to_many_mappings!(group")
    phrases: dict[str, list[str]] = {}

    for bad, good in re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)"\s*\)', src[one_start:many_start]):
        phrases.setdefault(_norm(bad), [])
        if good not in phrases[_norm(bad)]:
            phrases[_norm(bad)].append(good)

    for badg, goodg in re.findall(r'\(&\[([^\]]*)\],\s*&\[([^\]]*)\]\)', src[many_start:], re.S):
        bads = re.findall(r'"([^"]+)"', badg)
        goods = re.findall(r'"([^"]+)"', goodg)
        for b in bads:
            phrases.setdefault(_norm(b), [])
            for g in goods:
                if g not in phrases[_norm(b)]:
                    phrases[_norm(b)].append(g)

    return {k: v for k, v in phrases.items() if k and v and any(_norm(x) != k for x in v)}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    phrases = dict(sorted(extract(Path(sys.argv[1]).read_text(encoding="utf-8")).items()))
    lines = [
        '"""Phrase-correction data for the grammar checker.',
        "",
        "Auto-generated from Harper's `phrase_set_corrections` rule set",
        "(https://github.com/Automattic/harper, Apache-2.0). Each entry maps a",
        "non-standard phrase to one or more suggested corrections. Do not edit by",
        "hand; regenerate with tools/generate_phrase_data.py. See NOTICE.",
        '"""',
        "",
        "# bad phrase (lower-case, single-spaced) -> list of suggested corrections",
        "PHRASE_CORRECTIONS = {",
        *[f"    {k!r}: {v!r}," for k, v in phrases.items()],
        "}",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(phrases)} phrases to {OUT}")


if __name__ == "__main__":
    main()
