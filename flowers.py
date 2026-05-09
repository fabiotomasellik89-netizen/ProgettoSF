from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES, FLOWER_GROWTH_MS
from utils import to_ms, human_delta_short
from api import fetch_farm_with_user_key
from crops import group_rows

__all__ = ["find_flower_items", "flowers_for_land"]

def find_flower_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    
    farm = payload.get("farm", {})
    
    # Cerca in flowers.flowerBeds
    flowers = farm.get("flowers", {})
    flower_beds = flowers.get("flowerBeds", {})
    
    if isinstance(flower_beds, dict):
        for bed_key, bed_data in flower_beds.items():
            if isinstance(bed_data, dict):
                flower_data = bed_data.get("flower")
                if isinstance(flower_data, dict):
                    planted_at = to_ms(flower_data.get("plantedAt"))
                    name = flower_data.get("name", "Flower")
                    
                    if planted_at and name and "sunflower" not in name.lower():
                        # Usa il tempo di crescita specifico per questo fiore
                        growth_time = FLOWER_GROWTH_MS.get(name, 24 * 60 * 60 * 1000)
                        ready_ms = planted_at + growth_time
                        
                        items.append({"name": name, "ready_ms": ready_ms})
    
    return items

async def flowers_for_land(update: Update, context: ContextTypes.DEFAULT_TYPE, land_id: str):
    try:
        chat_id = update.effective_chat.id
        payload, _, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id)
    except Exception:
        await update.message.reply_text("Errore: Impossibile leggere i dati della farm.")
        return
    
    now_utc = datetime.fromtimestamp((server_now_ms or 0)/1000, tz=timezone.utc) if server_now_ms else datetime.now(timezone.utc)
    now_ms = int(now_utc.timestamp()*1000)

    items = find_flower_items(payload)

    fut: List[Tuple[int, str]] = []
    ready: List[str] = []
    
    for it in items:
        if it["ready_ms"] > now_ms:
            fut.append((it["ready_ms"], it["name"]))
        else:
            ready.append(it["name"])

    lines = ["ðŸŒ¼ Fiori:"]
    for n in sorted(ready):
        lines.append(f"{n}: pronto")
    
    if fut:
        for t, n, cnt in group_rows(sorted(fut), GROUP_THRESHOLD_MS)[:MAX_LINES]:
            dt = datetime.fromtimestamp(t/1000, tz=timezone.utc).astimezone(TZ)
            lines.append(f"{n}:  {dt.strftime('%d/%m - %H:%M')} ({human_delta_short(datetime.fromtimestamp(t/1000, tz=timezone.utc), now_utc)})" + (f" x{cnt}" if cnt > 1 else ""))
    
    if not ready and not fut:
        lines.append("â€” nulla")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)