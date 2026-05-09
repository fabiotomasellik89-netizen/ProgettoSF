# tasks.py
import os
import time
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:
    from backports.zoneinfo import ZoneInfo  # type: ignore

API_URL = "https://api.sunflower-land.com/community/farms/{land_id}"
HTTP_TIMEOUT_S = 12
RETRIES = 2
GROUP_WINDOW_MS = 60_000  # raggruppo per minuto


def _now_ms() -> int:
    return int(time.time() * 1000)


def _fmt_remaining(ms: Optional[int]) -> str:
    if ms is None:
        return ""
    if ms < 0:
        ms = 0
    s = ms // 1000
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def _fetch_farm(land_id: str) -> Optional[Dict[str, Any]]:
    url = API_URL.format(land_id=land_id)
    last_err: Optional[str] = None
    for attempt in range(1 + RETRIES):
        try:
            r = requests.get(
                url,
                timeout=HTTP_TIMEOUT_S,
                headers={"User-Agent": "SFL-multiuser-bot/1.0"},
            )
        except Exception as e:
            last_err = f"rete: {e}"
            time.sleep(0.8 * (attempt + 1))
            continue

        if r.status_code == 429:
            print("[FETCH] 429 Too Many Requests — prossimo giro")
            return None

        if r.status_code != 200:
            last_err = f"http {r.status_code}"
            time.sleep(0.6 * (attempt + 1))
            continue

        try:
            return r.json()
        except Exception:
            last_err = "non-json"
            time.sleep(0.4)
            continue

    print(f"[FETCH][{land_id}] fallita: {last_err}")
    return None


# -------------------- OVERRIDE opzionale da .env --------------------
def _parse_duration_to_ms(text: str) -> Optional[int]:
    """Accetta '197', '3:17', '3m17s', '00:03:17' → ms."""
    s = text.strip().lower()
    # 1) HH:MM:SS o MM:SS
    if ":" in s:
        parts = [p for p in s.split(":") if p != ""]
        try:
            parts = list(map(int, parts))
        except Exception:
            parts = []
        if len(parts) == 3:
            h, m, sec = parts
        elif len(parts) == 2:
            h, m, sec = 0, parts[0], parts[1]
        else:
            h = m = sec = None
        if h is not None:
            return (h * 3600 + m * 60 + sec) * 1000
    # 2) XmYs
    try:
        total = 0
        num = ""
        for ch in s:
            if ch.isdigit():
                num += ch
            elif ch in ("s", "m", "h"):
                if not num:
                    return None
                v = int(num)
                if ch == "h":
                    total += v * 3600
                elif ch == "m":
                    total += v * 60
                elif ch == "s":
                    total += v
                num = ""
        if num:
            # se c'è un numero senza suffisso, trattalo come secondi
            total += int(num)
        if total > 0:
            return total * 1000
    except Exception:
        pass
    # 3) solo secondi
    try:
        v = int(float(s))
        if v > 0:
            return v * 1000
    except Exception:
        pass
    return None


def _env_override_ms(name: str) -> Optional[int]:
    key = f"CROPTIME_{name.upper().replace(' ', '_')}"
    val = os.getenv(key)
    if not val:
        return None
    return _parse_duration_to_ms(val)


# -------------------- Normalizzazione API (sec/ms) --------------------
def _norm_epoch_ms(ts: Any) -> Optional[int]:
    """plantedAt può essere in secondi o ms → restituisce sempre ms."""
    if ts is None:
        return None
    try:
        v = int(ts)
    except Exception:
        return None
    if v <= 0:
        return None
    return v * 1000 if v < 1_000_000_000_000 else v


def _choose_boosted_ms(planted_ms: int, raw: Any, now_ms: int) -> Optional[int]:
    """
    boostedTime può essere in secondi o ms.
    Proviamo entrambe le interpretazioni e scegliamo quella più *vicina* al futuro;
    se entrambe passate, prendiamo la più vicina a 'now'. Tetto 30 giorni.
    """
    try:
        r = int(raw)
    except Exception:
        return None
    if r <= 0:
        return None

    MAX_MS = 30 * 24 * 3600 * 1000  # 30 giorni
    candidates: List[int] = []
    if r <= MAX_MS:
        candidates.append(r)            # interpreta come ms
    if r * 1000 <= MAX_MS:
        candidates.append(r * 1000)     # interpreta come secondi
    if not candidates:
        return None

    best = None
    best_key = None  # (is_past, abs_delta)
    for ms in candidates:
        delta = planted_ms + ms - now_ms
        is_past = 1 if delta < 0 else 0
        key = (is_past, abs(delta))
        if best_key is None or key < best_key:
            best_key = key
            best = ms
    return best


# -------------------- Raggruppamento compiti --------------------
def get_grouped_tasks(land_id: str, tz: str = "Europe/Rome") -> Dict[str, List[Dict[str, Any]]]:
    """
    Calcolo pronto/futuro da API per-utente:
      readyAt = plantedAt(normalizzato) + boostedTime(normalizzato o override .env)

    Ritorna:
      {
        "ready":  [{"name","time","count","ready_since_ms","display_time_ms"}],
        "future": [{"name","time","count","remaining_ms","display_time_ms"}],
      }
    """
    data = _fetch_farm(land_id)
    if not data or "farm" not in data:
        return {"ready": [], "future": []}

    farm = data["farm"]
    crops = (farm.get("crops") or {})
    now = _now_ms()
    z = ZoneInfo(tz)

    future: Dict[str, Dict[str, Any]] = {}
    ready: Dict[str, Dict[str, Any]] = {}

    for _, plot in (crops.items() if isinstance(crops, dict) else []):
        c = (plot or {}).get("crop") or {}
        name = c.get("name")
        planted_raw = c.get("plantedAt")
        boosted_raw = c.get("boostedTime")
        if not name:
            continue

        # 1) plantedAt → ms
        planted_ms = _norm_epoch_ms(planted_raw)
        if planted_ms is None:
            continue

        # 2) override per-crop da .env (es: CROPTIME_POTATO=197 o "3:17")
        env_ms = _env_override_ms(name)
        if env_ms is not None:
            boosted_ms = env_ms
            src = "env"
        else:
            boosted_ms = _choose_boosted_ms(planted_ms, boosted_raw, now)
            src = "api"

        if boosted_ms is None:
            # nessuna supposizione se l'API non fornisce dati plausibili
            continue

        ready_at = planted_ms + boosted_ms
        bucket = (ready_at // GROUP_WINDOW_MS) * GROUP_WINDOW_MS

        # Debug
        planted_local = datetime.fromtimestamp(planted_ms / 1000, tz=z).strftime("%H:%M:%S")
        ready_local = datetime.fromtimestamp(ready_at / 1000, tz=z).strftime("%H:%M:%S")
        print(
            f"[CROP] {name} src={src} plantedRaw={planted_raw}→plantedMs={planted_ms} ({planted_local}) "
            f"boostedRaw={boosted_raw}→usedMs={boosted_ms} "
            f"readyAt={ready_at} ({ready_local}) remaining={(ready_at-now)//1000}s"
        )

        key = f"{name}|{bucket}"
        if ready_at > now:
            g = future.setdefault(
                key,
                {"name": name, "time": bucket, "count": 0, "remaining_ms": None, "display_time_ms": None},
            )
            g["count"] += 1
            rem = ready_at - now
            if g["remaining_ms"] is None or rem < g["remaining_ms"]:
                g["remaining_ms"] = rem
            if g["display_time_ms"] is None or ready_at < g["display_time_ms"]:
                g["display_time_ms"] = ready_at
        else:
            g = ready.setdefault(
                key,
                {"name": name, "time": bucket, "count": 0, "ready_since_ms": None, "display_time_ms": None},
            )
            g["count"] += 1
            since = now - ready_at
            if g["ready_since_ms"] is None or since > g["ready_since_ms"]:
                g["ready_since_ms"] = since
            if g["display_time_ms"] is None or ready_at < g["display_time_ms"]:
                g["display_time_ms"] = ready_at

    out_ready = sorted(ready.values(), key=lambda x: x["time"])
    out_future = sorted(future.values(), key=lambda x: x["time"])

    # Log riassuntivi
    for g in out_ready:
        when = datetime.fromtimestamp((g.get("display_time_ms", g["time"])) / 1000, tz=z).strftime("%H:%M:%S")
        print(f"[PRONTI] {g['name']} → {g['count']} (dalle {when})")
    for g in out_future:
        when = datetime.fromtimestamp((g.get("display_time_ms", g["time"])) / 1000, tz=z).strftime("%H:%M:%S")
        print(f"[FUTURI] {g['name']} → {g['count']} alle {when} ({_fmt_remaining(int(g.get('remaining_ms') or 0))})")

    return {"ready": out_ready, "future": out_future}


# --- compat per main.py vecchi ---
def get_future_grouped_tasks_with_countdown(land_id: str, tz: str = "Europe/Rome") -> List[Dict[str, Any]]:
    return get_grouped_tasks(land_id, tz)["future"]

def get_ready_grouped_tasks(land_id: str, window_back_ms: int = 120_000) -> List[Dict[str, Any]]:
    now = _now_ms()
    start = now - window_back_ms
    ready = get_grouped_tasks(land_id)["ready"]
    return [g for g in ready if start <= g["time"] <= now]
