from typing import Optional
import re


def validate_barcode(barcode: Optional[str]) -> bool:
    if not barcode:
        return True

    return bool(re.match(r"^[\d\-]+$", barcode))


def validate_pairing_code(code: str) -> bool:
    return bool(re.match(r"^\d{6}$", code))


def sanitize_search_query(query: str) -> str:
    return re.sub(r"[^\w\s\-]", "", query).strip()
