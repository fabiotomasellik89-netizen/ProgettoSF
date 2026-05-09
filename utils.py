import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union
import logging, time

log = logging.getLogger("sflbot")

def to_ms(value: Union[int, float, None]) -> int:
    """Converti secondi UNIX in millisecondi"""
    if value is None:
        return 0
        
    # Se è già in millisecondi (valori molto grandi)
    if value > 1e12:  # Valori > 1 trilione sono già ms
        return int(value)
    
    # Se è in secondi UNIX (valori tra 1e9 e 1e10)
    if value > 1e9 and value < 1e10:  # Timestamp UNIX normale
        return int(value * 1000)
    
    # Default: tratta come secondi e converte in ms
    return int(value * 1000)

def is_valid_timestamp(timestamp: int, max_age_days: int = 30) -> bool:
    """Controlla se un timestamp è valido e recente"""
    if timestamp <= 0:
        return False
        
    current_ms = int(time.time() * 1000)
    
    # Esclude timestamp nel futuro lontano (dopo il 2100)
    if timestamp > 4102444800000:  # 1 gennaio 2100
        return False
        
    # Esclude timestamp troppo vecchi (più di max_age_days)
    max_age_ms = max_age_days * 24 * 60 * 60 * 1000
    if timestamp < current_ms - max_age_ms:
        return False
        
    return True


def from_ms(milliseconds: int) -> float:
    """Converti millisecondi in secondi"""
    return milliseconds / 1000

def format_time_remaining(seconds: float) -> str:
    """Formatta il tempo rimanente in formato leggibile"""
    if seconds <= 0:
        return "Pronto!"
    
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"

def parse_duration(duration_str: str) -> Optional[int]:
    """Parsa una stringa di durata in secondi"""
    try:
        # Formato: 1h 30m 15s
        hours = minutes = seconds = 0
        
        if 'h' in duration_str:
            hours = int(re.search(r'(\d+)h', duration_str).group(1))
        if 'm' in duration_str:
            minutes = int(re.search(r'(\d+)m', duration_str).group(1))
        if 's' in duration_str:
            seconds = int(re.search(r'(\d+)s', duration_str).group(1))
        
        return hours * 3600 + minutes * 60 + seconds
    except:
        return None

CROP_CATEGORIES = {
    "base": ["Potato", "Pumpkin", "Sunflower", "Zucchini", "Rhubarb"],
    "medium": ["Cabbage", "Cauliflower", "Beetroot", "Parsnip", "Eggplant"],
    "advanced": ["Kale", "Wheat", "Corn", "Carrot", "Soybean"],
    "flowers": ["Red Pansy", "Yellow Pansy", "Purple Pansy", "White Pansy", "Blue Pansy"],
    "fruits": ["Apple", "Orange", "Blueberry", "Banana", "Cactus Fruit"]
}

def get_crop_category(crop_name: str) -> str:
    """Restituisce la categoria di un crop"""
    for category, crops in CROP_CATEGORIES.items():
        if crop_name in crops:
            return category
    return "other"

# utils.py

def human_delta_short(ms: int) -> str:
    """
    Tempo rimanente SENZA secondi.
    - >= 1 giorno: "XdYh"
    - >= 1 ora:    "XhYYm"  (minuti zero-padded)
    - >= 1 min:    "Xm"
    - <  1 min:    "0m"
    """
    if ms is None:
        return "0m"
    try:
        ms = int(ms)
    except Exception:
        return "0m"

    # Se il chiamante passa in SECONDI per errore, togli il commento qui sotto:
    if ms < 10_000_000:  # ~2h47m in ms: sotto questo valore è probabile che siano secondi
         ms *= 1000

    if ms < 0:
        ms = 0

    total_minutes = ms // 60_000
    hours_total = total_minutes // 60
    minutes = total_minutes % 60
    days = hours_total // 24
    hours_in_day = hours_total % 24

    if days > 0:
        return f"{days}g{hours_in_day}h"
    if hours_total > 0:
        return f"{hours_total}h{minutes:02d}m"
    if total_minutes > 0:
        return f"{total_minutes}m"
    return "0m"


import base64
def extract_land_id_from_api_key(api_key: str) -> str:
    """Estrae la land_id da una SFL API key nel formato: sfl.<base64_land_id>.<sig>
    Se non valida lancia ValueError.
    """
    if not api_key or not isinstance(api_key, str):
        raise ValueError("API key non valida")
    parts = api_key.split(".")
    if len(parts) < 3:
        raise ValueError("Formato API key non riconosciuto")
    # secondo segmento è base64 (URL-safe o standard)
    b64 = parts[1]
    # Aggiusta padding
    padding = len(b64) % 4
    if padding:
        b64 = b64 + ("=" * (4 - padding))
    try:
        decoded = base64.b64decode(b64).decode("utf-8")
    except Exception as e:
        raise ValueError("Impossibile decodificare API key") from e
    # decoded dovrebbe essere l'id numerico
    if not decoded.isdigit():
        raise ValueError("Land id non numerico nella API key")
    return decoded
