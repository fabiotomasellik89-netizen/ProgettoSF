# sflworld_client.py — versione SAFE con cache

import time

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

_BASE = "https://sfl.world/api/v1/land/{farm_id}"
_CACHE = {}            # {farm_id: (ts, data)}
_TTL = 300             # 5 minuti

def _now() -> int:
    return int(time.time())

def fetch_land_boosts(farm_id: str) -> dict:
    """Ritorna { name: {multiplier, progress, cap, percent} } oppure {} se non disponibile."""
    farm_id = str(farm_id)
    ts, data = _CACHE.get(farm_id, (0, {}))
    if _now() - ts < _TTL and data:
        return data

    if requests is None:
        return data or {}

    url = _BASE.format(farm_id=farm_id)
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        raw = r.json()
    except Exception:
        return data or {}

    out = {}
    resources = raw.get("resources") or raw.get("boosts") or raw.get("data") or []
    if isinstance(resources, dict):
        resources = list(resources.values())
    if isinstance(resources, list):
        for rec in resources:
            try:
                name = str(rec.get("name") or rec.get("item") or rec.get("resource") or "").strip()
                if not name:
                    continue
                mul = float(rec.get("multiplier") or rec.get("mult") or rec.get("value") or 1.0)
                prog = rec.get("progress") or rec.get("current")
                cap = rec.get("cap") or rec.get("target")
                pct = rec.get("percent") or rec.get("percentage")
                if isinstance(pct, str) and pct.endswith("%"):
                    try:
                        pct = float(pct[:-1])
                    except Exception:
                        pct = None
                out[name] = {
                    "multiplier": mul if mul else 1.0,
                    "progress": prog,
                    "cap": cap,
                    "percent": float(pct) if pct is not None else None,
                }
            except Exception:
                pass

    _CACHE[farm_id] = (_now(), out)
    return out
