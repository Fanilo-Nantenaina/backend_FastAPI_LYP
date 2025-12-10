from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import date


class DetectedProduct(BaseModel):
    product_name: str
    category: str
    count: int
    packaging_text: Optional[str] = ""
    expiry_date_text: Optional[str] = None
    estimated_shelf_life_days: Optional[int] = None


class DetectedProductMatch(BaseModel):
    """Produit détecté avec matching automatique"""

    detected_name: str
    detected_count: int
    confidence: float

    matched_item_id: Optional[int] = None
    matched_product_name: Optional[str] = None
    available_quantity: Optional[float] = None
    match_score: Optional[float] = None

    possible_matches: List[Dict[str, Any]] = []


class ConsumeAnalysisResponse(BaseModel):
    """Réponse pour analyse en mode SORTIE"""

    timestamp: str
    detected_count: int
    detected_products: List[DetectedProductMatch]
    requires_manual_review: bool


class VisionAnalysisResponse(BaseModel):
    timestamp: str
    detected_count: int
    items_added: int
    items_updated: int
    needs_manual_entry: List[Dict[str, Any]]
    detected_products: List[Dict[str, Any]]


class ManualEntryRequest(BaseModel):
    inventory_item_id: int
    expiry_date: date
