"""Australian Writing MCP: deterministic content quality checks.

Three checks are exposed:
  * check_spelling  - Australian English spelling (Hunspell en_AU + conventions)
  * check_grammar   - deterministic rule-based grammar/punctuation checks
  * get_reading_level - readability mapped to Australian school year level
"""

from .spelling import check_spelling
from .grammar import check_grammar
from .readability import get_reading_level

__all__ = ["check_spelling", "check_grammar", "get_reading_level"]
