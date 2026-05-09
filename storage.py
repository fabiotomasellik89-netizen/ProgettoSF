import json
import os
from pathlib import Path
from typing import Optional, List, Tuple
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Carica variabili d'ambiente dal file .env
load_dotenv()

# ============================================================================
# CONFIGURAZIONE CIFRATURA
# ============================================================================

# Genera una chiave di cifratura (da salvare in variabile d'ambiente ENCRYPTION_KEY)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# TEMPORANEO: Hardcode se .env non funziona
if not ENCRYPTION_KEY:
    # ⚠️ ATTENZIONE: Questa chiave è hardcoded!
    # In produzione, usa sempre il file .env
    ENCRYPTION_KEY = "gliVu6H3A_zXpsrGeRHSqYjFFhp02STpcXrNStBmMmc="
    print("⚠️ Usando ENCRYPTION_KEY hardcoded (temporaneo)")
    print("⚠️ Configura correttamente il file .env!")
else:
    print(f"✅ ENCRYPTION_KEY caricata dal .env: {ENCRYPTION_KEY[:20]}...")

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY non configurata!")

cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

# ============================================================================
# FILE DI STORAGE
# ============================================================================

_DB = Path("storage.json")
_API_KEYS_FILE = Path("data/api_keys.json")

# Assicurati che la directory data/ esista
_API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# FUNZIONI STORAGE PRINCIPALE
# ============================================================================

def _load() -> dict:
    """Carica il database principale"""
    if not _DB.exists():
        return {}
    try:
        return json.loads(_DB.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save(data: dict) -> None:
    """Salva il database principale"""
    _DB.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ============================================================================
# FUNZIONI API KEYS (CIFRATE)
# ============================================================================

def _load_api_keys() -> dict:
    """Carica le API keys cifrate dal file"""
    if not _API_KEYS_FILE.exists():
        return {}
    try:
        with open(_API_KEYS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_api_keys(keys_data: dict) -> None:
    """Salva le API keys cifrate nel file"""
    _API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_API_KEYS_FILE, 'w') as f:
        json.dump(keys_data, f, indent=2)

def set_api_key(chat_id: int, api_key: str) -> None:
    """
    Salva la SFL API key dell'utente in modo cifrato e deriva automaticamente il land_id
    
    Args:
        chat_id: ID della chat Telegram
        api_key: SFL API key dell'utente (formato: sfl.<base64_land_id>.<signature>)
    
    Raises:
        ValueError: Se la API key non è valida
    """
    from utils import extract_land_id_from_api_key
    
    keys_data = _load_api_keys()
    
    # Valida e deriva land_id dalla API key
    try:
        land_id = extract_land_id_from_api_key(api_key)
    except ValueError as e:
        raise ValueError(f"API key non valida: {e}")
    
    # Cifra la API key
    encrypted_key = cipher_suite.encrypt(api_key.encode()).decode()
    
    keys_data[str(chat_id)] = {
        'encrypted_key': encrypted_key,
        'land_id': land_id
    }
    _save_api_keys(keys_data)
    
    # Salva anche nel database principale per compatibilità
    data = _load()
    rec = data.get(str(chat_id)) or {}
    rec["land"] = land_id
    rec["subscribed"] = True  # Attiva automaticamente le notifiche
    data[str(chat_id)] = rec
    _save(data)

def get_api_key(chat_id: int) -> Optional[str]:
    """
    Recupera la SFL API key decifrata dell'utente
    
    Args:
        chat_id: ID della chat Telegram
        
    Returns:
        SFL API key decifrata o None se non trovata
    """
    keys_data = _load_api_keys()
    user_data = keys_data.get(str(chat_id))
    
    if not user_data or 'encrypted_key' not in user_data:
        return None
    
    encrypted_key = user_data['encrypted_key']
    
    try:
        # Decifra la API key
        decrypted_key = cipher_suite.decrypt(encrypted_key.encode()).decode()
        return decrypted_key
    except Exception as e:
        print(f"Errore nella decifratura della chiave: {e}")
        return None

def get_land_id_from_api_key(chat_id: int) -> Optional[str]:
    """
    Recupera il land_id salvato (senza decifrare la API key)
    
    Args:
        chat_id: ID della chat Telegram
        
    Returns:
        Land ID o None se non trovato
    """
    keys_data = _load_api_keys()
    user_data = keys_data.get(str(chat_id))
    
    if not user_data:
        return None
    
    return user_data.get('land_id')

def delete_api_key(chat_id: int) -> None:
    """
    Elimina la API key dell'utente
    
    Args:
        chat_id: ID della chat Telegram
    """
    keys_data = _load_api_keys()
    if str(chat_id) in keys_data:
        del keys_data[str(chat_id)]
        _save_api_keys(keys_data)

def validate_api_key(api_key: str) -> bool:
    """
    Valida che una stringa sia una SFL API key valida
    
    Args:
        api_key: Stringa da validare
        
    Returns:
        True se è una API key valida, False altrimenti
    """
    from utils import extract_land_id_from_api_key
    
    try:
        land_id = extract_land_id_from_api_key(api_key)
        # Verifica che il land_id sia un numero valido
        return land_id.isdigit() and int(land_id) > 0
    except Exception:
        return False

# ============================================================================
# FUNZIONI LAND (COMPATIBILITÀ)
# ============================================================================

def set_land(chat_id: int, land: str) -> None:
    """Imposta il land ID per un utente"""
    data = _load()
    rec = data.get(str(chat_id)) or {}
    rec["land"] = str(land)
    # Attiva automaticamente le notifiche quando la land viene impostata
    rec["subscribed"] = True
    data[str(chat_id)] = rec
    _save(data)

def get_land(chat_id: int) -> Optional[str]:
    """
    Recupera il land ID per un utente
    Prova prima dal database API keys cifrato, poi dal database principale
    """
    # Prova dal database API keys
    land_from_api = get_land_id_from_api_key(chat_id)
    if land_from_api:
        return land_from_api
    
    # Fallback al database principale
    data = _load()
    rec = data.get(str(chat_id)) or {}
    return rec.get("land")

# ============================================================================
# FUNZIONI NOTIFICHE
# ============================================================================

def set_notifications(chat_id: int, enabled: bool) -> None:
    """Imposta lo stato delle notifiche per un utente"""
    data = _load()
    rec = data.get(str(chat_id)) or {}
    rec["subscribed"] = bool(enabled)
    data[str(chat_id)] = rec
    _save(data)

def get_notifications(chat_id: int) -> bool:
    """Recupera lo stato delle notifiche per un utente"""
    data = _load()
    rec = data.get(str(chat_id)) or {}
    return bool(rec.get("subscribed", False))

def get_all_subscribed() -> List[Tuple[int, str]]:
    """
    Restituisce lista di tuple (chat_id, land_id) per utenti con notifiche attive
    """
    data = _load()
    out = []
    for k, rec in data.items():
        try:
            cid = int(k)
        except Exception:
            continue
        if rec.get("subscribed"):
            # Prova a ottenere land dalla API key, poi dal record
            land = get_land(cid) or rec.get("land")
            if land:
                out.append((cid, land))
    return out

# ============================================================================
# FUNZIONI UTILITÀ
# ============================================================================

def has_api_key(chat_id: int) -> bool:
    """Verifica se l'utente ha una API key salvata"""
    return get_api_key(chat_id) is not None

def get_user_info(chat_id: int) -> dict:
    """
    Recupera tutte le informazioni di un utente
    
    Returns:
        dict con chiavi: land_id, has_api_key, notifications_enabled
    """
    return {
        'land_id': get_land(chat_id),
        'has_api_key': has_api_key(chat_id),
        'notifications_enabled': get_notifications(chat_id)
    }