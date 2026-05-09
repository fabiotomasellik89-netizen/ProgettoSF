from datetime import datetime, timezone

# Costanti alveari CORRETTE - valori aggiornati
BEEHIVE_MAX_HONEY = 68_664_000  # 68.664M (53.989M prodotto + 14.675M boost fiori)
HONEY_PER_HOUR_BASE = 2_260_000  # 1 miele = 2.26M/ora (53.989M / 24h)
HONEY_PER_HOUR_HYPER = int(2_260_000 * 1.1)  # +10% con Hyper Bees = 2.486M/ora


def _abbr_num(n: float) -> str:
    for unit in ["", "K", "M", "B", "T"]:
        if abs(n) < 1000:
            return f"{n:.2f}{unit}".rstrip("0").rstrip(".") + (unit if unit else "")
        n /= 1000.0
    return f"{n:.2f}P"


def _fmt_hm(ms_left: int) -> str:
    if ms_left <= 0:
        return "0m"
    total_min = ms_left // 60_000
    days = total_min // (24 * 60)
    hours = (total_min // 60) % 24
    minutes = total_min % 60

    if days >= 1:
        return f"{days}g{hours}h" if hours > 0 else f"{days}g"
    if total_min >= 60:
        return f"{total_min//60}h{minutes}m" if minutes > 0 else f"{total_min//60}h"
    return f"{minutes}m"


def _fmt_time(ts_ms: int, tzinfo) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=tzinfo)
    return dt.strftime("%d/%m - %H:%M")


def build_beehives_section(payload: dict, now_ms: int, tzinfo=timezone.utc) -> list[str]:
    beehives = payload.get("farm", {}).get("beehives", {})
    if not beehives:
        return []

    # Skill Hyper Bees
    skills = payload.get("farm", {}).get("skills", {})
    has_hyper_bees = "Hyper Bees" in skills
    honey_per_hour = HONEY_PER_HOUR_HYPER if has_hyper_bees else HONEY_PER_HOUR_BASE

    rows = []

    for hive_id, hive in beehives.items():
        if not isinstance(hive, dict):
            continue

        coord = f"({hive.get('x', '?')},{hive.get('y', '?')})"
        honey_data = hive.get("honey", {}) or {}
        flowers = hive.get("flowers", []) or []

        extra = []

        # Miele attuale - CALCOLO CORRETTO
        produced = float(honey_data.get("produced", 0))
        updated_at = honey_data.get("updatedAt", now_ms)
        
        # Calcolo preciso delle ore trascorse
        hours_since_update = max(0, (now_ms - updated_at) / 3_600_000.0)
        accrued = hours_since_update * honey_per_hour
        current_honey = produced + accrued
        
        # Limita al massimo
        if current_honey > BEEHIVE_MAX_HONEY:
            current_honey = BEEHIVE_MAX_HONEY

        honey_str = f"{_abbr_num(current_honey)} ({current_honey / BEEHIVE_MAX_HONEY * 100:.1f}%)"

        # Swarm attivo
        if hive.get("swarm"):
            extra.append("🐝 sciame attivo (+0.2/+0.3 crops)")

        # Fiori attivi
        if flowers:
            valid_expiries = [f["expiresAt"] for f in flowers if isinstance(f.get("expiresAt"), (int, float))]
            if valid_expiries:
                earliest_expiry = min(valid_expiries)
                time_to_expiry_ms = max(0, earliest_expiry - now_ms)

                # Calcola quanto miele si produrrà prima della scadenza
                hours_to_expiry = time_to_expiry_ms / 3_600_000.0
                honey_before_expiry = hours_to_expiry * honey_per_hour
                future_honey = current_honey + honey_before_expiry
                
                # Limita al massimo
                if future_honey > BEEHIVE_MAX_HONEY:
                    future_honey = BEEHIVE_MAX_HONEY

                # Logica notifiche/alerts
                if current_honey >= BEEHIVE_MAX_HONEY:
                    extra.append("🔴 BLOCCATO (100%)")
                elif current_honey >= BEEHIVE_MAX_HONEY * 0.98:
                    extra.append("✅ pronto (>98%)")
                else:
                    # Calcola se arriverà al 98% prima della scadenza
                    honey_needed_for_98 = (BEEHIVE_MAX_HONEY * 0.98) - current_honey
                    
                    if honey_needed_for_98 <= 0:
                        extra.append("✅ pronto (>98%)")
                    elif honey_before_expiry >= honey_needed_for_98:
                        # Diventerà pronto prima della scadenza
                        hours_needed = honey_needed_for_98 / honey_per_hour
                        ready_time_ms = now_ms + int(hours_needed * 3_600_000)
                        time_left = ready_time_ms - now_ms
                        when = _fmt_time(ready_time_ms, tzinfo)
                        extra.append(f"✅ {when} ({_fmt_hm(time_left)})")
                    else:
                        # Non arriverà al 98% prima della scadenza
                        future_percent = (future_honey / BEEHIVE_MAX_HONEY) * 100
                        when_expiry = _fmt_time(earliest_expiry, tzinfo)
                        extra.append(f"⏸️ {when_expiry} → {future_percent:.1f}%")
            else:
                extra.append("⚠️ fiore senza scadenza")
        else:
            extra.append("❌ senza fiore → produzione ferma")

        rows.append(f"🐝 {coord} → {' • '.join(extra)} • {honey_str}")

    return rows