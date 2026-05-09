# flowers_rewards.py — fix "cannot access local variable 'entry'..."
from __future__ import annotations
from typing import Dict, Any, List

def find_flower_reward_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Legge i reward dei fiori direttamente da farm.flowers.flowerBeds.*.reward.items[0].name
    Ritorna una lista di dict:
      {
        "name": "Flower – reward",
        "reward_item": "<nome reward>",     # es. "Venus Bumpkin Trap"
        "bed_id": "<id aiuola>"             # opzionale, utile per dedup/debug
      }
    """
    out: List[Dict[str, Any]] = []

    if not isinstance(payload, dict):
        return out

    farm = payload.get("farm") or {}
    flowers = farm.get("flowers") or {}
    beds = flowers.get("flowerBeds") or {}

    if not isinstance(beds, dict):
        return out

    for bed_id, bed in beds.items():
        if not isinstance(bed, dict):
            continue
        reward = bed.get("reward")
        if not isinstance(reward, dict):
            continue
        items = reward.get("items") or []
        if not isinstance(items, list) or not items:
            continue

        first = items[0] if len(items) > 0 else None
        if isinstance(first, dict):
            rname = first.get("name")
            if isinstance(rname, str) and rname.strip():
                out.append({
                    "name": "Flower – reward",
                    "reward_item": rname.strip(),
                    "bed_id": str(bed_id)
                })

    return out
