# minerals.py
from typing import Dict, Any, List, Optional

# Tempi di rigenerazione (ms) definiti in config.py
try:
    from config import MINERAL_REGEN_MS
except Exception:
    MINERAL_REGEN_MS = {}

# bucket -> nome canonico (in base al payload che mi hai mostrato)
_BUCKET_TO_NAME: Dict[str, str] = {
    "stones":      "Stone",
    "iron":        "Iron",
    "gold":        "Gold",
    "crimstones":  "Crimstone",
    "sunstones":   "Sunstone",
    "oilReserves": "Oil",
}

# Bucket “stone-like” che usano stone.minedAt
_STONE_LIKE = {"stones", "iron", "gold", "crimstones", "sunstones"}

def _to_ms(v) -> Optional[int]:
    if v is None:
        return None
    try:
        n = int(v)
        return n * 1000 if n < 10**11 else n
    except Exception:
        return None

def _ready_time(bucket: str, node: Dict[str, Any], canon: str) -> Optional[int]:
    """
    Calcola ready_ms per un nodo del bucket, con fallback a createdAt.
      - stones/iron/gold/crimstones/sunstones: usa node["stone"]["minedAt"] se >0, altrimenti createdAt
      - oilReserves: usa node["oil"]["drilledAt"] se >0, altrimenti createdAt
      - poi aggiunge MINERAL_REGEN_MS[canon]
    """
    regen = MINERAL_REGEN_MS.get(canon)
    if not regen:
        return None

    base = None
    if bucket in _STONE_LIKE:
        st = node.get("stone") if isinstance(node.get("stone"), dict) else None
        mined = _to_ms(st.get("minedAt")) if st else None
        base = mined if (mined and mined > 0) else _to_ms(node.get("createdAt"))
    elif bucket == "oilReserves":
        oil = node.get("oil") if isinstance(node.get("oil"), dict) else None
        drilled = _to_ms(oil.get("drilledAt")) if oil else None
        base = drilled if (drilled and drilled > 0) else _to_ms(node.get("createdAt"))
    else:
        base = _to_ms(node.get("createdAt"))

    return (base + int(regen)) if base else None

def _iter_nodes(bucket_obj: Any) -> List[Dict[str, Any]]:
    """
    I bucket nel tuo payload sono dict { id -> node }.
    Gestiamo anche liste per sicurezza.
    """
    out: List[Dict[str, Any]] = []
    if isinstance(bucket_obj, dict):
        for _, node in bucket_obj.items():
            if isinstance(node, dict):
                out.append(node)
    elif isinstance(bucket_obj, list):
        for node in bucket_obj:
            if isinstance(node, dict):
                out.append(node)
    return out

def find_mineral_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Trova minerali OVUNQUE nel payload cercando ricorsivamente i bucket noti.
    Ritorna: [{"name": <Stone/Iron/...>, "ready_ms": <int>}] deduplicati per (name, ready_ms).
    """
    out: List[Dict[str, Any]] = []
    seen = set()

    def walk(obj: Any):
        if isinstance(obj, dict):
            # 1) processa eventuali bucket minerali presenti a questo livello
            for bkey, canon in _BUCKET_TO_NAME.items():
                bucket_obj = obj.get(bkey)
                if bucket_obj:
                    for node in _iter_nodes(bucket_obj):
                        ready = _ready_time(bkey, node, canon)
                        if not ready:
                            continue
                        key = (canon, ready)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append({"name": canon, "ready_ms": ready})
            # 2) continua la ricorsione nei valori
            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for el in obj:
                walk(el)

        # scalari: niente da fare

    walk(payload)
    out.sort(key=lambda x: x["ready_ms"])
    return out
