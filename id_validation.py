"""
ID number format validation for Identity Check.

Checks FORMAT only (is this a well-formed number of the claimed type?),
never authenticity. No UIDAI/NSDL lookups — consistent with IRDAI's
prohibition on live e-KYC for this use.
"""
import re

# --- Verhoeff tables (Aadhaar's check-digit scheme) ---
_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0],
]
_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8],
]


def _verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def _clean(value: str) -> str:
    return re.sub(r"[\s\-]", "", (value or "")).upper()


def _aadhaar(n):
    if not n.isdigit():
        return "Aadhaar must contain digits only."
    if len(n) != 12:
        return f"Aadhaar must be exactly 12 digits (got {len(n)})."
    if n[0] in "01":
        return "Aadhaar cannot start with 0 or 1."
    if not _verhoeff_ok(n):
        return "Aadhaar check digit is invalid — likely a typo."
    return None


def _pan(n):
    if len(n) != 10:
        return f"PAN must be exactly 10 characters (got {len(n)})."
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", n):
        return "PAN must be 5 letters, 4 digits, 1 letter (e.g. ABCPE1234F)."
    if n[3] not in "ABCFGHJLPT":
        return "PAN 4th character is not a valid holder type."
    return None


def _passport(n):
    if not re.fullmatch(r"[A-Z][0-9]{7}", n):
        return "Indian passport number must be 1 letter followed by 7 digits (e.g. K1234567)."
    return None


def _voter_id(n):
    if not re.fullmatch(r"[A-Z]{3}[0-9]{7}", n):
        return "Voter ID (EPIC) must be 3 letters followed by 7 digits."
    return None


_RULES = {
    "aadhaar": _aadhaar,
    "pan": _pan,
    "passport": _passport,
    "voter id": _voter_id,
    "voter_id": _voter_id,
    "epic": _voter_id,
}


def validate_id(id_type: str, id_number: str):
    """
    Returns (ok, normalized_number, error_message).
    Unknown ID types pass with no format rule applied (ok=True, error=None).
    """
    n = _clean(id_number)
    if not n:
        return False, n, "ID number is empty."
    rule = _RULES.get((id_type or "").strip().lower())
    if rule is None:
        return True, n, None
    err = rule(n)
    return (err is None), n, err


def mask_id(id_type: str, id_number: str) -> str:
    """Aadhaar is masked to last 4 digits for storage/display; others unchanged."""
    n = _clean(id_number)
    if (id_type or "").strip().lower() == "aadhaar" and len(n) >= 4:
        return "XXXX XXXX " + n[-4:]
    return n
