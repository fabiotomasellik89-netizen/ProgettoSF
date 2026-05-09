from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import TZ, GROUP_THRESHOLD_MS, MAX_LINES
from utils import to_ms, human_delta_short
from api import fetch_farm_with_user_key
from crops import group_rows  # per il raggruppo entro 1 minuto

__all__ = ["find_cooking_items", "cucina_for_land"]

# --- chiavi che spesso compaiono nel payload del deli/cooking ---
_TIME_KEYS = (
    "readyAt", "availableAt", "endAt", "completeAt",
    "finishAt", "ready_at", "available_at",
)
_NAME_KEYS = ("name", "recipe", "item", "product")

def _extract_time(d: Dict[str, Any]) -> int | None:
    # 1) diretto
    for k in _TIME_KEYS:
        t = to_ms(d.get(k))
        if isinstance(t, int) and t > 0:
            return t
    # 2) annidato
    for inner in ("progress", "state", "status"):
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

def find_cooking_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Ritorna tutti gli item in cottura come:
      [{ "name": str, "ready_ms": int }]
    1) legge esplicitamente payload['deli']['cooking']
    2) fa una scansione completa di dict/list alla ricerca di (name + readyAt*)
    """
    items: List[Dict[str, Any]] = []

    def add(name, t):
        t = to_ms(t)
        if isinstance(name, str) and name.strip() and isinstance(t, int) and t > 0:
            items.append({"name": name.strip(), "ready_ms": t})

    # 1) percorso esplicito deli.cooking
    deli = payload.get("deli")
    if isinstance(deli, dict):
        cooking = deli.get("cooking")
        if isinstance(cooking, list):
            for it in cooking:
                if isinstance(it, dict):
                    add(it.get("name") or it.get("recipe"),
                        it.get("readyAt") or it.get("availableAt"))

    # 2) fallback robusto
    def maybe_add(node: Any):
        if not isinstance(node, dict):
            return
        nm = _extract_name(node)
        rt = _extract_time(node)
        if nm and rt:
            add(nm, rt)

    def scan(node: Any):
        if isinstance(node, dict):
            maybe_add(node)
            for v in node.values():
                scan(v)
        elif isinstance(node, list):
            for v in node:
                scan(v)

    scan(payload)

    # dedupe
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for it in items:
        key = (it["name"], it["ready_ms"])
        if key in seen:
            continue
        seen.add(key); uniq.append(it)
    return uniq

# ---- comando / pulsante "Cucina" ----
async def cucina_for_land(update: Update, context: ContextTypes.DEFAULT_TYPE, land_id: str):
    try:
        chat_id = update.effective_chat.id
        payload, used_url, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id)
    except Exception:
        await update.message.reply_text("Errore: Impossibile leggere i dati della farm.")
        return

    if server_now_ms:
        now_ms = server_now_ms
        now_utc = datetime.fromtimestamp(server_now_ms / 1000, tz=timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)
        now_ms = int(now_utc.timestamp() * 1000)

    items = find_cooking_items(payload)

    fut_rows: List[Tuple[int, str]] = []
    ready_names: List[str] = []
    for it in items:
        if it["ready_ms"] > now_ms:
            fut_rows.append((it["ready_ms"], it["name"]))
        else:
            ready_names.append(it["name"])

    lines = ["Cucina:"]
    if ready_names:
        for n in sorted(ready_names):
            lines.append(f"{n}:  pronto")

    if fut_rows:
        groups = group_rows(sorted(fut_rows), GROUP_THRESHOLD_MS)
        for t, nm, cnt in groups[:MAX_LINES]:
            dt_utc = datetime.fromtimestamp(t/1000, tz=timezone.utc)
            dt_loc = dt_utc.astimezone(TZ)
            cd = human_delta_short(dt_utc, now_utc)
            lines.append(f"{nm}:  {dt_loc.strftime('%d/%m - %H:%M')} ({cd})" + (f" x{cnt}" if cnt > 1 else ""))

    if not ready_names and not fut_rows:
        lines.append("â€” nulla in cottura")

    if server_now_ms:
        dt_api = datetime.fromtimestamp(server_now_ms/1000, tz=timezone.utc).astimezone(TZ)
        lines.append(f"\nAggiornamento API: {dt_api.strftime('%d/%m - %H:%M')}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)