"""ABN / ACN normalisation and check-digit validation.

Deterministic and offline. The algorithms are the published ATO (ABN) and
ASIC (ACN/ARBN) check-digit rules.

Normalisation is deliberately conservative: it strips the formatting people
and spreadsheets add (spaces, dashes, an ``ABN`` prefix, Excel's ``.0`` and
scientific-notation float coercion) but never guesses missing digits. Where a
value looks like it lost leading zeros (common for ACNs that went through a
spreadsheet), the zero-padded candidate is *reported*, not silently used.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
ACN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 1)

# "51824753556.0" / "5.1824753556E+10" — what a numeric spreadsheet cell
# turns an identifier into.
_FLOAT_RE = re.compile(r"^\s*\d+(\.\d+)?([eE][+-]?\d+)?\s*$")


def _digits(value: Any) -> tuple[str, list[str]]:
    """Return (digit string, notes) for an arbitrary identifier value."""
    notes: list[str] = []
    if value is None:
        return "", notes
    if isinstance(value, bool):
        return "", notes
    if isinstance(value, int):
        return str(value), notes
    if isinstance(value, float):
        if value.is_integer():
            notes.append("numeric_input_coerced")
            return str(int(value)), notes
        return "", notes
    text = str(value).strip()
    if _FLOAT_RE.match(text) and ("." in text or "e" in text.lower()):
        try:
            dec = Decimal(text)
        except InvalidOperation:
            dec = None
        if dec is not None and dec == dec.to_integral_value():
            notes.append("float_formatting_removed")
            return str(int(dec)), notes
    return re.sub(r"\D", "", text), notes


def abn_is_valid(digits: str) -> bool:
    """True if *digits* is an 11-digit string passing the ABN checksum."""
    if len(digits) != 11 or not digits.isdigit() or digits[0] == "0":
        return False
    nums = [int(c) for c in digits]
    nums[0] -= 1
    return sum(w * d for w, d in zip(ABN_WEIGHTS, nums)) % 89 == 0


def acn_is_valid(digits: str) -> bool:
    """True if *digits* is a 9-digit string passing the ACN/ARBN checksum."""
    if len(digits) != 9 or not digits.isdigit():
        return False
    total = sum(w * int(d) for w, d in zip(ACN_WEIGHTS, digits[:8]))
    return (10 - total % 10) % 10 == int(digits[8])


def format_abn(digits: str) -> str:
    """``51824753556`` → ``51 824 753 556`` (ATO display format)."""
    if len(digits) != 11:
        return digits
    return f"{digits[:2]} {digits[2:5]} {digits[5:8]} {digits[8:]}"


def format_acn(digits: str) -> str:
    """``004085616`` → ``004 085 616``."""
    if len(digits) != 9:
        return digits
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def normalise_abn(value: Any) -> str:
    """11-digit ABN key, or ``""`` if the input is not a valid ABN.

    This is the join key: exact, checksum-verified, no fuzzy recovery.
    """
    digits, _ = _digits(value)
    return digits if abn_is_valid(digits) else ""


def normalise_acn(value: Any) -> str:
    """9-digit ACN key, or ``""`` if the input is not a valid ACN."""
    digits, _ = _digits(value)
    return digits if acn_is_valid(digits) else ""


def validate_abn(value: Any) -> dict[str, Any]:
    """Explain whether *value* is a structurally valid ABN."""
    digits, notes = _digits(value)
    result: dict[str, Any] = {
        "input": "" if value is None else str(value),
        "digits": digits,
        "valid": False,
        "abn": "",
        "formatted": "",
        "reason": "",
        "notes": notes,
    }
    if not digits:
        result["reason"] = "no_digits"
    elif len(digits) < 11:
        result["reason"] = "too_few_digits"
    elif len(digits) > 11:
        result["reason"] = "too_many_digits"
        if len(digits) in (20, 22):
            result["notes"].append("may_contain_two_identifiers")
    elif digits[0] == "0":
        result["reason"] = "leading_zero_not_permitted"
    elif not abn_is_valid(digits):
        result["reason"] = "checksum_failed"
    else:
        result.update(valid=True, abn=digits, formatted=format_abn(digits), reason="ok")
    # A 9-digit value passed as an ABN is very often an ACN.
    if len(digits) == 9 and acn_is_valid(digits):
        result["notes"].append("looks_like_acn")
    return result


def validate_acn(value: Any) -> dict[str, Any]:
    """Explain whether *value* is a structurally valid ACN (or ARBN)."""
    digits, notes = _digits(value)
    result: dict[str, Any] = {
        "input": "" if value is None else str(value),
        "digits": digits,
        "valid": False,
        "acn": "",
        "formatted": "",
        "reason": "",
        "notes": notes,
    }
    if not digits:
        result["reason"] = "no_digits"
    elif len(digits) > 9:
        result["reason"] = "too_many_digits"
        if len(digits) == 11 and abn_is_valid(digits):
            result["notes"].append("looks_like_abn")
            if acn_is_valid(digits[2:]):
                result["notes"].append("abn_embeds_valid_acn")
                result["acn_from_abn_suffix"] = digits[2:]
    elif len(digits) < 9:
        result["reason"] = "too_few_digits"
        padded = digits.zfill(9)
        if acn_is_valid(padded):
            # Spreadsheets drop leading zeros. Report, don't assume.
            result["notes"].append("possible_leading_zero_loss")
            result["zero_padded_candidate"] = padded
    elif not acn_is_valid(digits):
        result["reason"] = "checksum_failed"
    else:
        result.update(valid=True, acn=digits, formatted=format_acn(digits), reason="ok")
    return result
