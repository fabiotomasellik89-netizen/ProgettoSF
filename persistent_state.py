# persistent_state.py - Gestione persistente dello stato di swarm e mutazioni per land_id
import json
import logging
import os
from typing import Dict, Set, List, Tuple
from datetime import datetime, timezone

log = logging.getLogger("sflbot")

STATE_FILE = "swarm_mutations_state.json"

def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)

class PersistentStateManager:
    """
    Gestisce lo stato persistente di swarm e mutazioni per ogni land_id.
    
    Salva su file JSON in formato:
    {
        "land_id_1": {
            "bee_swarm": {
                "hive_id_1": timestamp_ms,
                "hive_id_2": timestamp_ms,
                ...
            },
            "mutations": {
                "mutation_key_1": timestamp_ms,
                "mutation_key_2": timestamp_ms,
                ...
            }
        },
        "land_id_2": { ... }
    }
    """
    
    def __init__(self, filename: str = STATE_FILE):
        self.filename = filename
        self._data: Dict[str, Dict[str, Dict[str, int]]] = {}
        self._load()
    
    def _load(self):
        """Carica lo stato dal file JSON"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                log.info(f"Stato persistente caricato da {self.filename}")
            else:
                self._data = {}
                log.info(f"File {self.filename} non esiste, stato iniziale vuoto")
        except Exception as e:
            log.error(f"Errore caricamento stato persistente: {e}")
            self._data = {}
    
    def _save(self):
        """Salva lo stato su file JSON"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            log.debug(f"Stato persistente salvato in {self.filename}")
        except Exception as e:
            log.error(f"Errore salvataggio stato persistente: {e}")
    
    def _ensure_land(self, land_id: str):
        """Assicura che la land_id esista nella struttura dati"""
        if land_id not in self._data:
            self._data[land_id] = {
                "bee_swarm": {},
                "mutations": {}
            }
    
    def mark_bee_swarm_notified(self, land_id: str, hive_id: str):
        """Marca un bee swarm come notificato per una land_id"""
        self._ensure_land(land_id)
        self._data[land_id]["bee_swarm"][hive_id] = _now_ms()
        self._save()
        log.debug(f"Bee swarm marcato per {land_id}/{hive_id}")
    
    def is_bee_swarm_notified(self, land_id: str, hive_id: str) -> bool:
        """Controlla se un bee swarm è stato già notificato per una land_id"""
        self._ensure_land(land_id)
        return hive_id in self._data[land_id]["bee_swarm"]
    
    def mark_mutation_notified(self, land_id: str, mutation_key: str):
        """Marca una mutazione come notificata per una land_id"""
        self._ensure_land(land_id)
        self._data[land_id]["mutations"][mutation_key] = _now_ms()
        self._save()
        log.debug(f"Mutazione marcata per {land_id}/{mutation_key}")
    
    def is_mutation_notified(self, land_id: str, mutation_key: str) -> bool:
        """Controlla se una mutazione è stata già notificata per una land_id"""
        self._ensure_land(land_id)
        return mutation_key in self._data[land_id]["mutations"]
    
    def get_notified_swarms(self, land_id: str) -> Set[str]:
        """Ritorna l'insieme dei hive_id già notificati per una land_id"""
        self._ensure_land(land_id)
        return set(self._data[land_id]["bee_swarm"].keys())
    
    def get_notified_mutations(self, land_id: str) -> Set[str]:
        """Ritorna l'insieme delle mutation keys già notificate per una land_id"""
        self._ensure_land(land_id)
        return set(self._data[land_id]["mutations"].keys())
    
    def clear_land_state(self, land_id: str):
        """Cancella completamente lo stato per una land_id"""
        if land_id in self._data:
            del self._data[land_id]
            self._save()
            log.info(f"Stato cancellato per {land_id}")
    
    def get_state_summary(self, land_id: str) -> Dict:
        """Ritorna un riassunto dello stato per una land_id"""
        self._ensure_land(land_id)
        return {
            "bee_swarm_count": len(self._data[land_id]["bee_swarm"]),
            "mutations_count": len(self._data[land_id]["mutations"]),
            "bee_swarm": self._data[land_id]["bee_swarm"],
            "mutations": self._data[land_id]["mutations"]
        }
        
def load_state(key: str) -> Dict:
    """Carica stato generico da file JSON"""
    filename = f"{key}.json"
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        log.error(f"Errore caricamento stato {key}: {e}")
    return {}

def save_state(key: str, data: Dict):
    """Salva stato generico su file JSON"""
    filename = f"{key}.json"
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Errore salvataggio stato {key}: {e}")        


# Istanza globale
_persistent_state: PersistentStateManager | None = None

def get_persistent_state() -> PersistentStateManager:
    """Ritorna l'istanza globale del manager di stato persistente"""
    global _persistent_state
    if _persistent_state is None:
        _persistent_state = PersistentStateManager()
    return _persistent_state


__all__ = [
    "PersistentStateManager",
    "get_persistent_state"
]