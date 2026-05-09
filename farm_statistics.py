# farm_statistics.py - Sistema statistiche farm 24h (NO CIRCULAR IMPORTS)
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("sflbot")

_STATS_FILE = Path("data/farm_stats.json")
_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Timezone italiano
TZ = ZoneInfo("Europe/Rome")

def _load_stats() -> dict:
    """Carica le statistiche salvate"""
    if not _STATS_FILE.exists():
        return {}
    try:
        with open(_STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Errore caricamento statistiche: {e}")
        return {}

def _save_stats(data: dict) -> None:
    """Salva le statistiche"""
    try:
        with open(_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Errore salvataggio statistiche: {e}")

def _get_current_day() -> str:
    """Ottieni la data corrente in formato YYYY-MM-DD (timezone italiano)"""
    return datetime.now(TZ).strftime("%Y-%m-%d")

def _get_yesterday() -> str:
    """Ottieni la data di ieri in formato YYYY-MM-DD"""
    yesterday = datetime.now(TZ) - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")

def _init_day_stats() -> dict:
    """Inizializza struttura statistiche per un giorno"""
    return {
        "started_at": datetime.now(TZ).isoformat(),
        "last_update": datetime.now(TZ).isoformat(),
        
        # Inventario iniziale (snapshot all'1 di notte)
        "initial_inventory": {},
        
        # Contatori raccolte
        "crops_harvested": {},      # {crop_name: count}
        "fruits_harvested": {},     # {fruit_name: count}
        "trees_chopped": 0,
        "minerals_mined": {},       # {mineral_name: count}
        "flowers_harvested": {},    # {flower_name: count}
        
        # Animali
        "animals_fed": {},          # {animal_type: count}
        "eggs_collected": 0,
        "milk_collected": 0,
        "wool_collected": 0,
        "honey_collected": 0,
        
        # Crafting & Cooking
        "items_crafted": {},        # {item_name: count}
        "items_cooked": {},         # {recipe_name: count}
        
        # SFL & Tokens
        "sfl_earned": 0.0,
        "sfl_spent": 0.0,
        "tokens_earned": 0.0,
        "tokens_spent": 0.0,
        
        # Acquisti/Vendite
        "items_bought": {},         # {item_name: count}
        "items_sold": {},           # {item_name: count}
        
        # Quest & Deliveries
        "quests_completed": 0,
        "deliveries_completed": 0,
        
        # Mutazioni
        "mutations_collected": [],  # [mutation_name, ...]
        
        # Tempo totale attivo
        "active_time_minutes": 0,
        
        # Snapshot finale (alle 23:59)
        "final_inventory": {},
        "completed": False
    }

# ============================================================================
# GESTIONE SNAPSHOT GIORNALIERI
# ============================================================================

def take_snapshot(farm_id: str, payload: Dict[str, Any]) -> None:
    """
    Prende uno snapshot dell'inventario corrente
    Chiamato automaticamente all'1 di notte
    """
    data = _load_stats()
    farm_id = str(farm_id)
    
    if farm_id not in data:
        data[farm_id] = {}
    
    current_day = _get_current_day()
    
    # Crea nuovo giorno se non esiste
    if current_day not in data[farm_id]:
        data[farm_id][current_day] = _init_day_stats()
    
    # Estrai inventario dal payload
    inventory = payload.get("farm", {}).get("inventory", {})
    
    # Salva snapshot iniziale (se non già fatto)
    if not data[farm_id][current_day]["initial_inventory"]:
        data[farm_id][current_day]["initial_inventory"] = dict(inventory)
        log.info(f"📸 Snapshot iniziale salvato per farm {farm_id} - {current_day}")
    
    # Aggiorna timestamp
    data[farm_id][current_day]["last_update"] = datetime.now(TZ).isoformat()
    
    _save_stats(data)

def finalize_day(farm_id: str, payload: Dict[str, Any]) -> None:
    """
    Finalizza le statistiche del giorno (chiamato alle 23:59)
    """
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    if farm_id not in data or current_day not in data[farm_id]:
        return
    
    # Salva inventario finale
    inventory = payload.get("farm", {}).get("inventory", {})
    data[farm_id][current_day]["final_inventory"] = dict(inventory)
    data[farm_id][current_day]["completed"] = True
    data[farm_id][current_day]["last_update"] = datetime.now(TZ).isoformat()
    
    _save_stats(data)
    log.info(f"✅ Statistiche giornaliere finalizzate per farm {farm_id} - {current_day}")

# ============================================================================
# TRACKING ATTIVITÀ
# ============================================================================

def track_harvest(farm_id: str, item_type: str, item_name: str, quantity: int = 1) -> None:
    """
    Traccia raccolte di crops/fruits/flowers/minerals
    
    Args:
        farm_id: ID della farm
        item_type: "crops", "fruits", "flowers", "minerals"
        item_name: Nome dell'item raccolto
        quantity: Quantità raccolta
    """
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    # Assicurati che esistano le strutture
    if farm_id not in data:
        data[farm_id] = {}
    if current_day not in data[farm_id]:
        data[farm_id][current_day] = _init_day_stats()
    
    day_stats = data[farm_id][current_day]
    
    # Mappa tipo -> campo
    field_map = {
        "crops": "crops_harvested",
        "fruits": "fruits_harvested",
        "flowers": "flowers_harvested",
        "minerals": "minerals_mined"
    }
    
    field = field_map.get(item_type)
    if field:
        if item_name not in day_stats[field]:
            day_stats[field][item_name] = 0
        day_stats[field][item_name] += quantity
        day_stats["last_update"] = datetime.now(TZ).isoformat()
        _save_stats(data)
        log.debug(f"📊 Farm {farm_id}: +{quantity} {item_name} ({item_type})")

def track_animal_collection(farm_id: str, animal_type: str, product: str, quantity: int = 1) -> None:
    """
    Traccia raccolte da animali
    
    Args:
        animal_type: "Chicken", "Cow", "Sheep", "Bee"
        product: "Egg", "Milk", "Wool", "Honey"
    """
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    if farm_id not in data:
        data[farm_id] = {}
    if current_day not in data[farm_id]:
        data[farm_id][current_day] = _init_day_stats()
    
    day_stats = data[farm_id][current_day]
    
    # Aggiorna contatori
    if product == "Egg":
        day_stats["eggs_collected"] += quantity
    elif product == "Milk":
        day_stats["milk_collected"] += quantity
    elif product == "Wool":
        day_stats["wool_collected"] += quantity
    elif product == "Honey":
        day_stats["honey_collected"] += quantity
    
    # Traccia anche feeding
    if animal_type not in day_stats["animals_fed"]:
        day_stats["animals_fed"][animal_type] = 0
    day_stats["animals_fed"][animal_type] += 1
    
    day_stats["last_update"] = datetime.now(TZ).isoformat()
    _save_stats(data)

def track_crafting(farm_id: str, item_name: str, quantity: int = 1) -> None:
    """Traccia item craftati"""
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    if farm_id not in data:
        data[farm_id] = {}
    if current_day not in data[farm_id]:
        data[farm_id][current_day] = _init_day_stats()
    
    day_stats = data[farm_id][current_day]
    
    if item_name not in day_stats["items_crafted"]:
        day_stats["items_crafted"][item_name] = 0
    day_stats["items_crafted"][item_name] += quantity
    day_stats["last_update"] = datetime.now(TZ).isoformat()
    _save_stats(data)

def track_cooking(farm_id: str, recipe_name: str, quantity: int = 1) -> None:
    """Traccia ricette cucinate"""
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    if farm_id not in data:
        data[farm_id] = {}
    if current_day not in data[farm_id]:
        data[farm_id][current_day] = _init_day_stats()
    
    day_stats = data[farm_id][current_day]
    
    if recipe_name not in day_stats["items_cooked"]:
        day_stats["items_cooked"][recipe_name] = 0
    day_stats["items_cooked"][recipe_name] += quantity
    day_stats["last_update"] = datetime.now(TZ).isoformat()
    _save_stats(data)

def track_sfl_transaction(farm_id: str, amount: float, is_earned: bool = True) -> None:
    """Traccia transazioni SFL"""
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    if farm_id not in data:
        data[farm_id] = {}
    if current_day not in data[farm_id]:
        data[farm_id][current_day] = _init_day_stats()
    
    day_stats = data[farm_id][current_day]
    
    if is_earned:
        day_stats["sfl_earned"] += amount
    else:
        day_stats["sfl_spent"] += amount
    
    day_stats["last_update"] = datetime.now(TZ).isoformat()
    _save_stats(data)

# ============================================================================
# RECUPERO STATISTICHE
# ============================================================================

def get_today_stats(farm_id: str) -> Optional[Dict[str, Any]]:
    """Ottieni statistiche del giorno corrente"""
    data = _load_stats()
    farm_id = str(farm_id)
    current_day = _get_current_day()
    
    return data.get(farm_id, {}).get(current_day)

def get_yesterday_stats(farm_id: str) -> Optional[Dict[str, Any]]:
    """Ottieni statistiche di ieri"""
    data = _load_stats()
    farm_id = str(farm_id)
    yesterday = _get_yesterday()
    
    return data.get(farm_id, {}).get(yesterday)

def get_stats_range(farm_id: str, days: int = 7) -> Dict[str, Dict[str, Any]]:
    """Ottieni statistiche degli ultimi N giorni"""
    data = _load_stats()
    farm_id = str(farm_id)
    
    result = {}
    for i in range(days):
        date = (datetime.now(TZ) - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in data.get(farm_id, {}):
            result[date] = data[farm_id][date]
    
    return result

# ============================================================================
# CALCOLO DELTA (DIFF TRA INVENTARI)
# ============================================================================

def calculate_inventory_delta(farm_id: str, date: Optional[str] = None) -> Dict[str, int]:
    """
    Calcola la differenza tra inventario iniziale e finale
    
    Returns:
        {item_name: delta_quantity} (positivo = guadagnato, negativo = consumato)
    """
    data = _load_stats()
    farm_id = str(farm_id)
    
    if date is None:
        date = _get_current_day()
    
    day_stats = data.get(farm_id, {}).get(date)
    if not day_stats:
        return {}
    
    initial = day_stats.get("initial_inventory", {})
    final = day_stats.get("final_inventory", {})
    
    # Se non c'è finale, usa snapshot attuale
    if not final:
        return {}
    
    # Calcola delta
    delta = {}
    all_items = set(initial.keys()) | set(final.keys())
    
    for item in all_items:
        initial_qty = float(initial.get(item, 0))
        final_qty = float(final.get(item, 0))
        diff = final_qty - initial_qty
        
        if diff != 0:
            delta[item] = int(diff)
    
    return delta

# ============================================================================
# CLEANUP AUTOMATICO
# ============================================================================

def cleanup_old_stats(days: int = 30) -> None:
    """Rimuovi statistiche più vecchie di N giorni"""
    data = _load_stats()
    cutoff = datetime.now(TZ) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    
    changed = False
    for farm_id in list(data.keys()):
        for date in list(data[farm_id].keys()):
            if date < cutoff_str:
                del data[farm_id][date]
                changed = True
        
        # Rimuovi farm vuote
        if not data[farm_id]:
            del data[farm_id]
    
    if changed:
        _save_stats(data)
        log.info(f"Cleanup statistiche: rimossi dati più vecchi di {days} giorni")