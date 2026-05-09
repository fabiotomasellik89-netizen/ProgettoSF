# mutation_storage.py - Persistenza per mutazioni, bee swarm e beehive pieni
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

log = logging.getLogger("sflbot")

_MUTATIONS_FILE = Path("data/mutations_sent.json")

# Assicurati che la directory data/ esista
_MUTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

def _load_mutations() -> dict:
    """Carica il database delle mutazioni/swarm notificate"""
    if not _MUTATIONS_FILE.exists():
        return {
            "mutations": {},      # {farm_id: {animal_id: {"name": "...", "notified_at": timestamp}}}
            "bee_swarm": {},      # {farm_id: {hive_id: {"notified_at": timestamp}}}
            "beehive_full": {}    # {farm_id: {hive_id: {"notified_at": timestamp}}}
        }
    try:
        with open(_MUTATIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Errore caricamento mutations_sent.json: {e}")
        return {"mutations": {}, "bee_swarm": {}, "beehive_full": {}}

def _save_mutations(data: dict) -> None:
    """Salva il database delle mutazioni/swarm notificate"""
    try:
        with open(_MUTATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Errore salvataggio mutations_sent.json: {e}")

# ============================================================================
# MUTAZIONI
# ============================================================================

def mark_mutation_sent(farm_id: str, animal_id: str, mutation_name: str) -> None:
    """Marca una mutazione come già notificata"""
    data = _load_mutations()
    
    farm_id = str(farm_id)
    if farm_id not in data["mutations"]:
        data["mutations"][farm_id] = {}
    
    data["mutations"][farm_id][animal_id] = {
        "name": mutation_name,
        "notified_at": datetime.now().isoformat()
    }
    
    _save_mutations(data)
    log.info(f"Mutazione salvata: {mutation_name} per animale {animal_id} (farm {farm_id})")

def is_mutation_sent(farm_id: str, animal_id: str) -> bool:
    """Controlla se una mutazione è già stata notificata"""
    data = _load_mutations()
    farm_id = str(farm_id)
    return animal_id in data["mutations"].get(farm_id, {})

def get_sent_mutations(farm_id: str) -> dict:
    """Ottieni tutte le mutazioni notificate per una farm"""
    data = _load_mutations()
    return data["mutations"].get(str(farm_id), {})

def clear_mutation(farm_id: str, animal_id: str) -> bool:
    """Rimuovi una mutazione dal registro (quando viene raccolta)"""
    data = _load_mutations()
    farm_id = str(farm_id)
    
    if farm_id in data["mutations"] and animal_id in data["mutations"][farm_id]:
        del data["mutations"][farm_id][animal_id]
        _save_mutations(data)
        log.info(f"Mutazione rimossa per animale {animal_id} (farm {farm_id})")
        return True
    return False

# ============================================================================
# BEE SWARM (con timeout 10 minuti)
# ============================================================================

def mark_bee_swarm_sent(farm_id: str, hive_id: str) -> None:
    """Marca uno swarm come già notificato"""
    data = _load_mutations()
    
    farm_id = str(farm_id)
    if farm_id not in data["bee_swarm"]:
        data["bee_swarm"][farm_id] = {}
    
    data["bee_swarm"][farm_id][hive_id] = {
        "notified_at": datetime.now().isoformat()
    }
    
    _save_mutations(data)
    log.info(f"Bee swarm salvato per hive {hive_id} (farm {farm_id})")

def is_bee_swarm_sent(farm_id: str, hive_id: str) -> bool:
    """
    Controlla se uno swarm è già stato notificato (SENZA timeout)
    Una volta notificato, non notifica più per quello swarm.
    Il dato è persistente e sopravvive ai riavvii del bot.
    """
    data = _load_mutations()
    farm_id = str(farm_id)
    
    if farm_id not in data["bee_swarm"]:
        return False
    
    return hive_id in data["bee_swarm"][farm_id]

# ============================================================================
# BEEHIVE FULL (notifica una sola volta)
# ============================================================================

def mark_beehive_full_sent(farm_id: str, hive_id: str) -> None:
    """Marca un beehive pieno come già notificato"""
    data = _load_mutations()
    
    farm_id = str(farm_id)
    if farm_id not in data["beehive_full"]:
        data["beehive_full"][farm_id] = {}
    
    data["beehive_full"][farm_id][hive_id] = {
        "notified_at": datetime.now().isoformat()
    }
    
    _save_mutations(data)
    log.info(f"Beehive pieno salvato per hive {hive_id} (farm {farm_id})")

def is_beehive_full_sent(farm_id: str, hive_id: str, timeout_hours: int = 24) -> bool:
    """
    Controlla se un beehive pieno è già stato notificato di recente
    
    Args:
        farm_id: ID della farm
        hive_id: ID dell'alveare
        timeout_hours: Ore prima di poter notificare di nuovo (default: 24)
    
    Returns:
        True se è stato notificato di recente, False altrimenti
    """
    data = _load_mutations()
    farm_id = str(farm_id)
    
    if farm_id not in data["beehive_full"] or hive_id not in data["beehive_full"][farm_id]:
        return False
    
    notified_at_str = data["beehive_full"][farm_id][hive_id].get("notified_at")
    if not notified_at_str:
        return False
    
    try:
        notified_at = datetime.fromisoformat(notified_at_str)
        time_passed = datetime.now() - notified_at
        
        # Se sono passate più di timeout_hours, può essere notificato di nuovo
        if time_passed > timedelta(hours=timeout_hours):
            return False
        
        return True
    except Exception as e:
        log.error(f"Errore parsing data beehive: {e}")
        return False

def clear_beehive_full(farm_id: str, hive_id: str) -> bool:
    """Rimuovi un beehive dal registro (quando viene svuotato)"""
    data = _load_mutations()
    farm_id = str(farm_id)
    
    if farm_id in data["beehive_full"] and hive_id in data["beehive_full"][farm_id]:
        del data["beehive_full"][farm_id][hive_id]
        _save_mutations(data)
        log.info(f"Beehive pieno rimosso per hive {hive_id} (farm {farm_id})")
        return True
    return False

def get_sent_beehive_full(farm_id: str) -> dict:
    """Ottieni tutti i beehive pieni notificati per una farm"""
    data = _load_mutations()
    return data["beehive_full"].get(str(farm_id), {})

# ============================================================================
# PULIZIA AUTOMATICA
# ============================================================================

def cleanup_old_entries(days: int = 7) -> None:
    """
    Rimuove entry più vecchie di N giorni
    
    Args:
        days: Giorni di retention (default: 7)
    """
    data = _load_mutations()
    cutoff = datetime.now() - timedelta(days=days)
    changed = False
    
    # Cleanup mutazioni
    for farm_id in list(data["mutations"].keys()):
        for animal_id in list(data["mutations"][farm_id].keys()):
            notified_at_str = data["mutations"][farm_id][animal_id].get("notified_at")
            if notified_at_str:
                try:
                    notified_at = datetime.fromisoformat(notified_at_str)
                    if notified_at < cutoff:
                        del data["mutations"][farm_id][animal_id]
                        changed = True
                except Exception:
                    pass
        # Rimuovi farm vuote
        if not data["mutations"][farm_id]:
            del data["mutations"][farm_id]
    
    # Cleanup bee swarm
    for farm_id in list(data["bee_swarm"].keys()):
        for hive_id in list(data["bee_swarm"][farm_id].keys()):
            notified_at_str = data["bee_swarm"][farm_id][hive_id].get("notified_at")
            if notified_at_str:
                try:
                    notified_at = datetime.fromisoformat(notified_at_str)
                    if notified_at < cutoff:
                        del data["bee_swarm"][farm_id][hive_id]
                        changed = True
                except Exception:
                    pass
        if not data["bee_swarm"][farm_id]:
            del data["bee_swarm"][farm_id]
    
    # Cleanup beehive full
    for farm_id in list(data["beehive_full"].keys()):
        for hive_id in list(data["beehive_full"][farm_id].keys()):
            notified_at_str = data["beehive_full"][farm_id][hive_id].get("notified_at")
            if notified_at_str:
                try:
                    notified_at = datetime.fromisoformat(notified_at_str)
                    if notified_at < cutoff:
                        del data["beehive_full"][farm_id][hive_id]
                        changed = True
                except Exception:
                    pass
        if not data["beehive_full"][farm_id]:
            del data["beehive_full"][farm_id]
    
    if changed:
        _save_mutations(data)
        log.info(f"Cleanup completato: rimossi entry più vecchi di {days} giorni")

# ============================================================================
# UTILITY PER DEBUG
# ============================================================================

def get_all_stats() -> dict:
    """Ottieni statistiche complete su tutte le notifiche salvate"""
    data = _load_mutations()
    
    stats = {
        "total_mutations": sum(len(v) for v in data["mutations"].values()),
        "total_swarms": sum(len(v) for v in data["bee_swarm"].values()),
        "total_full_beehives": sum(len(v) for v in data["beehive_full"].values()),
        "farms_tracked": len(set(
            list(data["mutations"].keys()) + 
            list(data["bee_swarm"].keys()) + 
            list(data["beehive_full"].keys())
        ))
    }
    
    return stats