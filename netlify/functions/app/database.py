"""Fictional verified system inventory database for SalesEasy."""
import re
from typing import List, Optional, Dict, Any
from app.models import InventoryItem


VERIFIED_INVENTORY: List[Dict[str, Any]] = [
    {
        "outlet": "Indiranagar Mart",
        "sku": "Cola 500ml",
        "system_stock": 0,
        "unit": "units",
        "last_verified": "2026-11-02 08:00 AM IST",
    },
    {
        "outlet": "Metro Fresh",
        "sku": "Cola 500ml",
        "system_stock": 48,
        "unit": "units",
        "last_verified": "2026-11-02 08:30 AM IST",
    },
    {
        "outlet": "City Corner",
        "sku": "Juice 1L",
        "system_stock": 12,
        "unit": "units",
        "last_verified": "2026-11-02 09:00 AM IST",
    },
]


def get_all_inventory() -> List[InventoryItem]:
    """Return all verified inventory items."""
    return [InventoryItem(**item) for item in VERIFIED_INVENTORY]


def find_matching_records(text: str, outlet_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search the verified database for any outlet and SKU mentions in the field update text.
    Returns list of matched records with their verified system stock.
    """
    normalized_text = text.lower()
    matches = []

    for item in VERIFIED_INVENTORY:
        outlet_name = item["outlet"].lower()
        sku_name = item["sku"].lower()
        sku_terms = re.split(r"[\s\-_]+", sku_name)

        # Match outlet
        outlet_matched = False
        if outlet_hint and outlet_hint.lower() in outlet_name:
            outlet_matched = True
        elif outlet_name in normalized_text:
            outlet_matched = True
        else:
            # Check partial outlet name (e.g., 'Indiranagar' or 'Metro')
            parts = outlet_name.split()
            if any(part in normalized_text for part in parts if len(part) > 3):
                outlet_matched = True

        # Match SKU
        sku_matched = False
        if sku_name in normalized_text:
            sku_matched = True
        elif all(term in normalized_text for term in sku_terms):
            sku_matched = True
        elif any(term in normalized_text for term in ["cola", "coke"] if "cola" in sku_name):
            sku_matched = True
        elif any(term in normalized_text for term in ["juice"] if "juice" in sku_name):
            sku_matched = True

        if outlet_matched and sku_matched:
            matches.append(item)
        elif outlet_matched and not sku_matched:
            # Store found, record associated store records for context
            matches.append(item)

    # Deduplicate matches
    seen = set()
    unique_matches = []
    for m in matches:
        key = (m["outlet"], m["sku"])
        if key not in seen:
            seen.add(key)
            unique_matches.append(m)

    return unique_matches

