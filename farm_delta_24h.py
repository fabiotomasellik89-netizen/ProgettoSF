# farm_delta_24h.py - Sistema snapshot giornaliero semplificato
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("sflbot")

SNAPSHOTS_DIR = Path("data/snapshots")
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

TZ = ZoneInfo("Europe/Rome")

# ==============================================================================
# GESTIONE SNAPSHOT GIORNALIERO
# ==============================================================================

def get_daily_snapshot_path(farm_id: str) -> Path:
    """Ritorna il path del file snapshot giornaliero"""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    return SNAPSHOTS_DIR / f"{farm_id}_daily_{today}.json"

def save_daily_snapshot(farm_id: str, payload: Dict) -> None:
    """
    Salva lo snapshot giornaliero (chiamato all'1 di notte)
    Questo è l'UNICO snapshot che viene salvato automaticamente
    """
    path = get_daily_snapshot_path(farm_id)
    
    try:
        snapshot = {
            "timestamp": datetime.now(TZ).isoformat(),
            "farm_id": farm_id,
            "payload": payload
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        
        log.info(f"📸 Snapshot giornaliero salvato per farm {farm_id}")
    except Exception as e:
        log.error(f"Errore salvataggio snapshot {farm_id}: {e}")

def load_daily_snapshot(farm_id: str) -> Optional[Dict]:
    """
    Carica lo snapshot giornaliero (salvato all'1 di notte)
    Ritorna None se non esiste
    """
    path = get_daily_snapshot_path(farm_id)
    
    if not path.exists():
        log.warning(f"Snapshot giornaliero non trovato per farm {farm_id}")
        return None
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
        
        snapshot_time = datetime.fromisoformat(snapshot["timestamp"])
        hours_ago = (datetime.now(TZ) - snapshot_time).total_seconds() / 3600
        
        log.info(f"📖 Caricato snapshot di {hours_ago:.1f}h fa")
        return snapshot
    except Exception as e:
        log.error(f"Errore caricamento snapshot: {e}")
        return None

def cleanup_old_snapshots(farm_id: str, keep_days: int = 7) -> None:
    """Rimuove snapshot più vecchi di N giorni"""
    try:
        for file in SNAPSHOTS_DIR.glob(f"{farm_id}_daily_*.json"):
            # Estrai data dal filename
            date_str = file.stem.split("_daily_")[1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            file_date = file_date.replace(tzinfo=TZ)
            
            age_days = (datetime.now(TZ) - file_date).days
            
            if age_days > keep_days:
                file.unlink()
                log.info(f"🗑️ Rimosso snapshot vecchio: {file.name}")
    except Exception as e:
        log.error(f"Errore cleanup snapshot: {e}")

# ==============================================================================
# CALCOLO DELTA (confronto on-demand quando utente clicca statistiche)
# ==============================================================================

async def calculate_delta_today(farm_id: str, chat_id: int) -> Dict:
    """
    Calcola le differenze tra ora e lo snapshot delle 1:00 di oggi
    
    Questo viene chiamato SOLO quando l'utente clicca "Statistiche"
    NON salva il payload corrente, lo usa solo per il confronto
    """
    from api import fetch_farm_with_user_key
    
    # 1. Scarica payload attuale
    try:
        current_payload, _, _ = await fetch_farm_with_user_key(farm_id, chat_id, force=True)
    except Exception as e:
        log.error(f"Errore fetch payload attuale: {e}")
        return {
            "has_previous": False,
            "summary": "❌ Errore nel recuperare i dati della farm"
        }
    
    # 2. Carica snapshot giornaliero
    daily_snapshot = load_daily_snapshot(farm_id)
    
    if not daily_snapshot:
        return {
            "has_previous": False,
            "summary": (
                "📊 *Statistiche Giornaliere*\n\n"
                "⏰ Nessuno snapshot disponibile oggi.\n\n"
                "Lo snapshot viene salvato automaticamente all'*1:00 di notte*.\n"
                "Torna domani per vedere le tue statistiche!"
            )
        }
    
    # 3. Calcola tempo trascorso
    try:
        prev_time = datetime.fromisoformat(daily_snapshot["timestamp"])
        time_diff = datetime.now(TZ) - prev_time
        hours_ago = time_diff.total_seconds() / 3600
    except Exception:
        hours_ago = 0
        prev_time = datetime.now(TZ)
    
    # 4. Estrai inventari
    prev_payload = daily_snapshot["payload"]
    prev_inventory = prev_payload.get("farm", {}).get("inventory", {})
    curr_inventory = current_payload.get("farm", {}).get("inventory", {})
    
    # 5. Delta SFL
    try:
        prev_balance = float(prev_payload.get("balance", 0))
        curr_balance = float(current_payload.get("balance", 0))
        sfl_delta = curr_balance - prev_balance
    except Exception:
        sfl_delta = 0
    
    # 6. Calcola delta inventario
    all_items = set(prev_inventory.keys()) | set(curr_inventory.keys())
    
    delta = {}
    for item in all_items:
        try:
            prev_count = float(prev_inventory.get(item, 0))
        except (ValueError, TypeError):
            prev_count = 0
        
        try:
            curr_count = float(curr_inventory.get(item, 0))
        except (ValueError, TypeError):
            curr_count = 0
        
        diff = curr_count - prev_count
        if diff != 0:
            delta[item] = diff
    
    # 7. Categorizza item
    categories = categorize_items(delta, sfl_delta)
    
    # 8. Costruisci messaggio
    now = datetime.now(TZ)
    lines = [
        "📊 *Statistiche Giornaliere*",
        f"🕐 {prev_time.strftime('%d/%m %H:%M')} → {now.strftime('%d/%m %H:%M')}\n"
    ]
    
    # Main (SFL)
    if categories["main"]:
        lines.append("💰 *Main:*")
        for item, value in categories["main"]:
            sign = "+" if value > 0 else ""
            lines.append(f"  {sign}{value:.2f} {item}")
        lines.append("")
    
    # Resources
    if categories["resources"]:
        lines.append("🪵 *Resources:*")
        items_str = format_category_items(categories["resources"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Tools
    if categories["tools"]:
        lines.append("🔨 *Tools:*")
        items_str = format_category_items(categories["tools"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Seeds
    if categories["seeds"]:
        lines.append("🌰 *Seeds:*")
        items_str = format_category_items(categories["seeds"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Crops
    if categories["crops"]:
        lines.append("🌱 *Crops:*")
        items_str = format_category_items(categories["crops"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Fruits
    if categories["fruits"]:
        lines.append("🎃 *Fruits:*")
        items_str = format_category_items(categories["fruits"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Food
    if categories["food"]:
        lines.append("🍳 *Food:*")
        items_str = format_category_items(categories["food"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Fish
    if categories["fish"]:
        lines.append("🟣 *Fish:*")
        items_str = format_category_items(categories["fish"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Animals
    if categories["animals"]:
        lines.append("🐾 *Animals:*")
        items_str = format_category_items(categories["animals"])
        lines.append(f"  {items_str}")
        lines.append("")
    
    # Other (limita a top 20)
    if categories["other"]:
        lines.append("📦 *Other:*")
        top_other = categories["other"][:20]
        items_str = format_category_items(top_other)
        lines.append(f"  {items_str}")
        if len(categories["other"]) > 20:
            lines.append(f"  _... e altri {len(categories['other']) - 20} item_")
        lines.append("")
    
    if not any(categories.values()):
        lines.append("_Nessuna variazione da oggi_\n")
    
    lines.append(f"_Aggiornato: {now.strftime('%d/%m - %H:%M')}_")
    
    return {
        "has_previous": True,
        "hours_ago": hours_ago,
        "summary": "\n".join(lines)
    }

# ==============================================================================
# CATEGORIZZAZIONE E FORMATTAZIONE
# ==============================================================================

def categorize_items(delta: Dict[str, float], sfl_delta: float) -> Dict[str, List]:
    """Categorizza gli item per tipo"""
    
    # Definizioni categorie
    RESOURCES = {"Wood", "Stone", "Iron", "Gold", "Crimstone", "Sunstone"}
    TOOLS = {"Axe", "Pickaxe", "Rod", "Sword"}
    SEEDS = {item for item in delta.keys() if "Seed" in item}
    
    CROPS = {
        "Sunflower", "Potato", "Pumpkin", "Carrot", "Cabbage", "Beetroot",
        "Cauliflower", "Parsnip", "Eggplant", "Corn", "Radish", "Wheat", "Kale"
    }
    
    FRUITS = {
        "Apple", "Blueberry", "Orange", "Banana", "Tomato", "Lemon", "Grape"
    }
    
    FOOD = {
        "Boiled Egg", "Mashed Potato", "Pancakes", "Roasted Cauliflower",
        "Sauerkraut", "Radish Pie", "Kale Omelette", "Cabbers n Mash",
        "Popcorn", "Fermented Fish", "Reindeer Carrot", "Cheese",
        "Bumpkin Salad", "Goblin Brunch", "Cauliflower Burger"
    }
    
    FISH = {
        "Anchovy", "Butterflyfish", "Blowfish", "Clownfish", "Sea Bass",
        "Sea Horse", "Horse Mackerel", "Squid", "Red Snapper", "Moray Eel",
        "Olive Flounder", "Napoleonfish", "Surgeonfish", "Zebra Turkeyfish",
        "Ray", "Hammerhead Shark", "Tuna", "Mahi Mahi", "Blue Marlin",
        "Oarfish", "Football Fish", "Sunfish", "Coelacanth", "Whale",
        "Barred Knifejaw", "Barracuda", "Parrotfish"
    }
    
    ANIMALS = {"Egg", "Chicken", "Milk", "Cow", "Sheep", "Wool", "Feather"}
    
    categories = {
        "main": [],
        "resources": [],
        "tools": [],
        "seeds": [],
        "crops": [],
        "fruits": [],
        "food": [],
        "fish": [],
        "animals": [],
        "other": []
    }
    
    # SFL
    if sfl_delta != 0:
        categories["main"].append(("SFL", sfl_delta))
    
    # Categorizza item
    for item, value in delta.items():
        if item in RESOURCES:
            categories["resources"].append((item, value))
        elif item in TOOLS:
            categories["tools"].append((item, value))
        elif item in SEEDS:
            categories["seeds"].append((item, value))
        elif item in CROPS:
            categories["crops"].append((item, value))
        elif item in FRUITS:
            categories["fruits"].append((item, value))
        elif item in FOOD:
            categories["food"].append((item, value))
        elif item in FISH:
            categories["fish"].append((item, value))
        elif item in ANIMALS:
            categories["animals"].append((item, value))
        elif "Coin" in item or "Block Buck" in item:
            categories["main"].append((item, value))
        else:
            categories["other"].append((item, value))
    
    # Ordina per valore assoluto (dal più grande al più piccolo)
    for cat in categories:
        categories[cat].sort(key=lambda x: abs(x[1]), reverse=True)
    
    return categories

def format_category_items(items: List[Tuple[str, float]]) -> str:
    """Formatta lista di item con +/- in una riga compatta"""
    parts = []
    for item, value in items:
        sign = "+" if value > 0 else ""
        if value == int(value):
            parts.append(f"{sign}{int(value)} {item}")
        else:
            parts.append(f"{sign}{value:.1f} {item}")
    
    return " / ".join(parts)