from typing import Optional
import re


def validate_barcode(barcode: Optional[str]) -> bool:
    """Valide un code-barres (EAN-13, UPC, etc.)"""
    if not barcode:
        return True

    # Accepte les formats standards
    return bool(re.match(r"^[\d\-]+$", barcode))


def validate_pairing_code(code: str) -> bool:
    """Valide un code de jumelage"""
    return bool(re.match(r"^\d{6}$", code))


def sanitize_search_query(query: str) -> str:
    """Nettoie une requête de recherche"""
    # Supprimer les caractères spéciaux dangereux
    return re.sub(r"[^\w\s\-]", "", query).strip()
