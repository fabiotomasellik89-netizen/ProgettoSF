# notify_format.py – Formattazione notifiche con alveari e swarm aggiornati

from __future__ import annotations
from typing import Optional, Dict, Any

ITEM_EMOJI = {
    "Sunflower": "🌻", "Potato": "🥔", "Pumpkin": "🎃", "Carrot": "🥕", "Cabbage": "🥬",
    "Beetroot": "🟣", "Cauliflower": "🥦", "Parsnip": "🌱", "Radish": "🌱", "Wheat": "🌾",
    "Kale": "🥬", "Eggplant": "🍆", "Corn": "🌽", "Tomato": "🍅", "Blueberry": "🫐",
    "Orange": "🍊", "Apple": "🍎", "Banana": "🍌", "Lemon": "🍋",
    "Stone": "🪨", "Iron": "⚙️", "Gold": "🪙", "Crimstone": "🔴", "Sunstone": "🟡", "Oil": "🛢️",
    "Wood": "🪵", "Egg": "🥚", "Milk": "🥛",
    "default": "⏰",
}

TYPE_EMOJI = {
    "crops": "🌱", "fruits": "🍎", "minerals": "⛏️", "trees": "🌳", "animals": "🐄",
    "flowers": "🌸", "compost": "♻️", "cooking": "🍳",
    "beehive_full": "🍯", "beehive_blocked": "🚫", "beehive_soon": "🍯", "bee_swarm": "🐝",
}

def get_emoji(item_name: str) -> str:
    return ITEM_EMOJI.get(item_name, ITEM_EMOJI.get("default", "⏰"))

def _is_sunshower_active(payload: Dict[str, Any], item_type: str) -> bool:
    if item_type != "crops":
        return False
    return payload.get("game", {}).get("weather", "").lower() == "sunshower"

def _fmt_eta(time_left_ms: int, has_sunshower: bool = False) -> str:
    if time_left_ms <= 0:
        return "ora"
    secs = max(0, time_left_ms // 1000)
    hours, rem = divmod(secs, 3600)
    minutes, seconds = divmod(rem, 60)
    sun = " 🌞" if has_sunshower else ""
    if hours:
        return f"{hours}h {minutes}m{sun}"
    if minutes:
        return f"{minutes}m {seconds}s{sun}" if seconds else f"{minutes}m{sun}"
    return f"{seconds}s{sun}"

def render_line(
    payload: Dict[str, Any],
    item_type: str,
    item_name: str,
    count: float = 1.0,
    time_left_ms: int = 0,
    chat_id: Optional[int] = None
) -> str:
    skills = payload.get("farm", {}).get("skills", {})
    swarm_boost = "+0.3" if "Pollen Power Up" in skills else "+0.2"

    base_emoji = TYPE_EMOJI.get(item_type, get_emoji(item_name))

    if item_type == "bee_swarm":
        return f"🐝 {item_name} → {swarm_boost} ai raccolti!"
    if item_type == "beehive_blocked":
        return f"🚫 {item_name} è BLOCCATO (100%)! Raccogli subito!"
    if item_type == "beehive_full":
        return f"🍯 {item_name} è pieno (>98%)! Raccogli per chance sciame!"
    if item_type == "beehive_soon":
        eta = _fmt_eta(time_left_ms)
        return f"🍯 {item_name} sarà pieno tra {eta}! Prepara per sciame!"

    has_sunshower = _is_sunshower_active(payload, item_type)
    item_display = f"{int(count)} {item_name}" if count > 1 else item_name

    if time_left_ms == 0:
        return f"{base_emoji} {item_display} è pronto!"
    else:
        eta_str = _fmt_eta(time_left_ms, has_sunshower)
        return f"{base_emoji} {item_display} sarà pronto tra {eta_str}!"