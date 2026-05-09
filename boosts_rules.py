# boosts_rules.py – COMPLETO: crops + frutti + minerali + alberi

from __future__ import annotations
from typing import Optional, Dict
import os, json, logging

log = logging.getLogger("sflbot")

_MULTIPLIERS_CACHE: Dict[str, Dict] = {}
_RULES_CACHE: Optional[Dict] = None

def _load_rules() -> Dict:
    """Carica rules/effects.json"""
    global _RULES_CACHE
    if _RULES_CACHE:
        return _RULES_CACHE
    try:
        rules_path = os.path.join(os.path.dirname(__file__), "rules", "effects.json")
        with open(rules_path, "r") as f:
            _RULES_CACHE = json.load(f)
        return _RULES_CACHE
    except Exception as e:
        log.debug(f"Errore caricamento rules: {e}")
        _RULES_CACHE = {"skills": {}, "collectibles": {}, "multipliers": {}}
        return _RULES_CACHE

def _get_land_id_from_api_keys(chat_id: Optional[str] = None) -> Optional[str]:
    """Legge land_id da data/api_keys.json"""
    try:
        api_keys_path = os.path.join(os.path.dirname(__file__), "data", "api_keys.json")
        if not os.path.exists(api_keys_path):
            return None
        with open(api_keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if chat_id and str(chat_id) in data:
            return str(data[str(chat_id)].get("land_id"))
        for chat, info in data.items():
            land_id = info.get("land_id")
            if land_id:
                return str(land_id)
        return None
    except Exception as e:
        log.debug(f"Errore lettura land_id: {e}")
        return None

def _fetch_multipliers_from_api(land_id: str) -> Optional[Dict]:
    """Fetch moltiplicatori dall'API sfl.world"""
    try:
        if land_id in _MULTIPLIERS_CACHE:
            return _MULTIPLIERS_CACHE[land_id]
        url = f"https://sfl.world/api/v1/land/{land_id}"
        import requests
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            _MULTIPLIERS_CACHE[land_id] = data
            return data
        return None
    except Exception as e:
        log.debug(f"Errore fetch API: {e}")
        return None

def _parse_api_response(api_data: Dict) -> Dict[str, float]:
    """Converte risposta API in dict {item_name: multiplier}"""
    multipliers = {}
    for category in ["crops", "fruits", "resources", "greenhouse"]:
        items = api_data.get(category, {})
        for item_name, values in items.items():
            if isinstance(values, dict):
                avg = values.get("avg", 1.0)
                display_name = item_name.capitalize()
                multipliers[display_name] = round(float(avg), 4)
    return multipliers

def _get_active_boosts_for_item(payload: dict, item_name: str) -> float:
    """Calcola bonus dalle skill/NFT attive dell'utente"""
    bonus = 0.0
    rules = _load_rules()
    skill_rules = rules.get("skills", {})
    coll_rules = rules.get("collectibles", {})
    
    farm = payload.get("farm", {})
    bumpkin = farm.get("bumpkin", {})
    skills = bumpkin.get("skills", {})
    
    for skill_name, is_active in skills.items():
        if not is_active or skill_name not in skill_rules:
            continue
        rule = skill_rules[skill_name]
        items_bonuses = rule.get("items", {})
        if item_name in items_bonuses:
            multiplier = items_bonuses[item_name]
            if multiplier and multiplier > 1.0:
                bonus += (multiplier - 1.0)
    
    home = farm.get("home", {})
    collectibles = home.get("collectibles", {})
    
    for coll_name, coll_list in collectibles.items():
        if not isinstance(coll_list, list) or not coll_list:
            continue
        active = [c for c in coll_list if "removedAt" not in c]
        if not active or coll_name not in coll_rules:
            continue
        rule = coll_rules[coll_name]
        items_bonuses = rule.get("items", {})
        if item_name in items_bonuses:
            multiplier = items_bonuses[item_name]
            if multiplier and multiplier > 1.0:
                bonus += (multiplier - 1.0)
    
    return bonus

def _get_crop_specific_boosts(payload: dict, item_name: str) -> float:
    """Calcola bonus specifici del crop: swarm + fertilizzante"""
    bonus = 0.0
    farm = payload.get("farm", {})
    crops = farm.get("crops", {})
    
    for plot_id, plot_data in crops.items():
        if not isinstance(plot_data, dict):
            continue
        crop = plot_data.get("crop", {})
        if crop.get("name") != item_name:
            continue
        
        # Bonus bee swarm (0.30 per swarm)
        bee_swarm = plot_data.get("beeSwarm", {})
        swarm_count = bee_swarm.get("count", 0)
        if swarm_count > 0:
            swarm_bonus = swarm_count * 0.30
            bonus += swarm_bonus
        
        # Bonus fertilizzante
        fertiliser = plot_data.get("fertiliser", {})
        fert_name = fertiliser.get("name", "")
        if fert_name == "Sprout Mix":
            bonus += 0.20
        elif fert_name == "Fruitful Blend":
            bonus += 0.20
        
        break
    
    return bonus

def _get_fruit_specific_boosts(payload: dict, item_name: str) -> float:
    """Calcola bonus specifici del frutteto: fertilizzante"""
    bonus = 0.0
    farm = payload.get("farm", {})
    fruit_patches = farm.get("fruitPatches", {})
    
    for patch_id, patch_data in fruit_patches.items():
        if not isinstance(patch_data, dict):
            continue
        fruit = patch_data.get("fruit", {})
        if fruit.get("name") != item_name:
            continue
        
        # Bonus fertilizzante
        fertiliser = patch_data.get("fertiliser", {})
        fert_name = fertiliser.get("name", "")
        
        if fert_name == "Fruitful Blend":
            bonus += 0.20
        
        break
    
    return bonus

def _get_mineral_critical_bonus(payload: dict, mineral_type: str, item_name: str) -> float:
    """Calcola bonus da critical hits per minerali"""
    bonus = 0.0
    farm = payload.get("farm", {})
    
    mineral_map = {
        "Stone": "stone",
        "Iron": "iron", 
        "Gold": "gold",
        "Crimstone": "crimstone"
    }
    
    farm_key = mineral_map.get(item_name)
    if not farm_key:
        return 0.0
    
    minerals = farm.get(farm_key, {})
    for plot_id, plot_data in minerals.items():
        if not isinstance(plot_data, dict):
            continue
        mineral_data = plot_data.get("stone", {})
        critical_hit = mineral_data.get("criticalHit", {})
        
        if critical_hit.get("Native", 0) == 1:
            bonus += 0.20
            break
    
    return bonus

def _get_tree_critical_bonus(payload: dict, item_name: str) -> float:
    """Calcola bonus da critical hits per alberi"""
    bonus = 0.0
    if item_name != "Wood":
        return 0.0
    
    farm = payload.get("farm", {})
    trees = farm.get("trees", {})
    
    for plot_id, tree_data in trees.items():
        if not isinstance(tree_data, dict):
            continue
        wood_data = tree_data.get("wood", {})
        critical_hit = wood_data.get("criticalHit", {})
        
        if critical_hit.get("Tough Tree", 0) == 1:
            bonus += 2.0
        if critical_hit.get("Native", 0) == 1:
            bonus += 0.20
        
        break
    
    return bonus

def get_multiplier(payload: dict, item_name: str, item_type: Optional[str] = None, chat_id: Optional[int] = None) -> float:
    """
    Moltiplicatore totale = API base + skill/NFT + swarm/fertilizzante + critical hits
    """
    land_id = _get_land_id_from_api_keys(chat_id)
    if not land_id:
        log.debug("Land ID non trovato")
        return 1.0
    
    # Fetch API
    api_data = _fetch_multipliers_from_api(land_id)
    if not api_data:
        return 1.0
    
    mults = _parse_api_response(api_data)
    
    # Base moltiplicatore
    base_mult = 1.0
    if item_name in mults:
        base_mult = mults[item_name]
    else:
        item_cap = item_name.capitalize()
        if item_cap in mults:
            base_mult = mults[item_cap]
    
    # Bonus skill/NFT
    user_bonus = _get_active_boosts_for_item(payload, item_name)
    
    # Bonus specifici (crop, fruit, tree, mineral)
    specific_bonus = 0.0
    if item_type == "crops":
        specific_bonus = _get_crop_specific_boosts(payload, item_name)
    elif item_type == "fruits":
        specific_bonus = _get_fruit_specific_boosts(payload, item_name)
    elif item_type == "minerals":
        specific_bonus = _get_mineral_critical_bonus(payload, item_type, item_name)
    elif item_type == "trees":
        specific_bonus = _get_tree_critical_bonus(payload, item_name)
    
    # Totale
    total_mult = base_mult + user_bonus + specific_bonus
    
    return max(1.0, total_mult)