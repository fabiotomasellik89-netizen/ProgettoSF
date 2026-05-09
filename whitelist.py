import os
import json
from pathlib import Path
from typing import Optional, Dict

_WL_FILE = Path("whitelist.json")
_OWNER_ID: Optional[int] = None

def _load() -> Dict:
    """Carica whitelist da file"""
    if not _WL_FILE.exists():
        return {"allowed": {}, "banned": {}, "seen": {}}
    try:
        return json.loads(_WL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"allowed": {}, "banned": {}, "seen": {}}

def _save(data: Dict) -> None:
    """Salva whitelist su file"""
    _WL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def init_whitelist(owner_id: Optional[int] = None) -> None:
    """Inizializza whitelist con owner"""
    global _OWNER_ID
    _OWNER_ID = owner_id
    
    if owner_id:
        data = _load()
        if "allowed" not in data:
            data["allowed"] = {}
        # Aggiungi owner automaticamente
        data["allowed"][str(owner_id)] = {
            "name": "Owner",
            "username": "",
            "added_at": ""
        }
        _save(data)

def is_owner(user_id: int) -> bool:
    """Verifica se è l'owner"""
    return _OWNER_ID is not None and user_id == _OWNER_ID

def is_allowed(user_id: int) -> bool:
    """Verifica se l'utente è in whitelist"""
    if is_owner(user_id):
        return True
    
    data = _load()
    # Se whitelist vuota, permetti a tutti (mode aperto)
    if not data.get("allowed"):
        return True
    
    return str(user_id) in data.get("allowed", {})

def is_banned(user_id: int) -> bool:
    """Verifica se l'utente è bannato"""
    data = _load()
    return str(user_id) in data.get("banned", {})

def add_user(user_id: int, name: str = "", username: str = "") -> None:
    """Aggiungi utente alla whitelist"""
    if is_banned(user_id):
        return  # Non aggiungere utenti bannati
    
    data = _load()
    if "allowed" not in data:
        data["allowed"] = {}
    
    data["allowed"][str(user_id)] = {
        "name": name,
        "username": username,
        "added_at": ""
    }
    _save(data)

def remove_user(user_id: int) -> bool:
    """Rimuovi utente dalla whitelist"""
    if is_owner(user_id):
        return False  # Non rimuovere owner
    
    data = _load()
    if str(user_id) in data.get("allowed", {}):
        del data["allowed"][str(user_id)]
        _save(data)
        return True
    return False

def ban_user(user_id: int, reason: str = "") -> None:
    """Banna un utente"""
    if is_owner(user_id):
        return  # Non bannare owner
    
    data = _load()
    if "banned" not in data:
        data["banned"] = {}
    
    # Rimuovi da whitelist se presente
    if str(user_id) in data.get("allowed", {}):
        del data["allowed"][str(user_id)]
    
    data["banned"][str(user_id)] = {
        "reason": reason,
        "banned_at": ""
    }
    _save(data)

def unban_user(user_id: int) -> bool:
    """Sbanna un utente"""
    data = _load()
    if str(user_id) in data.get("banned", {}):
        del data["banned"][str(user_id)]
        _save(data)
        return True
    return False

def note_seen(user_id: int, name: str = "", username: str = "") -> None:
    """Registra che abbiamo visto questo utente"""
    data = _load()
    if "seen" not in data:
        data["seen"] = {}
    
    data["seen"][str(user_id)] = {
        "name": name,
        "username": username,
        "last_seen": ""
    }
    _save(data)

def list_allowed_detailed() -> Dict:
    """Lista dettagliata degli utenti in whitelist"""
    data = _load()
    return data.get("allowed", {})

def list_seen_detailed() -> Dict:
    """Lista dettagliata degli utenti visti"""
    data = _load()
    return data.get("seen", {})