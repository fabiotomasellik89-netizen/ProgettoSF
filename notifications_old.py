# notifications.py - Sistema notifiche CORRETTO con Bee Swarm Fix
import asyncio
import time
import logging
from typing import Callable, Iterable, Dict, List, Tuple

from api import fetch_farm_with_user_key
from notify_format import render_line

log = logging.getLogger("sflbot")

# Costanti
PRE_NOTICE_SECONDS = 120           # notifica 1 minuto prima
API_MIN_REFRESH_SECONDS = 15 * 60  # refresh API ogni 15 minuti

ItemRow = Tuple[str, str, float, int]  # (type, name, count, time_left_ms)

def _now_ms() -> int: 
    return int(time.time() * 1000)

class NotificationManager:
    def __init__(self, chat_ids: Iterable[int], farm_id: str, bot_send: Callable[[int, str], asyncio.Future]):
        self.chat_ids = list(chat_ids)
        self.farm_id = str(farm_id)
        self.bot_send = bot_send
        self._timer_task: asyncio.Task | None = None
        self._last_payload: Dict | None = None
        self._last_fetch_ts: float = 0.0
        self._sent_keys: set[tuple] = set()  # anti-duplicazione
        self.is_running = False
        self._check_interval = 60  # Check ogni minuto

    async def start(self) -> None:
        """Avvia il sistema di notifiche"""
        if self.is_running:
            log.warning(f"Manager già in esecuzione per farm {self.farm_id}")
            return
            
        self.is_running = True
        log.info(f"Avvio NotificationManager per farm {self.farm_id} con {len(self.chat_ids)} chat")
        
        try:
            # Carica payload iniziale
            await self._ensure_payload(force=True)
            log.info(f"Payload iniziale caricato per farm {self.farm_id}")
        except Exception as e:
            log.error(f"Errore caricamento payload iniziale per farm {self.farm_id}: {e}")
            # Continua comunque, riproverà al prossimo check
        
        # Avvia loop notifiche
        self._timer_task = asyncio.create_task(self._notification_loop())

    async def stop(self) -> None:
        """Ferma il sistema di notifiche"""
        self.is_running = False
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
        self._timer_task = None
        log.info(f"NotificationManager fermato per farm {self.farm_id}")

    async def _notification_loop(self) -> None:
        """Loop principale delle notifiche"""
        while self.is_running:
            try:
                # Aspetta intervallo
                await asyncio.sleep(self._check_interval)
                
                if not self.is_running:
                    break
                
                # Carica dati aggiornati
                try:
                    payload = await self._ensure_payload(force=False)
                except Exception as e:
                    log.error(f"Errore fetch payload per farm {self.farm_id}: {e}")
                    continue
                
                # Controlla item pronti
                now_ms = _now_ms()
                items = self._eligible_items(payload, now_ms)
                
                if items:
                    log.info(f"Farm {self.farm_id}: trovati {len(items)} item da notificare")
                    await self._notify(items, payload)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Errore nel loop notifiche per farm {self.farm_id}: {e}")
                # Continua comunque dopo errore

    async def _ensure_payload(self, force: bool = False) -> Dict:
        """Carica payload con cache"""
        now = time.time()
        
        # Usa cache se disponibile e non scaduta
        if not force and self._last_payload and (now - self._last_fetch_ts < API_MIN_REFRESH_SECONDS):
            return self._last_payload
        
        try:
            # Usa il primo chat_id disponibile per recuperare l'API key
            chat_id = self.chat_ids[0] if self.chat_ids else None
            log.debug(f"🔍 _ensure_payload: farm={self.farm_id}, chat_id={chat_id}, force={force}")
            
            if not chat_id:
                raise ValueError("Nessun chat_id disponibile per le notifiche")
            
            # fetch_farm è async e ritorna (payload, url, now_ms)
            log.debug(f"🔍 Chiamata fetch_farm_with_user_key({self.farm_id}, {chat_id}, force={force})")
            payload, _, _ = await fetch_farm_with_user_key(self.farm_id, chat_id, force=force)
            
            self._last_payload = payload
            self._last_fetch_ts = now
            log.debug(f"✅ Payload caricato per farm {self.farm_id}")
            return payload
        except Exception as e:
            log.error(f"Errore fetch farm {self.farm_id}: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            # Usa cache se disponibile anche se vecchia
            if self._last_payload:
                log.warning(f"Usando cache vecchia per farm {self.farm_id}")
                return self._last_payload
            # Altrimenti ritorna dict vuoto
            return {"farm": {}}

    def _gather_listings(self, payload: Dict, now_ms: int) -> Dict[str, List[Tuple[str, float, int]]]:
        """
        Raccoglie tutti gli item da varie categorie.
        Ritorna: {tipo: [(nome, count, ready_ms), ...]}
        """
        # Importa le funzioni helper da tempo.py
        try:
            from tempo import (
                _future_crops, _future_fruit, _future_cooking,
                _future_compost, _future_animals, _future_minerals,
                _future_trees, _future_flowers
            )
        except ImportError as e:
            log.error(f"Impossibile importare funzioni da tempo.py: {e}")
            return {}
        
        def convert_rows(rows: List[Tuple[int, str]]) -> List[Tuple[str, float, int]]:
            """Converte da (ready_ms, name) a (name, count, ready_ms) con aggregazione MIGLIORATA"""
            grouped = {}
            for ready_ms, name in rows:
                # Raggruppa per nome E finestra di 5 minuti (non 1 minuto)
                time_bucket = ready_ms // 300000  # 5 minuti = 300000ms
                key = (name, time_bucket)
                
                if key not in grouped:
                    grouped[key] = {"name": name, "count": 0, "min_ready_ms": ready_ms}
                
                grouped[key]["count"] += 1
                # Mantieni il tempo del primo item
                if ready_ms < grouped[key]["min_ready_ms"]:
                    grouped[key]["min_ready_ms"] = ready_ms
            
            # Converti in formato richiesto
            result = []
            for data in grouped.values():
                result.append((data["name"], data["count"], data["min_ready_ms"]))
            
            return result
        
        # Controlla mutazioni animali
        mutations = self._check_animal_mutations(payload)
        
        # Controlla bee swarm attivi
        bee_swarm = self._check_bee_swarm(payload)
        
        # Controlla beehive pieni
        beehive_full = self._check_beehive_full(payload)
        
        return {
            "crops": convert_rows(_future_crops(payload, now_ms)),
            "fruits": convert_rows(_future_fruit(payload, now_ms)),
            "compost": convert_rows(_future_compost(payload, now_ms)),
            "animals": convert_rows(_future_animals(payload, now_ms)),
            "cooking": convert_rows(_future_cooking(payload, now_ms)),
            "minerals": convert_rows(_future_minerals(payload, now_ms)),
            "trees": convert_rows(_future_trees(payload, now_ms)),
            "flowers": convert_rows(_future_flowers(payload, now_ms)),
            "mutations": mutations,  # Aggiungi mutazioni
            "bee_swarm": bee_swarm,  # Aggiungi bee swarm
            "beehives": beehive_full,  # Aggiungi beehive pieni
        }

    def _check_animal_mutations(self, payload: Dict) -> List[Tuple[str, float, int]]:
        """
        Controlla se ci sono animali con mutazioni (campo 'reward' presente).
        Ritorna lista di tuple (nome_mutazione, count, now_ms)
        USA STORAGE PERSISTENTE per evitare duplicati dopo riavvio
        """
        from mutation_storage import is_mutation_sent, mark_mutation_sent
        
        mutations = []
        farm = payload.get("farm", {})
        
        # Controlla henHouse (polli)
        hen_house = farm.get("henHouse", {})
        if isinstance(hen_house, dict):
            animals = hen_house.get("animals", {})
            if isinstance(animals, dict):
                for animal_id, animal_data in animals.items():
                    if isinstance(animal_data, dict):
                        reward = animal_data.get("reward")
                        if reward and isinstance(reward, dict):
                            items = reward.get("items", [])
                            for item in items:
                                if isinstance(item, dict):
                                    mutation_name = item.get("name", "Mutazione Pollo")
                                    
                                    # USA STORAGE PERSISTENTE
                                    if not is_mutation_sent(self.farm_id, animal_id):
                                        mutations.append((mutation_name, 1, _now_ms()))
                                        mark_mutation_sent(self.farm_id, animal_id, mutation_name)
                                        log.info(f"✅ NUOVA MUTAZIONE: {mutation_name} per animale {animal_id}")
        
        # Controlla barn (mucche e pecore)
        barn = farm.get("barn", {})
        if isinstance(barn, dict):
            animals = barn.get("animals", {})
            if isinstance(animals, dict):
                for animal_id, animal_data in animals.items():
                    if isinstance(animal_data, dict):
                        reward = animal_data.get("reward")
                        if reward and isinstance(reward, dict):
                            items = reward.get("items", [])
                            for item in items:
                                if isinstance(item, dict):
                                    mutation_name = item.get("name", "Mutazione Animale")
                                    
                                    # USA STORAGE PERSISTENTE
                                    if not is_mutation_sent(self.farm_id, animal_id):
                                        mutations.append((mutation_name, 1, _now_ms()))
                                        mark_mutation_sent(self.farm_id, animal_id, mutation_name)
                                        log.info(f"✅ NUOVA MUTAZIONE: {mutation_name} per animale {animal_id}")
                                        
        # Controlla flowerBeds (fiori)
        flowers_data = farm.get("flowers", {})
        if isinstance(flowers_data, dict):
            flower_beds = flowers_data.get("flowerBeds", {})
            if isinstance(flower_beds, dict):
                for bed_id, bed_data in flower_beds.items():
                    if isinstance(bed_data, dict):
                        flower = bed_data.get("flower", {})
                        if isinstance(flower, dict):
                            reward = flower.get("reward")
                            if reward and isinstance(reward, dict):
                                items = reward.get("items", [])
                                for item in items:
                                    if isinstance(item, dict):
                                        mutation_name = item.get("name", "Mutazione Fiore")
                                        
                                        # USA STORAGE PERSISTENTE
                                        if not is_mutation_sent(self.farm_id, bed_id):
                                            mutations.append((mutation_name, 1, _now_ms()))
                                            mark_mutation_sent(self.farm_id, bed_id, mutation_name)
                                            log.info(f"✅ NUOVA MUTAZIONE: {mutation_name} per fiore {bed_id}")
        
        return mutations
        

    def _check_bee_swarm(self, payload: Dict) -> List[Tuple[str, float, int]]:
        """
        Controlla se ci sono beehive con swarm attivo.
        Ritorna lista di tuple (nome_swarm, count, now_ms)
        USA STORAGE PERSISTENTE con timeout 10 minuti
        """
        from mutation_storage import is_bee_swarm_sent, mark_bee_swarm_sent
        
        swarm_beehives = []
        farm = payload.get("farm", {})
        beehives = farm.get("beehives", {})
        
        if not isinstance(beehives, dict):
            return swarm_beehives
        
        for hive_id, hive_data in beehives.items():
            if not isinstance(hive_data, dict):
                continue
            
            swarm = hive_data.get("swarm")
            if not swarm or not isinstance(swarm, dict):
                continue
            
            # Swarm presente e attivo
            flowers = hive_data.get("flowers", [])
            if not flowers or not isinstance(flowers, list):
                continue
            
            # Determina il tipo di swarm basandosi sui fiori
            flower_name = flowers[0].get("name", "") if len(flowers) > 0 else ""
            swarm_name = f"🐝 Swarm attivo su {flower_name}!" if flower_name else "🐝 Bee Swarm attivo!"
            
            # Controlla se è già stato notificato (timeout 10 minuti)
            if not is_bee_swarm_sent(self.farm_id, hive_id):
                swarm_beehives.append((swarm_name, 1, _now_ms()))
                mark_bee_swarm_sent(self.farm_id, hive_id)
                log.info(f"✅ NUOVO BEE SWARM: {swarm_name} per beehive {hive_id}")
        
        return swarm_beehives

    def _check_beehive_full(self, payload: Dict) -> List[Tuple[str, float, int]]:
        """
        Controlla se ci sono beehive che hanno raggiunto >= 98% capacità.
        Ritorna lista di tuple (nome_hive, count, now_ms)
        """
        full_beehives = []
        farm = payload.get("farm", {})
        beehives = farm.get("beehives", {})
        
        if not isinstance(beehives, dict):
            return full_beehives
        
        for hive_id, hive_data in beehives.items():
            if not isinstance(hive_data, dict):
                continue
            
            # Calcola capacità
            honey = hive_data.get("honey", {})
            if not isinstance(honey, dict):
                continue
            
            updatedAt = honey.get("updatedAt", 0)
            if updatedAt == 0:
                continue
            
            # Calcola miele accumulato
            now_ms = _now_ms()
            time_elapsed_hours = (now_ms - updatedAt) / (1000 * 60 * 60)
            
            # Rate: 0.5 honey per ora per flower
            flowers = hive_data.get("flowers", [])
            if not flowers or not isinstance(flowers, list):
                continue
            
            production_rate = len(flowers) * 0.5  # honey/ora
            produced_honey = time_elapsed_hours * production_rate
            
            # Capacità massima: 10 * numero di fiori
            max_capacity = len(flowers) * 10
            current_honey = produced_honey
            
            # Soglia 98%
            if current_honey >= (max_capacity * 0.98):
                # Anti-duplicazione: notifica solo se non già inviata negli ultimi 30 minuti
                key = ("beehive_full", hive_id, now_ms // 1800000)  # bucket 30 min
                if key not in self._sent_keys:
                    hive_name = f"🍯 Beehive {hive_id[-4:]} al {int((current_honey/max_capacity)*100)}%"
                    full_beehives.append((hive_name, 1, now_ms))
                    self._sent_keys.add(key)
                    log.info(f"✅ BEEHIVE PIENO: {hive_name}")
        
        return full_beehives

    def _eligible_items(self, payload: Dict, now_ms: int) -> List[ItemRow]:
        """
        Determina quali items sono eligibili per notifica.
        
        Ritorna: Lista di tuple (type, name, count, time_left_ms)
                 SOLO items con 0 < time_left <= PRE_NOTICE_SECONDS
        
        NOTE:
        - Bee swarm, mutazioni, beehive pieni hanno time_left=0 (notifica immediata)
        - Altri items hanno time_left nel range (0, PRE_NOTICE_SECONDS*1000]
        - Items con time_left <= 0 (già pronti) NON vengono inclusi
        """
        listings = self._gather_listings(payload, now_ms)
        
        # Raggruppa items per categoria+nome+bucket temporale
        pre_grouped: Dict[tuple, dict] = {}
        
        # 1. Raccogli items con PRE-ALERT (SOLO FUTURI, non già pronti)
        for item_type, rows in listings.items():
            # Bee swarm, mutazioni, beehive pieni gestiti separatamente
            if item_type in ("mutations", "bee_swarm", "beehives"):
                continue  # Gestite separatamente sotto
            
            for (name, count, ready_at_ms) in rows:
                time_left_ms = ready_at_ms - now_ms
                
                # ⚠️ CRITICO: Solo items FUTURI entro la finestra di notifica
                # NON notificare se time_left_ms <= 0 (già pronto)
                if 30000 < time_left_ms <= PRE_NOTICE_SECONDS * 1000:
                    # Chiave per raggruppamento: tipo + nome + bucket temporale 5min
                    time_bucket = ready_at_ms // 300000  # 5 minuti
                    key = (item_type, name, time_bucket)
                    
                    if key not in pre_grouped:
                        pre_grouped[key] = {
                            "type": item_type,
                            "name": name,
                            "count": 0,
                            "min_time_left": time_left_ms,
                            "min_ready": ready_at_ms
                        }
                    
                    # Accumula count
                    pre_grouped[key]["count"] += count
                    # Mantieni il tempo minore
                    if time_left_ms < pre_grouped[key]["min_time_left"]:
                        pre_grouped[key]["min_time_left"] = time_left_ms
        
        # Converti in output format
        out: List[ItemRow] = []
        
        # 1. Aggiungi bee swarm (PRIORITÀ MASSIMA - notifica immediata)
        bee_swarm = listings.get("bee_swarm", [])
        log.debug(f"Bee swarm trovati in listings: {len(bee_swarm)}")
        for (swarm_name, count, detected_ms) in bee_swarm:
            log.info(f"➡️ Aggiungendo notifica bee swarm: {swarm_name}")
            out.append(("bee_swarm", swarm_name, float(count), 0))
        
        # 2. Aggiungi mutazioni (priorità alta - notifica immediata)
        mutations = listings.get("mutations", [])
        for (mutation_name, count, detected_ms) in mutations:
            log.info(f"➡️ Aggiungendo notifica mutazione: {mutation_name}")
            out.append(("mutation", mutation_name, float(count), 0))
        
        # 3. Aggiungi beehive pieni (notifica immediata)
        beehives = listings.get("beehives", [])
        for (hive_name, count, detected_ms) in beehives:
            log.info(f"➡️ Aggiungendo notifica beehive pieno: {hive_name}")
            out.append(("beehives", hive_name, float(count), 0))
        
        # 4. Aggiungi items raggruppati (SOLO PRE-ALERT, non già pronti)
        for data in pre_grouped.values():
            # Anti-duplicazione finale
            final_key = (data["type"], data["name"], data["min_ready"] // 60000)
            if final_key in self._sent_keys:
                continue
            
            log.debug(f"➡️ PRE-ALERT: {data['name']} tra {data['min_time_left']//1000}s")
            
            out.append((
                data["type"], 
                data["name"], 
                float(data["count"]), 
                data["min_time_left"]
            ))
        
        log.debug(f"Eligible items totali: {len(out)} (bee_swarm: {len(bee_swarm)}, mutations: {len(mutations)})")
        out.sort(key=lambda t: t[3])  # Ordina per tempo rimanente
        return out

    def _build_title(self, items: List[ItemRow]) -> str:
        """Costruisce il titolo della notifica"""
        # Controlla se ci sono bee swarm (priorità altissima)
        bee_swarm = [it for it in items if it[0] == "bee_swarm"]
        if bee_swarm:
            if len(bee_swarm) == 1:
                return f"🐝 Bee Swarm attivo!"
            return f"🐝 {len(bee_swarm)} Bee Swarm attivi!"
        
        # Controlla se ci sono mutazioni
        mutations = [it for it in items if it[0] == "mutation"]
        if mutations:
            if len(mutations) == 1:
                return f"🧬 Nuova mutazione in arrivo: {mutations[0][1]}!"
            return f"🧬 {len(mutations)} nuove mutazioni in arrivo!"
        
        # Titolo normale per item con countdown
        eta_ms = min((it[3] for it in items))
        eta_str = self._fmt_eta(eta_ms)
        
        if len(items) == 1:
            item_type, name, cnt, _ = items[0]
            # Mappa emoticon per tipo
            emoji_map = {
                "crops": "🌱",
                "fruits": "🍎", 
                "animals": "🐾",
                "cooking": "👨‍🍳",
                "compost": "♻️",
                "minerals": "⛏️",
                "trees": "🌳",
                "flowers": "🌼",
                "beehives": "🍯"
            }
            
            # Se è un'ape (Bee nel nome), usa 🐝
            if "Bee" in name:
                emoji = "🐝"
            else:
                emoji = emoji_map.get(item_type, "⏰")
            
            count = int(cnt)
            if count > 1:
                return f"{emoji} {count} {name} pronto tra {eta_str}!"
        else:
            return f"{emoji} {name} pronto tra {eta_str}!"
        
        return f"⏰ {len(items)} risorse saranno pronte tra {eta_str}!"

    @staticmethod
    def _fmt_eta(ms_left: int) -> str:
        """Formatta ETA in modo leggibile"""
        secs = max(0, ms_left // 1000)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h: 
            return f"{h}h {m}m"
        if m: 
            return f"{m}m {s}s" if s else f"{m}m"
        return f"{s}s"

    async def _notify(self, items: List[ItemRow], payload: Dict) -> None:
        """Invia notifiche con formattazione migliorata"""
        # Marca come inviati (solo per item normali, mutazioni già marcate)
        for (item_type, name, _cnt, _tl) in items:
            if item_type in ("mutation", "bee_swarm"):
                continue  # Già gestite nei check specifici
            for (_n, _count, ready_at_ms) in self._gather_listings(payload, _now_ms()).get(item_type, []):
                if _n == name:
                    self._sent_keys.add((item_type, name, ready_at_ms // 300000))
                    break

        # Costruisci messaggio con nuovo formato
        from notify_format import render_line
        
        title = self._build_title(items)
        
        # Raggruppa per categoria
        by_category = {}
        for (item_type, name, cnt, _tl) in items:
            if item_type not in by_category:
                by_category[item_type] = []
            by_category[item_type].append((name, cnt))
        
        # Per mutazioni e bee_swarm: SOLO il titolo (già completo)
        if len(by_category) == 1 and list(by_category.keys())[0] in ("mutation", "bee_swarm"):
            message = title
        else:
            # Per altri items o mix: aggiungi dettagli
            lines = []
            
            # Ordine categorie (bee_swarm prima di mutation per priorità)
            category_order = ["bee_swarm", "mutation", "crops", "fruits", "animals", "cooking", "compost", "minerals", "trees", "flowers"]
            
            for category in category_order:
                if category not in by_category:
                    continue
                
                items_in_category = by_category[category]
                
                # Titolo categoria (solo se più di una categoria)
                if len(by_category) > 1:
                    category_names = {
                        "bee_swarm": "🐝 *Bee Swarm*",
                        "crops": "🌱 *Colture*",
                        "fruits": "🎃 *Frutta*", 
                        "animals": "🐾 *Animali*",
                        "cooking": "👨‍🍳 *Cucina*",
                        "compost": "♻️ *Compost*",
                        "minerals": "⛏️ *Minerali*",
                        "trees": "🌳 *Alberi*",
                        "flowers": "🌼 *Fiori*",
                        "mutation": "🧬 *Mutazioni*"
                    }
                    lines.append(category_names.get(category, category.title()))
                
                # Items della categoria
                for name, cnt in items_in_category:
                    if category == "bee_swarm":
                        lines.append(f"  {name}")  # Il nome già contiene emoji e testo
                    elif category == "mutation":
                        lines.append(f"  {name}")  # Nome mutazione già nel titolo
                    else:
                        lines.append(render_line(payload, category, name, cnt))
                
                # Riga vuota tra categorie (solo se più di una)
                if len(by_category) > 1:
                    lines.append("")
            
            message = title + "\n\n" + "\n".join(lines).strip()

        for chat_id in self.chat_ids:
            try:
                await self.bot_send(chat_id, message)
                log.info(f"Notifica inviata a chat {chat_id} per farm {self.farm_id}")
            except Exception as e:
                log.error(f"Errore invio notifica a chat {chat_id}: {e}")