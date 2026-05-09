# animals.py - Versione con notifica beehive pieno
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES
from utils import to_ms, human_delta_short
from api import fetch_farm_with_user_key
from crops import group_rows
import time

log = logging.getLogger("sflbot")

__all__ = ["find_animal_items", "animals_for_land", "find_ready_animal_items", "find_beehive_full"]

# Soglia massima miele producibile (53.989M circa)
BEEHIVE_MAX_HONEY = 68664000

def find_beehive_full(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Ritorna alveari che sono pieni o quasi pieni, con dettagli per notifiche.
    """
    full_beehives = []
    
    farm = payload.get("farm", {})
    beehives = farm.get("beehives", {})
    skills = farm.get("skills", {})
    has_hyper_bees = "Hyper Bees" in skills
    honey_rate = int(2_260_000 * 1.1) if has_hyper_bees else 2_260_000  # CORRETTO
    
    now_ms = int(time.time() * 1000)
    
    if not isinstance(beehives, dict):
        return full_beehives
    
    for hive_id, hive_data in beehives.items():
        if not isinstance(hive_data, dict):
            continue

        coord = f"({hive_data.get('x', '?')},{hive_data.get('y', '?')})"
        honey = hive_data.get("honey", {}) or {}
        produced = float(honey.get("produced", 0))
        updated_at = honey.get("updatedAt", now_ms)
        
        # Calcolo miele accumulato PRECISO
        hours_since_update = max(0, (now_ms - updated_at) / 3_600_000.0)
        accrued = hours_since_update * honey_rate
        current_honey = produced + accrued
        
        # Limita al massimo
        if current_honey > BEEHIVE_MAX_HONEY:
            current_honey = BEEHIVE_MAX_HONEY
        
        flowers = hive_data.get("flowers", []) or []
        has_flower = bool(flowers)

def find_animal_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    
    farm = payload.get("farm", {})
    current_time_ms = int(time.time() * 1000)
    
    # Analizza henHouse - Polli
    if "henHouse" in farm and isinstance(farm["henHouse"], dict):
        hen_house = farm["henHouse"]
        if "animals" in hen_house and isinstance(hen_house["animals"], dict):
            animals = hen_house["animals"]
            for animal_key, animal_data in animals.items():
                if isinstance(animal_data, dict) and animal_data.get("type") == "Chicken":
                    state = animal_data.get("state")
                    
                    if state == "sick":
                        continue
                    
                    awake_at = to_ms(animal_data.get("awakeAt"))
                    
                    if awake_at and awake_at > current_time_ms:
                        items.append({"name": "Chicken", "ready_ms": awake_at})
    
    # NOTA: Le api (beehives) sono ora gestite nella sezione dedicata "Alveari" in tempo.py
    # Non le includiamo più qui per evitare duplicati
    
    # Analizza barn - Mucche e Pecore
    if "barn" in farm and isinstance(farm["barn"], dict):
        barn = farm["barn"]
        if "animals" in barn and isinstance(barn["animals"], dict):
            animals = barn["animals"]
            for animal_key, animal_data in animals.items():
                if isinstance(animal_data, dict):
                    animal_type = animal_data.get("type")
                    state = animal_data.get("state")
                    
                    if state == "sick":
                        continue
                    
                    awake_at = to_ms(animal_data.get("awakeAt"))
                    if awake_at and awake_at > current_time_ms:
                        if animal_type == "Cow":
                            items.append({"name": "Cow", "ready_ms": awake_at})
                        elif animal_type == "Sheep":
                            items.append({"name": "Sheep", "ready_ms": awake_at})
    
    return items

def find_ready_animal_items(payload: Dict[str, Any], now_ms: int) -> List[str]:
    """Restituisce i nomi degli animali PRONTI"""
    ready_items = []
    
    farm = payload.get("farm", {})
    
    # 1. Polli pronti
    if "henHouse" in farm and isinstance(farm["henHouse"], dict):
        hen_house = farm["henHouse"]
        if "animals" in hen_house and isinstance(hen_house["animals"], dict):
            animals = hen_house["animals"]
            chicken_count = 0
            for animal_key, animal_data in animals.items():
                if isinstance(animal_data, dict) and animal_data.get("type") == "Chicken":
                    state = animal_data.get("state")
                    if state == "sick":
                        continue
                    
                    awake_at = to_ms(animal_data.get("awakeAt"))
                    if awake_at and awake_at <= now_ms:
                        chicken_count += 1
            
            if chicken_count > 0:
                ready_items.append(f"Chicken x{chicken_count}")
    
    # NOTA: Le api sono ora gestite nella sezione dedicata "Alveari" in tempo.py
    
    # 2. Mucche e pecore pronte
    if "barn" in farm and isinstance(farm["barn"], dict):
        barn = farm["barn"]
        if "animals" in barn and isinstance(barn["animals"], dict):
            animals = barn["animals"]
            cow_count = 0
            sheep_count = 0
            
            for animal_key, animal_data in animals.items():
                if isinstance(animal_data, dict):
                    animal_type = animal_data.get("type")
                    state = animal_data.get("state")
                    
                    if state == "sick":
                        continue
                    
                    awake_at = to_ms(animal_data.get("awakeAt"))
                    if awake_at and awake_at <= now_ms:
                        if animal_type == "Cow":
                            cow_count += 1
                        elif animal_type == "Sheep":
                            sheep_count += 1
            
            if cow_count > 0:
                ready_items.append(f"Cow x{cow_count}")
            if sheep_count > 0:
                ready_items.append(f"Sheep x{sheep_count}")
    
    return ready_items

async def animals_for_land(update: Update, context: ContextTypes.DEFAULT_TYPE, land_id: str):
    try:
        chat_id = update.effective_chat.id
        payload, _, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id)
    except Exception:
        await update.message.reply_text("Errore: Impossibile leggere i dati della farm.")
        return
        
    now_utc = datetime.fromtimestamp((server_now_ms or 0)/1000, tz=timezone.utc) if server_now_ms else datetime.now(timezone.utc)
    now_ms = int(now_utc.timestamp()*1000)
    
    items = find_animal_items(payload)
    if not items:
        await update.message.reply_text("Nessun animale in produzione al momento.")
        return
    
    # Converti in formato compatibile con group_rows
    rows: List[Tuple[str, str, float, int]] = []
    for it in items:
        name = it.get("name", "Animal")
        ready_ms = it.get("ready_ms")
        if ready_ms:
            delta = ready_ms - now_ms
            if delta < 0:
                delta = 0
            rows.append(("animal", name, 1.0, delta))
    
    # Raggruppa e formatta
    grouped = group_rows(rows, GROUP_THRESHOLD_MS)
    lines: List[str] = []
    
    for grp in grouped:
        rep = grp["representative"]
        cnt = grp["count"]
        delta_ms = grp["time_left_ms"]
        delta_str = human_delta_short(delta_ms)
        
        item_name = rep[1]
        
        when_utc = now_utc + datetime.timedelta(milliseconds=delta_ms)
        when_local = when_utc.astimezone(TZ)
        when_str = when_local.strftime("%d/%m - %H:%M")
        
        if cnt > 1:
            lines.append(f"{item_name} x{cnt} {when_str} ({delta_str})")
        else:
            lines.append(f"{item_name} {when_str} ({delta_str})")
    
    # Limita il numero di righe
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines.append(f"... e altri {len(grouped) - MAX_LINES} gruppi")
    
    # Controlla beehive pieni
    full_beehives = find_beehive_full(payload)
    if full_beehives:
        lines.append("\n🍯 ALVEARI:")
        for hive in full_beehives:
            if "swarm" in hive.get("type", ""):
                lines.append(f"{hive['name']} → +0.2/+0.3 ai raccolti!")
            elif "blocked" in hive.get("type", ""):
                lines.append(f"🚫 {hive['name']}: BLOCCATO (100%)")
                lines.append("   Svuota subito!")
            elif "full" in hive.get("type", ""):
                lines.append(f"{hive['name']}: {hive['produced']:,.0f} miele (>98%)")
                lines.append("   Raccogli per chance sciame!")
            elif "soon" in hive.get("type", ""):
                eta = human_delta_short(hive.get("time_left_ms", 0) * 1000, now_utc)
                lines.append(f"🍯 {hive['name']} sarà pieno tra {eta}")
    
    text = "Animali:\n" + "\n".join(lines)
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)