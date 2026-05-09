# stats_tracker.py - Sistema snapshot all'1 di notte (semplificato)
import asyncio
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Dict

from farm_delta_24h import save_daily_snapshot, cleanup_old_snapshots

log = logging.getLogger("sflbot")
TZ = ZoneInfo("Europe/Rome")

class DailySnapshotScheduler:
    """Salva snapshot giornaliero all'1:00 di notte"""
    
    def __init__(self, farm_id: str, chat_id: int):
        self.farm_id = str(farm_id)
        self.chat_id = chat_id
        self.is_running = False
        self._task: asyncio.Task | None = None
    
    async def start(self) -> None:
        """Avvia lo scheduler"""
        if self.is_running:
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._daily_loop())
        log.info(f"📸 Scheduler snapshot avviato per farm {self.farm_id}")
    
    async def stop(self) -> None:
        """Ferma lo scheduler"""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info(f"📸 Scheduler snapshot fermato per farm {self.farm_id}")
    
    async def _daily_loop(self) -> None:
        """Loop principale: attende fino all'1:00 ogni giorno"""
        while self.is_running:
            try:
                # Calcola tempo fino all'1:00 di notte
                now = datetime.now(TZ)
                
                # Prossimo 1:00 (oggi o domani)
                next_snapshot = now.replace(hour=1, minute=0, second=0, microsecond=0)
                
                # Se è già passata l'1:00 oggi, vai a domani
                if now >= next_snapshot:
                    from datetime import timedelta
                    next_snapshot += timedelta(days=1)
                
                # Calcola secondi di attesa
                wait_seconds = (next_snapshot - now).total_seconds()
                
                hours_wait = wait_seconds / 3600
                log.info(f"⏰ Prossimo snapshot tra {hours_wait:.1f}h (alle {next_snapshot.strftime('%H:%M')})")
                
                # Aspetta fino all'1:00
                await asyncio.sleep(wait_seconds)
                
                if not self.is_running:
                    break
                
                # Salva snapshot
                await self._take_snapshot()
                
                # Pulisci vecchi snapshot (mantieni 7 giorni)
                cleanup_old_snapshots(self.farm_id, keep_days=7)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Errore nel loop snapshot per farm {self.farm_id}: {e}")
                # Riprova dopo 5 minuti in caso di errore
                await asyncio.sleep(300)
    
    async def _take_snapshot(self) -> None:
        """Salva lo snapshot giornaliero"""
        try:
            from api import fetch_farm_with_user_key
            
            # Fetch payload corrente
            payload, _, _ = await fetch_farm_with_user_key(self.farm_id, self.chat_id, force=True)
            
            # Salva snapshot
            save_daily_snapshot(self.farm_id, payload)
            
            log.info(f"✅ Snapshot giornaliero salvato per farm {self.farm_id}")
            
        except Exception as e:
            log.error(f"Errore salvataggio snapshot per farm {self.farm_id}: {e}")

# ============================================================================
# MANAGER GLOBALE
# ============================================================================

_schedulers: Dict[str, DailySnapshotScheduler] = {}

async def start_tracker_for_farm(farm_id: str, chat_id: int) -> None:
    """Avvia scheduler snapshot per una farm"""
    farm_id = str(farm_id)
    
    if farm_id in _schedulers:
        log.debug(f"Scheduler già attivo per farm {farm_id}")
        return
    
    scheduler = DailySnapshotScheduler(farm_id, chat_id)
    await scheduler.start()
    _schedulers[farm_id] = scheduler

async def stop_tracker_for_farm(farm_id: str) -> None:
    """Ferma scheduler per una farm"""
    farm_id = str(farm_id)
    
    if farm_id in _schedulers:
        await _schedulers[farm_id].stop()
        del _schedulers[farm_id]

async def stop_all_trackers() -> None:
    """Ferma tutti gli scheduler"""
    for farm_id in list(_schedulers.keys()):
        await stop_tracker_for_farm(farm_id)