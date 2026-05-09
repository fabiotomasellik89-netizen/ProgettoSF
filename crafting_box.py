# crafting_box.py - Versione corretta senza "Crafting Box —" nel nome
from __future__ import annotations
from typing import Any, Dict, List, Optional

# --- helper minimi ----------------------------------------------------------
def _to_ms(v) -> Optional[int]:
    if v is None: return None
    try:
        n = int(v)
        return n * 1000 if n < 10**11 else n
    except Exception:
        return None

def _extract_ready_ms(d: Dict[str, Any]) -> Optional[int]:
    if not isinstance(d, dict): return None
    for k in ("readyAt", "ready_at", "readyMs", "ready_ms", "availableAt"):
        ms = _to_ms(d.get(k))
        if isinstance(ms, int) and ms > 0:
            return ms
    # annidati comuni
    for inner in ("progress","state","status"):
        sub = d.get(inner)
        if isinstance(sub, dict):
            ms = _extract_ready_ms(sub)
            if isinstance(ms, int) and ms > 0:
                return ms
    return None

def _label_from(d: Dict[str, Any]) -> str:
    """Estrae il nome dell'item dalla struttura craftingBox"""
    # Prova a estrarre da item.collectible
    item = d.get("item")
    if isinstance(item, dict):
        for k in ("collectible", "name", "label", "type", "product"):
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    
    # Prova a estrarre da name diretto
    name = d.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    
    # fallback
    return "Item"

def _is_crafting_active(d: Dict[str, Any]) -> bool:
    """Verifica se la craftingBox è attivamente in produzione"""
    if not isinstance(d, dict):
        return False
    
    status = d.get("status", "").lower()
    
    # Status "crafting" o "active" indica produzione attiva
    if status in ("crafting", "active", "inprogress", "in-progress", "in_progress"):
        return True
    
    # Se c'è readyAt e startedAt, controlla che sia in corso
    ready_at = _to_ms(d.get("readyAt"))
    started_at = _to_ms(d.get("startedAt"))
    
    if ready_at and started_at:
        import time
        current_ms = int(time.time() * 1000)
        # Se readyAt è nel futuro, è attivo
        if ready_at > current_ms:
            return True
    
    return False

# --- scanner robusto --------------------------------------------------------
def _emit_from_node(node: Dict[str, Any], out: List[Dict[str, Any]]):
    """Emette item se la craftingBox è attiva"""
    # Verifica che sia attivamente in crafting
    if not _is_crafting_active(node):
        return
    
    ready = _extract_ready_ms(node)
    if isinstance(ready, int) and ready > 0:
        label = _label_from(node)
        # SOLO il nome dell'item, senza "Crafting Box —"
        out.append({"name": label, "ready_ms": ready})

def find_craftingbox_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Trova blocchi Crafting Box ATTIVI (status "crafting") e ritorna:
      [{"name": "<item>", "ready_ms": <ms>}]
    
    Percorsi coperti:
      - payload["craftingBox"]
      - payload["farm"]["craftingBox"]
      - payload["farm"]["buildings"]["craftingBox"]
    Poi fallback: scansione ricorsiva di qualsiasi chiave "craftingBox".
    """
    out: List[Dict[str, Any]] = []

    # 1) Percorsi diretti più comuni
    def _get(d: Dict[str, Any], *keys) -> Optional[Dict[str, Any]]:
        cur = d
        for k in keys:
            if not isinstance(cur, dict): return None
            cur = cur.get(k)
        return cur if isinstance(cur, dict) else None

    direct_candidates = [
        _get(payload, "craftingBox"),
        _get(payload, "farm", "craftingBox"),
        _get(payload, "farm", "buildings", "craftingBox"),
    ]
    
    for cand in direct_candidates:
        if isinstance(cand, dict):
            _emit_from_node(cand, out)

    # 2) Fallback: ricorsivo su chiavi chiamate "craftingBox"
    def walk(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, dict) and str(k).replace(" ", "").lower() == "craftingbox":
                    _emit_from_node(v, out)
                walk(v)
        elif isinstance(obj, list):
            for el in obj:
                walk(el)

    walk(payload)

    # dedup (name, ready_ms) + ordina
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for it in sorted(out, key=lambda x: x["ready_ms"]):
        key = (it["name"], it["ready_ms"])
        if key in seen: 
            continue
        seen.add(key)
        uniq.append(it)
    
    return uniq