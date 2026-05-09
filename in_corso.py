from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import logging

# Se questi import servono davvero altrove, tienili.
# Non scrivere `sections.append(...)` qui: va fatto nel renderer/tempo.
from minerals import find_mineral_items
from flowers import find_flower_items

from config import CRAFT_TIME_MS, COOK_TIME_MS
from notifications_old import notification_manager

log = logging.getLogger("sflbot")


def find_in_progress_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cerca ricorsivamente tutti gli elementi 'in corso' nel payload (esclusi crops)."""
    items: List[Dict[str, Any]] = []

    def _scan(node, path: str = ""):
        if isinstance(node, dict):
            # Crafting (Workshop)
            if node.get("name") and node.get("readyAt") and "workshop" in path.lower():
                items.append({
                    "type": "craft",
                    "name": node.get("name"),
                    "readyAt": node.get("readyAt"),
                    "data": node,
                })

            # Cooking (Kitchen)
            if node.get("name") and node.get("readyAt") and "kitchen" in path.lower():
                items.append({
                    "type": "cook",
                    "name": node.get("name"),
                    "readyAt": node.get("readyAt"),
                    "data": node,
                })

            # Smelting (Fire Pit)
            if node.get("name") and node.get("readyAt") and "firepit" in path.lower():
                items.append({
                    "type": "smelt",
                    "name": node.get("name"),
                    "readyAt": node.get("readyAt"),
                    "data": node,
                })

            # Ricorsione
            for k, v in node.items():
                _scan(v, f"{path}.{k}" if path else k)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                _scan(item, f"{path}[{i}]")

    _scan(payload)
    
    # NOTA: Gli alveari (beehives) sono ora gestiti dalla sezione dedicata "Alveari" in tempo.py
    # tramite la funzione _future_beehives, quindi non li includiamo qui
    
    return items


def compute_ready_ms(item: Dict[str, Any]) -> Optional[int]:
    """Calcola il ready_ms per elementi non-crop."""
    return item.get("readyAt")


async def check_ready_items(payload: Dict[str, Any], user_id: int, bot):
    """
    Controlla se ci sono elementi pronti (non-crop) e invia notifiche.
    N.B. Le notifiche per chest/sciame sono gestite in notifications.py.
    """
    items = find_in_progress_items(payload)
    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    for item in items:
        ready_ms = compute_ready_ms(item)
        if ready_ms and ready_ms <= current_ms:
            await notification_manager.add_notification(user_id, item["type"], item["name"])