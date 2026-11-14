"""Which tool groups this server offers, set by the operator through the environment.

Same convention as the sibling servers: a flag is on for 1, true, yes or on, in any case.

  SANCTIONS_ENABLE_SCREENING   DFAT and ABF screening, from local snapshots. Never uses the network. Default: on.
  SANCTIONS_ENABLE_GLEIF       GLEIF LEI lookups. Send queries to api.gleif.org. Default: off.

A group that is off is not offered to the client at all, so an agent never sees a tool it cannot use.
"""

from __future__ import annotations

import os

SCREENING_ENV = "SANCTIONS_ENABLE_SCREENING"
GLEIF_ENV = "SANCTIONS_ENABLE_GLEIF"
_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return default if not raw else raw in _TRUE


def screening_enabled() -> bool:
    return _flag(SCREENING_ENV, True)


def gleif_enabled() -> bool:
    return _flag(GLEIF_ENV, False)
