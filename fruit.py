# fruit.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from api import fetch_farm_with_user_key
from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES
from utils import to_ms, human_delta_short
from crops import group_rows

__all__ = ["find_fruit_items", "frutta_for_land"]

log = logging.getLogger("sflbot")

# tabella tempi (supporta entrambi i nomi usati nel config)
try:
    from config import FRUIT_REGEN_MS as FRUIT_MS
except Exception:
    try:
        from config import FRUIT_GROWTH_MS as FRUIT_MS
    except Exception:
        FRUIT_MS = {}

# alias opzionali
try:
    from config import FRUIT_ALIASES as _ALIASES
except Exception:
    _ALIASES = {}

# normalizzazione case-insensitive con priorità  alla tabella tempi
_FRUIT_KEYS = {k.casefold(): k for k in FRUIT_MS.keys()}
_ALIAS_KEYS = {k.casefold(): v for k, v in (_ALIASES or {}).items()}

def _norm_name(raw: str | None) -> str:
    if not raw:
        return "Fruit"
    s = raw.strip()
    key = s.casefold()
    if key in _FRUIT_KEYS:
        return _FRUIT_KEYS[key]
    if key in _ALIAS_KEYS:
        return _ALIAS_KEYS[key]
    return s


def find_fruit_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cerca i frutti nella posizione corretta dell'API"""
    out: List[Dict[str, Any]] = []
    
    # Cerca nella posizione principale dell'API
    farm = payload.get("farm", {})
    fruit_patches = farm.get("fruitPatches", {})
    
    if not isinstance(fruit_patches, dict):
        return out

    for patch_key, patch in fruit_patches.items():
        if not isinstance(patch, dict):
            continue
            
        fruit = patch.get("fruit", {})
        if not isinstance(fruit, dict):
            continue

        name = fruit.get("name", "").strip()
        if not name:
            continue
            
        # Usa harvestedAt se disponibile, altrimenti plantedAt
        harvested_at = to_ms(fruit.get("harvestedAt"))
        planted_at = to_ms(fruit.get("plantedAt"))
        
        if not harvested_at and not planted_at:
            continue
            
        start_time = max(harvested_at or 0, planted_at or 0)
        base_time = FRUIT_MS.get(name)
        
        if not base_time:
            continue
            
        ready_ms = start_time + base_time
        out.append({"name": name, "ready_ms": ready_ms})
    
    return out

# comando opzionale per test rapido della sola sezione frutta

async def frutta_for_land(update: Update, context: ContextTypes.DEFAULT_TYPE, land_id: str):
    try:
        chat_id = update.effective_chat.id
        payload, _url, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id, force=True)
    except Exception:
        await update.message.reply_text("Errore: Impossibile leggere i dati della farm.")
        return

    now_utc = datetime.fromtimestamp(server_now_ms/1000, tz=timezone.utc) if server_now_ms else datetime.now(timezone.utc)
    now_ms = int(now_utc.timestamp()*1000)

    rows: List[Tuple[int, str]] = []
    for it in find_fruit_items(payload):
        t = it.get("ready_ms")
        n = it.get("name") or "Fruit"
        if isinstance(t, int) and t > now_ms:
            rows.append((t, n))

    lines: List[str] = ["Frutta:"]
    if not rows:
        lines.append("â€” nessun albero trovato")
    else:
        for anchor_ms, name, cnt in group_rows(sorted(rows), GROUP_THRESHOLD_MS)[:MAX_LINES]:
            dt_ready_utc = datetime.fromtimestamp(anchor_ms/1000, tz=timezone.utc)
            cd = human_delta_short(dt_ready_utc, now_utc)
            lines.append(f"{name}:  {dt_ready_utc.astimezone(TZ).strftime('%d/%m - %H:%M')} ({cd})" + (f" x{cnt}" if cnt>1 else ""))

    if server_now_ms:
        dt_api_local = datetime.fromtimestamp(server_now_ms/1000, tz=timezone.utc).astimezone(TZ)
        lines.append(f"\nAggiornamento API: {dt_api_local.strftime('%d/%m - %H:%M')}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)