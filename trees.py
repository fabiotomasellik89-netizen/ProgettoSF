from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES
from utils import to_ms, human_delta_short
from api import fetch_farm_with_user_key
from crops import group_rows

__all__ = ["find_tree_items", "trees_for_land"]

_TIME_KEYS = (
    "readyAt","createdAT","endAt","completeAt","finishAt",
    "recoverAt","recoveryAt","choppedAt","ready_at","available_at"
)
_NAME_KEYS = ("name","item","product","type","label")

def _extract_time(d: Dict[str, Any]) -> int | None:
    for k in _TIME_KEYS:
        t = to_ms(d.get(k))
        if isinstance(t, int) and t > 0:
            return t
    for inner in ("progress","state","status"):
        sub = d.get(inner)
        if isinstance(sub, dict):
            for k in _TIME_KEYS:
                t = to_ms(sub.get(k))
                if isinstance(t, int) and t > 0:
                    return t
    return None

def _extract_name(d: Dict[str, Any]) -> str | None:
    for k in _NAME_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def find_tree_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    
    farm = payload.get("farm", {})
    BASE_TREE_REGEN_MS = 7_200_000  # 2h
    
    if "trees" in farm and isinstance(farm["trees"], dict):
        trees = farm["trees"]
        for tree_key, tree_data in trees.items():
            if isinstance(tree_data, dict):
                # Cerca i dati annidati sotto "wood"
                wood_data = tree_data.get("wood")
                if isinstance(wood_data, dict):
                    chopped_at = to_ms(wood_data.get("choppedAt"))
                    if chopped_at:
                        ready_ms = chopped_at + BASE_TREE_REGEN_MS
                        name = "Tree"
                        items.append({"name": name, "ready_ms": ready_ms})
    
    return items

def find_ready_tree_items(payload: Dict[str, Any], now_ms: int) -> List[str]:
    ready_items = []
    farm = payload.get("farm", {})
    
    if "trees" in farm:
        trees = farm["trees"]
        for tree_key, tree_data in trees.items():
            if isinstance(tree_data, dict) and tree_data.get("wood", {}).get("choppedAt"):
                ready_items.append("Tree")
    
    return ready_items

async def trees_for_land(update: Update, context: ContextTypes.DEFAULT_TYPE, land_id: str):
    try:
        chat_id = update.effective_chat.id
        payload, _, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id)
    except Exception:
        await update.message.reply_text("Errore: Impossibile leggere i dati della farm.")
        return
    now_utc = datetime.fromtimestamp((server_now_ms or 0)/1000, tz=timezone.utc) if server_now_ms else datetime.now(timezone.utc)
    now_ms = int(now_utc.timestamp()*1000)

    fut: List[Tuple[int,str]]=[]; ready=[]
    for it in find_tree_items(payload):
        if it["ready_ms"]>now_ms: fut.append((it["ready_ms"], it["name"]))
        else: ready.append(it["name"])

    lines=["ðŸŒ³ Alberi:"]
    for n in sorted(ready): lines.append(f"{n}: pronto")
    if fut:
        for t,n,cnt in group_rows(sorted(fut), GROUP_THRESHOLD_MS)[:MAX_LINES]:
            dt=datetime.fromtimestamp(t/1000,tz=timezone.utc).astimezone(TZ)
            lines.append(f"{n}:  {dt.strftime('%d/%m - %H:%M')} ({human_delta_short(datetime.fromtimestamp(t/1000,tz=timezone.utc), now_utc)})" + (f" x{cnt}" if cnt>1 else ""))
    if not ready and not fut: lines.append("â€” nulla")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)