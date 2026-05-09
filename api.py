# api.py
from __future__ import annotations
import time, httpx, logging
from typing import Dict, Any, Tuple, Optional
from config import API_BASE

log = logging.getLogger("sflbot")

# cache leggera: ultimo snapshot per land
_CACHE: Dict[str, Dict[str, Any]] = {}   # land_id -> {"data": ..., "at": ms}
_CACHE_TTL_MS = 60_000  # 60s: evita flood quando premi più volte

async def fetch_farm(
    land_id: str, 
    force: bool = False,
    api_key: Optional[str] = None
) -> Tuple[Dict[str, Any], str, int]:
    """
    Ritorna (payload, url, now_ms).
    
    Args:
        land_id: ID della farm da recuperare
        force: True per forzare refresh (bypass cache)
        api_key: SFL API Key dell'utente (formato: sfl.xxxxx.xxxxx)
    
    - force=True: bust cache lato server (query param + header no-cache).
    - in caso di 429/timeout/errore rete: se esiste uno snapshot in cache recente -> fallback.
    - api_key: Se fornita, viene aggiunta all'header x-api-key per autenticazione
    """
    now_ms = int(time.time() * 1000)
    url = f"{API_BASE}{land_id}"
    
    # Headers base
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SFLTelegramBot/2.0"
    }
    
    # Aggiungi API key se fornita
    if api_key:
        headers["x-api-key"] = api_key
    
    params = None
    if force:
        params = {"_": str(now_ms)}               # cache-busting server
        headers.update({
            "Cache-Control": "no-cache", 
            "Pragma": "no-cache"
        })

    # usa cache locale se non è scaduta e non forzi
    if not force and land_id in _CACHE:
        age = now_ms - _CACHE[land_id]["at"]
        if age <= _CACHE_TTL_MS:
            data = dict(_CACHE[land_id]["data"])
            data["__cached__"] = True
            log.debug(f"fetch_farm {land_id} -> usando cache locale ({age}ms)")
            return data, url, now_ms

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            log.debug(f"fetch_farm {land_id} -> chiamata API con key: {bool(api_key)}")
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
        
        data["__cached__"] = False
        _CACHE[land_id] = {"data": data, "at": now_ms}
        log.info(f"fetch_farm {land_id} -> successo (fresh data)")
        return data, url, now_ms

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        log.warning(f"fetch_farm {land_id} -> HTTP {status_code}")
        
        # Se 401/403, probabilmente API key non valida o mancante
        if status_code in (401, 403):
            log.error(f"fetch_farm {land_id} -> autenticazione fallita (API key non valida?)")
            # Non usare cache per errori di autenticazione
            raise ValueError("API Key non valida o scaduta. Aggiorna la tua API key.")
        
        # Per altri errori, prova fallback a cache
        if land_id in _CACHE:
            data = dict(_CACHE[land_id]["data"])
            data["__cached__"] = True
            log.info(f"fetch_farm {land_id} -> fallback a cache dopo HTTP {status_code}")
            return data, url, now_ms
        raise
        
    except (httpx.TimeoutException, httpx.TransportError) as e:
        log.warning(f"fetch_farm {land_id} -> network error: {e}")
        if land_id in _CACHE:
            data = dict(_CACHE[land_id]["data"])
            data["__cached__"] = True
            log.info(f"fetch_farm {land_id} -> fallback a cache dopo network error")
            return data, url, now_ms
        raise


async def fetch_farm_with_user_key(land_id: str, chat_id: int, force: bool = False) -> Tuple[Dict[str, Any], str, int]:
    """
    Wrapper che recupera automaticamente l'API key dell'utente dallo storage
    
    Args:
        land_id: ID della farm
        chat_id: ID chat Telegram dell'utente
        force: True per forzare refresh
    
    Returns:
        Tuple (payload, url, timestamp)
    
    Raises:
        ValueError: Se l'utente non ha una API key salvata
    """
    from storage import get_api_key
    
    api_key = get_api_key(chat_id)
    if not api_key:
        raise ValueError("API Key non trovata. Imposta la tua API key con /setkey")
    
    return await fetch_farm(land_id, force=force, api_key=api_key)


# Mantieni retrocompatibilità con codice esistente
# Se fetch_farm viene chiamato senza api_key, prova comunque (per test o uso server-side)