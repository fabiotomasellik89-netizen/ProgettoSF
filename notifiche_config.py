# notifiche_config.py - Correzione errori di sintassi
import logging
from typing import Dict

log = logging.getLogger("sflbot")

class NotificheConfig:
    def __init__(self):
        self.item_type_names = {
            "crops": "sono pronte per essere raccolte!",
            "fruits": "sono pronti per essere raccolti!",
            "animals": "sono pronti per essere raccolti!",
            "minerals": "sono pronte per essere estratte!",
            "trees": "è pronto per essere raccolto!",
            "flowers": "sono pronti per essere raccolti!",
            "compost": "è pronto!",
            "cooking": "ha finito di cuocere!",
        }
        
        self.future_item_type_names = {
            "crops": "saranno pronte per essere raccolte!",
            "fruits": "saranno pronti per essere raccolti!",
            "animals": "saranno pronti per essere raccolti!",
            "minerals": "saranno pronte per essere estratte!",
            "trees": "sarà pronto per essere raccolto!",
            "flowers": "saranno pronti per essere raccolti!",
            "compost": "sarà pronto!",
            "cooking": "avrà finito di cuocere!",
        }
        
        self.singular_names = {
            "Chicken": "La gallina",
            "Cow": "La mucca", 
            "Sheep": "La pecora",
            "Bee": "L'ape",
            "Stone": "La pietra",
            "Iron": "Il ferro",
            "Gold": "L'oro",
            "Tree": "L'albero",
        }

    def format_notification(self, item_type: str, item_name: str, quantity: int, 
                          yield_amount: float, currency: str, multiplier: float,
                          progress: str, payload: Dict, is_future: bool = False) -> str:
        """Formatta la notifica esattamente come negli esempi"""
        
        # Scegli il set di nomi corretto (presente o futuro)
        type_names = self.future_item_type_names if is_future else self.item_type_names
        
        # 1. Titolo principale
        if item_name in self.singular_names and quantity == 1:
            if is_future:
                title = f"{self.singular_names[item_name]} sarà pronto per essere raccolto!"
            else:
                title = f"{self.singular_names[item_name]} è pronto per essere raccolto!"
        elif quantity == 1:
            type_phrase = type_names.get(item_type, "è pronto!")
            title = f"{item_name} {type_phrase}"
        else:
            type_phrase = type_names.get(item_type, "sono pronti!")
            title = f"{item_name} {type_phrase}"
        
        # 2. Linea principale con resa e quantità
        total_yield = yield_amount * quantity * multiplier
        if item_type == "trees":
            main_line = f"\n{total_yield:.2f} {currency} from {quantity} trees"
        elif item_type == "animals":
            main_line = f"\n{total_yield:.2f} {currency} from {quantity} {item_name.lower()}s"
        else:
            main_line = f"\n{total_yield:.2f} {item_name} from {quantity} beds"
        
        # 3. Linea del boost
        boost_line = f"x{multiplier:.2f} {progress}"
        
        # 4. Dettagli aggiuntivi (semi, etc.)
        details = self._get_additional_details(payload, item_name)
        
        # Costruisci il messaggio finale
        message = title + main_line + "\n" + boost_line
        
        if details:
            message += "\n\n" + details
        
        return message

    def _get_additional_details(self, payload: Dict, item_name: str) -> str:
        """Aggiunge dettagli come i semi disponibili"""
        try:
            farm = payload.get("farm", {})
            inventory = farm.get("inventory", {})
            
            details = []
            
            # Semi per le colture
            if item_name in ["Sunflower", "Potato", "Pumpkin", "Carrot", "Cabbage", 
                           "Beetroot", "Cauliflower", "Parsnip", "Eggplant", "Corn", 
                           "Radish", "Wheat", "Kale"]:
                seed_name = f"{item_name} Seed"
                seed_count = inventory.get(seed_name, 0)
                if seed_count > 0:
                    details.append(f"{seed_name}: {seed_count}")
            
            # CORREZIONE: Altri dettagli specifici - FIX della sintassi
            if item_name == "Compost Bin":
                buildings = farm.get("buildings", {})  # CORREZIONE: {} invece di []
                compost_bins = buildings.get("Compost Bin", [])  # CORREZIONE: [] per lista
                for bin_data in compost_bins:
                    if isinstance(bin_data, dict):
                        producing = bin_data.get("producing", {})  # CORREZIONE: {} invece di []
                        if producing:
                            # CORREZIONE: Chiudi la stringa con il quote mancante
                            details.append(f"Producing: {producing.get('name', 'Compost')}")
            
            return "\n".join(details)
            
        except Exception as e:
            log.debug(f"Errore nei dettagli aggiuntivi: {e}")
            return ""

# Istanza globale
notifiche_config = NotificheConfig()