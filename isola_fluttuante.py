# isola_fluttuante.py — stand-alone, con supporto API key
from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
import asyncio
import httpx

# timezone: prova Europe/Rome, altrimenti usa UTC (mai crashare)
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Rome")
except Exception:
    TZ = timezone.utc


# =============== Helpers tempo/formatting ===============
def _to_ms(v) -> Optional[int]:
    try:
        v = int(v)
        if v < 10_000_000_000:  # secondi -> ms
            v *= 1000
        return v
    except Exception:
        return None

def _fmt_human_delta(ms: Optional[int]) -> str:
    if not ms or ms <= 0:
        return "0m"
    s = ms // 1000
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    if d:
        return f"{d}g{h}h"
    if h:
        return f"{h}h{m}m"
    return f"{m}m"

def _fmt_when(ms: int) -> str:
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=TZ)
        return dt.strftime("%d/%m - %H:%M")
    except Exception:
        return "—"

def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


# =============== Fetch payload completo (con API key) ===============
async def _fetch_full_payload(land_id: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Scarica il payload completo della farm dal community endpoint.
    Ritorna {} se non disponibile. Retry soft su 429 e HTTPError.
    
    Args:
        land_id: ID della farm
        api_key: SFL API key dell'utente (necessaria per autenticazione)
    """
    if not land_id:
        return {}

    url = f"https://api.sunflower-land.com/community/farms/{land_id}"
    params = {"_": _now_ms()}
    
    # Headers con API key se fornita
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SFLTelegramBot/2.0"
    }
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                data = r.json()
                return data if isinstance(data, dict) else {}
            if r.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            # Se 401/403, probabilmente API key mancante o non valida
            if r.status_code in (401, 403):
                return {}
            r.raise_for_status()
        except httpx.HTTPError:
            if attempt == 2:
                return {}
            await asyncio.sleep(1.0)
        except Exception:
            # qualunque altro errore → riprova, poi arrenditi
            if attempt == 2:
                return {}
            await asyncio.sleep(1.0)

    return {}


# =============== Ricerca ricorsiva di "floatingIsland" ===============
def _find_floating_island(node: Any) -> Dict[str, Any]:
    """
    Trova ricorsivamente la chiave 'floatingIsland' ovunque nel payload.
    Ritorna {} se non trovata o se non è un dict.
    """
    import logging
    log = logging.getLogger("sflbot")
    
    try:
        if isinstance(node, dict):
            # Check diretto
            fi = node.get("floatingIsland")
            if isinstance(fi, dict):
                log.info(f"Isola: Trovata floatingIsland con keys: {list(fi.keys())}")
                return fi
            
            # Ricerca ricorsiva
            for key, v in node.items():
                if key == "floatingIsland":
                    continue  # già controllato sopra
                found = _find_floating_island(v)
                if found:
                    log.info(f"Isola: floatingIsland trovata sotto chiave '{key}'")
                    return found
                    
        elif isinstance(node, list):
            for i, v in enumerate(node):
                found = _find_floating_island(v)
                if found:
                    log.info(f"Isola: floatingIsland trovata in lista[{i}]")
                    return found
    except Exception as e:
        log.error(f"Isola: Errore in _find_floating_island: {e}")
        pass
    
    return {}


# =============== Parser/formatter Isola ===============
def _read_schedule(fi: Dict[str, Any]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    try:
        for wind in (fi.get("schedule") or []):
            sa = _to_ms((wind or {}).get("startAt"))
            ea = _to_ms((wind or {}).get("endAt"))
            if sa and ea and ea > sa:
                out.append((sa, ea))
        out.sort(key=lambda t: t[0])
    except Exception:
        out = []
    return out

# --- Ricava la prossima finestra dell'isola (stand-alone) ---
def _find_next_window(fi: Dict[str, Any], now_ms: int) -> Optional[Tuple[int, int]]:
    sched = fi.get("schedule") or []
    best = None
    for w in sched:
        try:
            sa = _to_ms((w or {}).get("startAt"))
            ea = _to_ms((w or {}).get("endAt"))
            if sa and ea and ea > now_ms:
                if sa > now_ms:
                    # finestra futura: candidata
                    if best is None or sa < best[0]:
                        best = (sa, ea)
                elif sa <= now_ms < ea:
                    # finestra corrente: per completezza
                    if best is None:
                        best = (sa, ea)
        except Exception:
            continue
    return best

async def get_next_island_window(land_id: str, api_key: Optional[str] = None) -> Optional[Tuple[int, int]]:
    """
    Ritorna (start_ms, end_ms) della finestra più prossima (corrente o futura).
    Cerca ricorsivamente 'floatingIsland' nel payload completo.
    
    Args:
        land_id: ID della farm
        api_key: SFL API key dell'utente
    """
    payload = await _fetch_full_payload(land_id, api_key)
    fi = _find_floating_island(payload)
    if not fi:
        return None
    return _find_next_window(fi, _now_ms())


def _windows_status(windows: List[Tuple[int, int]], now_ms: int):
    current = None
    upcoming = None
    for (sa, ea) in windows:
        if sa <= now_ms < ea:
            current = (sa, ea)
            break
        if now_ms < sa:
            upcoming = (sa, ea)
            break

    next_two: List[Tuple[int, int]] = []
    for (sa, ea) in windows:
        if now_ms < sa:
            next_two.append((sa, ea))
        if len(next_two) >= 2:
            break

    return current, upcoming, next_two

def _read_shop(fi: Dict[str, Any]) -> List[Dict[str, Any]]:
    shop = fi.get("shop") or {}
    bought = fi.get("boughtAt") or {}
    items: List[Dict[str, Any]] = []

    try:
        for key, meta in shop.items():
            name = (meta or {}).get("name") or key
            cost_items = ((meta or {}).get("cost") or {}).get("items") or {}
            bought_ms = _to_ms(bought.get(name)) or _to_ms(bought.get(key))
            items.append({
                "name": name,
                "cost_items": cost_items,
                "bought_at_ms": bought_ms
            })
        # ordina: non acquistati prima, poi per Love Charm crescente, poi alfabetico
        def _sort_key(it: Dict[str, Any]):
            bought_flag = 1 if it.get("bought_at_ms") else 0
            lc = (it.get("cost_items") or {}).get("Love Charm", 0)
            return (bought_flag, lc, it.get("name") or "")
        items.sort(key=_sort_key)
    except Exception:
        items = []

    return items

def build_floating_island_text_from_fi(fi: Dict[str, Any]) -> str:
    now = _now_ms()
    windows = _read_schedule(fi)
    items = _read_shop(fi)

    lines: List[str] = []
    lines.append("🏝️ *Isola fluttuante*")

    # Stato finestre
    cur, nxt, nxt2 = _windows_status(windows, now)
    if cur:
        sa, ea = cur
        left = max(0, ea - now)
        lines.append(f"🟢 *Aperta ora* — fino alle {_fmt_when(ea)} ({_fmt_human_delta(left)})")
    elif nxt:
        sa, ea = nxt
        eta = max(0, sa - now)
        lines.append(f"🕐 Prossima apertura: {_fmt_when(sa)} → (tra {_fmt_human_delta(eta)})")
    else:
        lines.append("ℹ️ Nessuna finestra in calendario.")

    # Prossime due finestre
    if nxt2:
        lines.append("")
        lines.append("*Finestre successive:*")
        for (sa, ea) in nxt2:
            if sa <= now:
                continue
            lines.append(f"• {_fmt_when(sa)} → {_fmt_when(ea)}")

    # Shop
    lines.append("")
    lines.append("🛒 *Negozio:*")
    if not items:
        lines.append("— (vuoto)")
    else:
        for it in items:
            name = it.get("name") or "Item"
            cost = it.get("cost_items") or {}
            bought_ms = it.get("bought_at_ms")
            # costo leggibile
            parts = []
            for k, v in cost.items():
                try:
                    q = int(v)
                except Exception:
                    q = v
                parts.append(f"{k} × {q}")
            cost_str = ", ".join(parts) if parts else "—"

            if bought_ms:
                lines.append(f"• {name} — {cost_str}  *(già acquistato: {_fmt_when(bought_ms)})*")
            else:
                lines.append(f"• {name} — {cost_str}")

    return "\n".join(lines)


# =============== Entry-point con supporto chat_id ===============
async def render_isola_fluttuante(land_id: str, chat_id: int) -> str:
    """
    - Recupera l'API key dell'utente dallo storage
    - Fa fetch del payload completo con autenticazione
    - Cerca 'floatingIsland' ovunque
    - Rende il testo
    
    Args:
        land_id: ID della farm
        chat_id: ID chat Telegram (per recuperare API key)
    
    Returns:
        str: Messaggio formattato
    """
    try:
        # Importa storage per recuperare API key
        from storage import get_api_key
        import logging
        log = logging.getLogger("sflbot")
        
        api_key = get_api_key(chat_id)
        if not api_key:
            log.error(f"Isola: API Key non trovata per chat {chat_id}")
            return ("🏝️ *Isola fluttuante*\n\n"
                    "❌ API Key non trovata. Imposta la tua API key con /setkey")
        
        log.info(f"Isola: Fetching farm {land_id} per chat {chat_id}")
        payload = await _fetch_full_payload(land_id, api_key)
        
        if not payload:
            log.error(f"Isola: Payload vuoto per farm {land_id}")
            return ("🏝️ *Isola fluttuante*\n\n"
                    "❌ Impossibile recuperare i dati. Verifica la tua API key.")
        
        log.info(f"Isola: Payload ricevuto, keys: {list(payload.keys())}")
        
        fi = _find_floating_island(payload)
        if not fi:
            log.warning(f"Isola: floatingIsland non trovata nel payload")
            log.debug(f"Isola: Struttura payload: {payload.keys()}")
            
            # Debug: mostra struttura
            debug_info = []
            if "game" in payload:
                debug_info.append(f"game keys: {list(payload['game'].keys())}")
            if "farm" in payload:
                debug_info.append(f"farm keys: {list(payload['farm'].keys())}")
            
            log.debug(f"Isola: Debug info: {debug_info}")
            
            return ("🏝️ *Isola fluttuante*\n\n"
                    "ℹ️ L'isola fluttuante non è disponibile.\n\n"
                    "_L'isola potrebbe non essere ancora attiva per la tua farm, "
                    "o potresti non averla ancora visitata._")
        
        log.info(f"Isola: floatingIsland trovata, keys: {list(fi.keys())}")
        result = build_floating_island_text_from_fi(fi)
        log.info(f"Isola: Messaggio generato, lunghezza: {len(result)}")
        return result
        
    except Exception as e:
        import logging
        log = logging.getLogger("sflbot")
        log.error(f"Isola: Errore durante il caricamento: {e}", exc_info=True)
        return ("🏝️ *Isola fluttuante*\n\n"
                f"❌ Errore durante il caricamento: {str(e)}")


__all__ = [
    "render_isola_fluttuante",
    "get_next_island_window"
]