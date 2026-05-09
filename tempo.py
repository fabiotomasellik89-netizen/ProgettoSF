from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone
import logging

from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES, GROWTH_MS
from utils import human_delta_short, to_ms, is_valid_timestamp

# Importa i moduli necessari
from crops import walk_crop_objects, compute_ready_ms, crop_display_name, group_rows
from fruit import find_fruit_items
from minerals import find_mineral_items
from compost import find_compost_items
from animals import find_animal_items
from trees import find_tree_items
from flowers import find_flower_items
from cooking import find_cooking_items
from crafting_box import find_craftingbox_items
from alveari import build_beehives_section

log = logging.getLogger("sflbot")

# ---------- Funzioni helper generiche ----------
def _future_generic(items: List[dict], now_ms: int) -> List[Tuple[int, str]]:
    """Converte item con ready_ms in lista di tuple (timestamp, nome)"""
    rows: List[Tuple[int, str]] = []
    for it in items:
        t = it.get("ready_ms")
        n = (it.get("name") or "Item").strip()
        if isinstance(t, int) and t > now_ms:
            rows.append((t, n))
    return rows

def _ready_generic(items: List[dict], now_ms: int) -> List[str]:
    """Restituisce nomi degli item gipronti"""
    out: List[str] = []
    for it in items:
        t = it.get("ready_ms")
        n = (it.get("name") or "Item").strip()
        if isinstance(t, int) and t <= now_ms:
            out.append(n)
    return out

# ---------- categoria: COLTURE ----------
def _future_crops(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di crops non pronti"""
    rows: List[Tuple[int, str]] = []
    
    for crop in walk_crop_objects(payload):
        planted_at = crop.get("plantedAt")
        name = crop.get("name")
        
        if not planted_at or not name:
            continue
            
        base_ms = GROWTH_MS.get(name)
        if not base_ms:
            continue
            
        ready_ms = planted_at + base_ms
        
        if ready_ms and ready_ms > now_ms:
            rows.append((ready_ms, name))
    
    return rows

def _ready_crops(payload: Dict[str, Any], now_ms: int) -> List[str]:
    """Restituisce nomi dei crops pronti"""
    out: List[str] = []
    for crop in walk_crop_objects(payload):
        planted_at = crop.get("plantedAt")
        boosted_time = crop.get("boostedTime")
        
        ready_ms, _ = compute_ready_ms(crop, planted_at, boosted_time, payload)
        if ready_ms and ready_ms <= now_ms:
            out.append(crop_display_name(crop))
    return out

# ---------- categoria: FRUTTA ----------
def _future_fruit(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di frutta non pronta"""
    return _future_generic(find_fruit_items(payload), now_ms)

def _ready_fruit(payload: Dict[str, Any], now_ms: int) -> List[str]:
    """Restituisce nomi della frutta pronta"""
    return _ready_generic(find_fruit_items(payload), now_ms)

# ---------- categoria: CUCINA ----------
def _future_cooking(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di cucina non pronta"""
    return _future_generic(find_cooking_items(payload), now_ms)

def _ready_cooking(payload: Dict[str, Any], now_ms: int) -> List[str]:
    return _ready_generic(find_cooking_items(payload), now_ms)


# ---------- categoria: CRAFTING BOX ----------
def _future_craftingbox(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di crafting box non pronti"""
    return _future_generic(find_craftingbox_items(payload), now_ms)

def _ready_craftingbox(payload: Dict[str, Any], now_ms: int) -> List[str]:
    return _ready_generic(find_craftingbox_items(payload), now_ms)

# ---------- altre categorie ----------
def _future_compost(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di compost non pronto"""
    return _future_generic(find_compost_items(payload), now_ms)

def _ready_compost(payload: Dict[str, Any], now_ms: int) -> List[str]:
    return _ready_generic(find_compost_items(payload), now_ms)

def _future_animals(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di animali non pronti"""
    return _future_generic(find_animal_items(payload), now_ms)

def _ready_animals(payload: Dict[str, Any], now_ms: int) -> List[str]:
    """Restituisce nomi degli animali pronti"""
    try:
        from animals import find_ready_animal_items
        return find_ready_animal_items(payload, now_ms)
    except Exception as e:
        log.error(f"Errore in _ready_animals: {e}")
        return []

def _future_minerals(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di minerali non pronti"""
    return _future_generic(find_mineral_items(payload), now_ms)

def _ready_minerals(payload: Dict[str, Any], now_ms: int) -> List[str]:
    return _ready_generic(find_mineral_items(payload), now_ms)

def _future_trees(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di alberi non pronti"""
    return _future_generic(find_tree_items(payload), now_ms)

def _ready_trees(payload: Dict[str, Any], now_ms: int) -> List[str]:
    return _ready_generic(find_tree_items(payload), now_ms)

def _future_flowers(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    """Restituisce lista di fiori non pronti"""
    return _future_generic(find_flower_items(payload), now_ms)

def _ready_flowers(payload: Dict[str, Any], now_ms: int) -> List[str]:
    return _ready_generic(find_flower_items(payload), now_ms)

# IN tempo.py - modifica la funzione _future_beehives:

def _future_beehives(payload: Dict[str, Any], now_ms: int) -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = []
    
    BEEHIVE_MAX_HONEY = 68664000
    HONEY_PER_HOUR_BASE = 2600909
    NOTIFICATION_THRESHOLD = BEEHIVE_MAX_HONEY * 0.98
    
    beehives = payload.get("farm", {}).get("beehives", {})
    
    for hive_id, hive in beehives.items():
        x = hive.get("x")
        y = hive.get("y")
        coord = f"({x},{y})" if x is not None and y is not None else hive_id[-4:]
        
        honey_data = hive.get("honey", {})
        produced = honey_data.get("produced", 0) or 0
        
        # Solo alveari sotto il 98%
        if produced >= NOTIFICATION_THRESHOLD:
            continue
            
        # Fiori attivi
        flowers = hive.get("flowers", [])
        active_flowers = [f for f in flowers if f.get("attachedUntil", 0) > now_ms]
        
        if not active_flowers:
            continue
            
        # Calcola produzione
        total_rate = 1.0
        for flower in active_flowers:
            total_rate *= flower.get("rate", 1.0)
        
        honey_per_hour = HONEY_PER_HOUR_BASE * total_rate
        
        # Calcola miele attuale (considerando tempo passato dall'update)
        updated_at = honey_data.get("updatedAt", now_ms)
        time_elapsed_ms = now_ms - updated_at
        time_elapsed_hours = time_elapsed_ms / (1000 * 60 * 60)
        current_honey = produced + (honey_per_hour * time_elapsed_hours)
        
        # Se già sopra soglia, salta (ma non dovrebbe succedere)
        if current_honey >= NOTIFICATION_THRESHOLD:
            continue
            
        honey_needed = NOTIFICATION_THRESHOLD - current_honey
        hours_needed = honey_needed / honey_per_hour
        
        # Calcola quando raggiungerà il 98%
        ready_time = now_ms + int(hours_needed * 60 * 60 * 1000)
        
        # Verifica se il fiore scade prima
        earliest_expiry = min(f.get("attachedUntil") for f in active_flowers)
        
        # Mostra in "In corso" solo se si riempie prima che scada il fiore
        if ready_time <= earliest_expiry:
            swarm_emoji = " 🐝" if hive.get("swarm") else ""
            rows.append((ready_time, f"Beehive {coord}{swarm_emoji}"))
    
    return rows

# ---------- formattazione UI ----------
def _fmt_future_section(title: str, rows: List[Tuple[int, str]], now_utc: datetime) -> List[str]:
    """Formatta una sezione di elementi futuri"""
    if not rows:
        return []
    
    lines = [f"*{title}*:"]
    
    # Filtra ulteriormente i timestamp non validi
    valid_rows = []
    for ready_ms, name in rows:
        if is_valid_timestamp(ready_ms):
            valid_rows.append((ready_ms, name))
    
    # Raggruppa le righe valide
    grouped = group_rows(sorted(valid_rows), GROUP_THRESHOLD_MS)
    
    for ready_ms, name, count in grouped[:MAX_LINES]:
        try:
            # Controllo aggiuntivo per timestamp validi
            if ready_ms <= 0 or ready_ms > 4102444800000:  # Evita timestamp impossibili
                continue
                
            dt_ready_utc = datetime.fromtimestamp(ready_ms / 1000, tz=timezone.utc)
            dt_ready_local = dt_ready_utc.astimezone(TZ)
            
            remaining_sec = (ready_ms - int(now_utc.timestamp() * 1000)) / 1000
            time_str = human_delta_short(remaining_sec)
            
            if count > 1:
                lines.append(f"{name}: {dt_ready_local.strftime('%d/%m - %H:%M')} ({time_str}) x{count}")
            else:
                lines.append(f"{name}: {dt_ready_local.strftime('%d/%m - %H:%M')} ({time_str})")
                
        except (ValueError, OverflowError, OSError) as e:
            log.warning(f"Timestamp non valido per {name}: {ready_ms} - {e}")
            continue
    
    return lines

def _fmt_ready_section(title: str, names: List[str]) -> List[str]:
    """Formatta una sezione di elementi pronti"""
    lines: List[str] = [f"{title}:"]
    if not names:
        lines.append("nulla")
        return lines
    
    # Raggruppa per nome (conteggio)
    freq: Dict[str, int] = {}
    for n in names:
        freq[n] = freq.get(n, 0) + 1
    
    for name in sorted(freq.keys()):
        cnt = freq[name]
        lines.append(f"{name}" + (f" x{cnt}" if cnt > 1 else ""))
    
    return lines

# ---------- comando principale ----------
async def in_corso_forland(land_id: str, chat_id: int) -> str:
    """
    Genera il messaggio 'In corso' con tutte le categorie
    
    Args:
        land_id: ID della farm
        chat_id: ID chat Telegram (per recuperare API key)
    
    Returns:
        str: Messaggio formattato da inviare all'utente
    """
    try:
        from api import fetch_farm_with_user_key
        payload, _used_url, server_now_ms = await fetch_farm_with_user_key(
            land_id, chat_id, force=True
        )
    except ValueError as e:
        return f"Errore: {str(e)}"
    except Exception as e:
        log.error(f"Errore in in_corso_forland: {e}")
        return "Impossibile leggere i dati della farm."

    now_utc = (
        datetime.fromtimestamp(server_now_ms / 1000, tz=timezone.utc)
        if server_now_ms
        else datetime.now(timezone.utc)
    )
    now_ms = int(now_utc.timestamp() * 1000)

    out: List[str] = ["*In corso:*", ""]

    # 1) Colture
    crops_lines = _fmt_future_section("Colture", _future_crops(payload, now_ms), now_utc)
    if crops_lines:
        out.extend(crops_lines)
        out.append("")

    # 2) Frutta
    fruit_lines = _fmt_future_section("Frutta", _future_fruit(payload, now_ms), now_utc)
    if fruit_lines:
        out.extend(fruit_lines)
        out.append("")

    # 3) Cucina
    cooking_lines = _fmt_future_section("Cucina", _future_cooking(payload, now_ms), now_utc)
    if cooking_lines:
        out.extend(cooking_lines)
        out.append("")

    # 4) Crafting Box
    craftingbox_lines = _fmt_future_section("Crafting Box", _future_craftingbox(payload, now_ms), now_utc)
    if craftingbox_lines:
        out.extend(craftingbox_lines)
        out.append("")

    # 5) Compost
    compost_lines = _fmt_future_section("Compost", _future_compost(payload, now_ms), now_utc)
    if compost_lines:
        out.extend(compost_lines)
        out.append("")

    # 6) Animali
    animals_lines = _fmt_future_section("Animali", _future_animals(payload, now_ms), now_utc)
    if animals_lines:
        out.extend(animals_lines)
        out.append("")

    # 7) Minerali
    minerals_lines = _fmt_future_section("Minerali", _future_minerals(payload, now_ms), now_utc)
    if minerals_lines:
        out.extend(minerals_lines)
        out.append("")

    # 8) Alberi
    trees_lines = _fmt_future_section("Alberi", _future_trees(payload, now_ms), now_utc)
    if trees_lines:
        out.extend(trees_lines)
        out.append("")

    # 9) Fiori
    flowers_lines = _fmt_future_section("Fiori", _future_flowers(payload, now_ms), now_utc)
    if flowers_lines:
        out.extend(flowers_lines)
        out.append("")

    # 10) Alveari
# 10) Alveari - versione semplificata per "In corso"
    beehives_future_lines = _fmt_future_section("Alveari", _future_beehives(payload, now_ms), now_utc)
    if beehives_future_lines:
        out.extend(beehives_future_lines)
        out.append("")

    # Footer con timestamp API
    if server_now_ms:
        dt_api_local = datetime.fromtimestamp(server_now_ms / 1000, tz=timezone.utc).astimezone(TZ)
        out.append(f"Aggiornamento API: {dt_api_local.strftime('%d/%m - %H:%M')}")

    return "\n".join(out)

async def pronti_for_land(land_id: str, chat_id: int) -> str:
    """
    Genera il messaggio degli elementi pronti
    
    Args:
        land_id: ID della farm
        chat_id: ID chat Telegram (per recuperare API key)
    
    Returns:
        str: Messaggio formattato da inviare all'utente
    """
    try:
        from api import fetch_farm_with_user_key
        payload, _used_url, server_now_ms = await fetch_farm_with_user_key(
            land_id, chat_id, force=True
        )
    except ValueError as e:
        return f"Errore: {str(e)}"
    except Exception as e:
        log.error(f"Errore in pronti_for_land: {e}")
        return "Impossibile leggere i dati della farm."

    now_utc = (
        datetime.fromtimestamp(server_now_ms / 1000, tz=timezone.utc)
        if server_now_ms
        else datetime.now(timezone.utc)
    )
    now_ms = int(now_utc.timestamp() * 1000)

    out: List[str] = ["*Pronti:*", ""]

    # Aggiungi solo le sezioni che hanno contenuto
    sections = [
        ("Colture", _ready_crops(payload, now_ms)),
        ("Frutta", _ready_fruit(payload, now_ms)),
        ("Cucina", _ready_cooking(payload, now_ms)),
        ("Compost", _ready_compost(payload, now_ms)),
        ("Animali", _ready_animals(payload, now_ms)),
        ("Minerali", _ready_minerals(payload, now_ms)),
        ("Alberi", _ready_trees(payload, now_ms)),
        ("Fiori", _ready_flowers(payload, now_ms))
    ]

    for title, items in sections:
        lines = _fmt_ready_section(title, items)
        if len(lines) > 1:  # Se c'almeno un elemento oltre al titolo
            out.extend(lines)
            out.append("")

    # Footer con timestamp API
    if server_now_ms:
        dt_api_local = datetime.fromtimestamp(server_now_ms / 1000, tz=timezone.utc).astimezone(TZ)
        out.append(f"Aggiornamento API: {dt_api_local.strftime('%d/%m - %H:%M')}")

    return "\n".join(out)

__all__ = [
    "in_corso_forland", 
    "pronti_for_land",
    "_future_crops",
    "_future_fruit", 
    "_future_cooking",
    "_future_compost",
    "_future_animals",
    "_future_minerals",
    "_future_trees",
    "_future_flowers",
    "_future_beehives"
]