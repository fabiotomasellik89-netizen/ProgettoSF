from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES
from utils import to_ms, human_delta_short
from api import fetch_farm_with_user_key
from crops import group_rows  # raggruppo entro 1 min
import time

__all__ = ["find_compost_items", "compost_for_land"]

_TIME_KEYS = (
    "readyAt","availableAt","endAt","completeAt","finishAt",
    "recoverAt","recoveryAt","ready_at","available_at"
)
_NAME_KEYS = ("name","item","product","type","label","recipe")

def _extract_time(d: Dict[str, Any]) -> int | None:
    # Cerca in pià¹ livelli e pià¹ campi
    time_keys = [
        "readyAt", "availableAt", "endAt", "completeAt", "finishAt", 
        "ready_at", "available_at", "endsAt", "completedAt", "finishedAt",
        "startAt", "startedAt", "producedAt", "productionEndsAt"
    ]
    
    for key in time_keys:
        t = to_ms(d.get(key))
        if t:
            return t
    
    # Cerca annidato in tutti i sottolivelli possibili
    for inner_key in ["progress", "state", "status", "production", "process", "producing", "crafting"]:
        inner = d.get(inner_key)
        if isinstance(inner, dict):
            for key in time_keys:
                t = to_ms(inner.get(key))
                if t:
                    return t
                # Cerca ancora pià¹ in profondità 
                for deep_key in ["progress", "state", "status"]:
                    deep_inner = inner.get(deep_key)
                    if isinstance(deep_inner, dict):
                        for deep_time_key in time_keys:
                            t = to_ms(deep_inner.get(deep_time_key))
                            if t:
                                return t
    
    return None

def _extract_name(d: Dict[str, Any]) -> str | None:
    for k in _NAME_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def find_compost_items(payload: Dict[str, Any], server_now_ms: int = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    
    farm = payload.get("farm", {})
    buildings = farm.get("buildings", {})
    
    # Cerca Compost Bin
    compost_bins = buildings.get("Compost Bin", [])
    for i, bin_data in enumerate(compost_bins):
        if isinstance(bin_data, dict):
            producing = bin_data.get("producing")
            if isinstance(producing, dict):
                ready_at = to_ms(producing.get("readyAt"))
                if ready_at:
                    items.append({"name": "Compost Bin", "ready_ms": ready_at})
    
    # Cerca Turbo Composter
    turbo_composters = buildings.get("Turbo Composter", [])
    for i, turbo_data in enumerate(turbo_composters):
        if isinstance(turbo_data, dict):
            producing = turbo_data.get("producing")
            if isinstance(producing, dict):
                ready_at = to_ms(producing.get("readyAt"))
                if ready_at:
                    items.append({"name": "Turbo Composter", "ready_ms": ready_at})
    
    # Cerca Premium Composter (se presente)
    premium_composters = buildings.get("Premium Composter", [])
    for i, premium_data in enumerate(premium_composters):
        if isinstance(premium_data, dict):
            producing = premium_data.get("producing")
            if isinstance(producing, dict):
                ready_at = to_ms(producing.get("readyAt"))
                if ready_at:
                    items.append({"name": "Premium Composter", "ready_ms": ready_at})
    
    return items

async def compost_for_land(update: Update, context: ContextTypes.DEFAULT_TYPE, land_id: str):
    try:
        chat_id = update.effective_chat.id
        payload, _, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id)
    except Exception:
        await update.message.reply_text("Errore: Impossibile leggere i dati della farm.")
        return
        
    now_utc = datetime.fromtimestamp((server_now_ms or 0)/1000, tz=timezone.utc) if server_now_ms else datetime.now(timezone.utc)
    now_ms = int(now_utc.timestamp()*1000)

    compost_items = find_compost_items(payload, server_now_ms)
    
    fut: List[Tuple[int, str]] = []
    ready: List[str] = []
    
    for it in compost_items:
        if it["ready_ms"] > now_ms:
            fut.append((it["ready_ms"], it["name"]))
        else:
            ready.append(it["name"])

    lines = ["â™»ï¸ *Compostaggio*:"]
    
    # Mostra prima quelli pronti
    if ready:
        for n in sorted(ready):
            lines.append(f"âœ… {n}: pronto per la raccolta")
        lines.append("")
    
    # Poi quelli futuri
    if fut:
        for t, n, cnt in group_rows(sorted(fut), GROUP_THRESHOLD_MS)[:MAX_LINES]:
            dt = datetime.fromtimestamp(t/1000, tz=timezone.utc).astimezone(TZ)
            time_remaining = human_delta_short(datetime.fromtimestamp(t/1000, tz=timezone.utc), now_utc)
            lines.append(f"â° {n}: {dt.strftime('%d/%m - %H:%M')} ({time_remaining})")
    elif not ready:
        lines.append("â€” Nessun compostatore attivo")
    
    # Aggiungi informazioni utili
    lines.append("")
    lines.append("ðŸ’¡ *Info compostaggio:*")
    lines.append("â€¢ Compost Bin: 6 ore")
    lines.append("â€¢ Turbo Composter: 8 ore")
    lines.append("â€¢ Premium Composter: 12 ore")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)