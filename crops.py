from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging

from config import GROWTH_MS, BASE_CROPS, FLOWER_GROWTH_MS, FRUIT_REGEN_MS
from utils import to_ms

log = logging.getLogger("sflbot")

def walk_crop_objects(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cerca ricorsivamente oggetti crop nel payload"""
    crops = []
    
    def _scan(node, path=""):
        if isinstance(node, dict):
            if node.get("name") and node.get("plantedAt"):
                crops.append(node)
            for k, v in node.items():
                _scan(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _scan(item, f"{path}[{i}]")
    
    _scan(payload)
    return crops

def crop_display_name(node: Dict[str, Any]) -> str:
    """Restituisce il nome visualizzabile del crop"""
    return node.get("name", "Crop")

def _get_scarecrow_time_reduction(payload: Dict[str, Any]) -> float:
    """Ritorna la riduzione tempo SOLO da Basic Scarecrow"""
    farm = payload.get("farm", {})
    collectibles = farm.get("collectibles", {})
    
    if "Basic Scarecrow" in collectibles:
        return 0.30
    return 0.0

def compute_ready_ms(node: Dict[str, Any], planted_ms: Optional[int], boosted_ms: Optional[int], payload: Dict[str, Any]) -> Tuple[Optional[int], Dict[str, Any]]:
    """
    Calcola il ready_ms per un crop.
    
    IMPORTANTE: 
    - planted_ms è già in millisecondi (gestito da to_ms())
    - GROWTH_MS è in millisecondi
    - boosted_ms dall'API può essere in millisecondi
    
    Returns:
        (ready_ms, debug_info)
    """
    name = node.get("name")
    if not name or not planted_ms:
        return None, {}
    
    # Ottieni tempo base in millisecondi da config
    base_ms = GROWTH_MS.get(name)
    if not base_ms:
        log.warning(f"Crop {name} non ha tempo di crescita definito in GROWTH_MS")
        return None, {}
    
    # Se c'è un tempo boostato dall'API, usa quello
    if boosted_ms is not None and boosted_ms > 0:
        ready_ms = planted_ms + boosted_ms
        return ready_ms, {"source": "api_boosted", "boosted_ms": boosted_ms}
    
    # Altrimenti calcola con boost da spaventapasseri
    effective_base_ms = base_ms
    reduction = 0.0
    
    if name in BASE_CROPS:
        reduction = _get_scarecrow_time_reduction(payload)
        if reduction > 0:
            effective_base_ms = int(base_ms * (1 - reduction))
    
    ready_ms = planted_ms + effective_base_ms
    
    debug_info = {
        "source": "config_base",
        "base_ms": base_ms,
        "reduction": reduction,
        "effective_ms": effective_base_ms
    }
    
    return ready_ms, debug_info

def group_rows(rows: List[Tuple[int, str]], threshold_ms: int) -> List[Tuple[int, str, int]]:
    """
    Raggruppa rows per tempo e nome entro threshold_ms.
    
    Args:
        rows: Lista di tuple (timestamp_ms, nome)
        threshold_ms: Soglia di raggruppamento in millisecondi
        
    Returns:
        Lista di tuple (timestamp_anchor, nome, count)
    """
    if not rows:
        return []
    
    grouped = []
    rows_sorted = sorted(rows, key=lambda x: x[0])
    
    current_group = []
    for t, n in rows_sorted:
        if not current_group:
            current_group.append((t, n))
        else:
            last_t, last_n = current_group[-1]
            # Raggruppa se stesso nome E entro soglia temporale
            if n == last_n and abs(t - last_t) <= threshold_ms:
                current_group.append((t, n))
            else:
                # Chiudi gruppo precedente
                anchor_t, anchor_n = current_group[0]
                grouped.append((anchor_t, anchor_n, len(current_group)))
                # Inizia nuovo gruppo
                current_group = [(t, n)]
    
    # Chiudi ultimo gruppo
    if current_group:
        anchor_t, anchor_n = current_group[0]
        grouped.append((anchor_t, anchor_n, len(current_group)))
    
    return grouped

def find_crop_items(payload: dict) -> list[dict]:
    """
    SOLO crops (no fiori, no frutta). Dedup per (name, ready_ms).
    """
    flower_names = set((FLOWER_GROWTH_MS or {}).keys()) if "FLOWER_GROWTH_MS" in globals() else set()
    fruit_names  = set((FRUIT_REGEN_MS  or {}).keys()) if "FRUIT_REGEN_MS"  in globals() else set()
    all_sets = []
    for nm in ("BASE_CROPS", "MEDIUM_CROPS", "ADVANCED_CROPS"):
        if nm in globals() and globals()[nm]:
            try:
                all_sets.append(set(globals()[nm]))
            except Exception:
                pass
    crop_whitelist = set().union(*all_sets) if all_sets else (set(GROWTH_MS.keys()) - flower_names - fruit_names)
    out: list[dict] = []
    seen = set()
    try:
        nodes = walk_crop_objects(payload)
    except Exception:
        nodes = []
    for node in nodes:
        name = node.get("name")
        if not name or name in flower_names or name in fruit_names or name not in crop_whitelist:
            continue
        planted_raw = node.get("plantedAt") or node.get("createdAt")
        planted_ms = to_ms(planted_raw)
        if not planted_ms:
            continue
        base_ms = GROWTH_MS.get(name) or (24 * 60 * 60 * 1000)
        ready_ms = planted_ms + base_ms
        key = (name, int(ready_ms))
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "ready_ms": ready_ms})
    return out