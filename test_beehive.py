#!/usr/bin/env python3
import asyncio
from api import fetch_farm_with_user_key
from datetime import datetime, timezone

def _fmt_hm(ms_left: int) -> str:
    if ms_left <= 0:
        return "0m"
    total_min = ms_left // 60000
    hours = total_min // 60
    minutes = total_min % 60
    return f"{hours}h{minutes}m"

async def test_in_corso_beehives():
    chat_id = 396672530
    land_id = "143246"
    
    payload, _, server_now_ms = await fetch_farm_with_user_key(land_id, chat_id, force=True)
    
    BEEHIVE_MAX_HONEY = 68664000
    HONEY_PER_HOUR_BASE = 2600909
    NOTIFICATION_THRESHOLD = BEEHIVE_MAX_HONEY * 0.98
    
    print("🔍 COSA APPARIREBBE IN 'IN CORSO':")
    print("=" * 60)
    
    beehives = payload.get("farm", {}).get("beehives", {})
    
    for hive_id, hive_data in beehives.items():
        x = hive_data.get('x')
        y = hive_data.get('y')
        honey_data = hive_data.get("honey", {})
        produced = honey_data.get("produced", 0)
        updated_at = honey_data.get("updatedAt", server_now_ms)
        
        # Fiori attivi
        flowers = hive_data.get("flowers", [])
        active_flowers = [f for f in flowers if f.get("attachedUntil", 0) > server_now_ms]
        
        if not active_flowers:
            print(f"📍 Alveare ({x},{y}): ❌ Nessun fiore attivo")
            continue
            
        # Calcola produzione
        total_rate = 1.0
        earliest_expiry = min(f.get("attachedUntil") for f in active_flowers)
        
        for flower in active_flowers:
            total_rate *= flower.get("rate", 1.0)
        
        honey_per_hour = HONEY_PER_HOUR_BASE * total_rate
        
        # Calcola miele attuale
        time_elapsed_ms = server_now_ms - updated_at
        time_elapsed_hours = time_elapsed_ms / (1000 * 60 * 60)
        current_honey = produced + (honey_per_hour * time_elapsed_hours)
        
        if current_honey >= NOTIFICATION_THRESHOLD:
            print(f"📍 Alveare ({x},{y}): ✅ Già sopra il 98%")
            continue
            
        honey_needed = NOTIFICATION_THRESHOLD - current_honey
        hours_needed = honey_needed / honey_per_hour
        ready_time = server_now_ms + int(hours_needed * 60 * 60 * 1000)
        
        # Verifica se appare in "In corso"
        will_appear_in_corso = ready_time <= earliest_expiry
        
        print(f"📍 Alveare ({x},{y}):")
        print(f"   Current: {current_honey:,.0f} ({(current_honey/BEEHIVE_MAX_HONEY*100):.1f}%)")
        print(f"   Needed for 98%: {honey_needed:,.0f}")
        print(f"   Production: {honey_per_hour:,.0f}/h")
        print(f"   Hours needed: {hours_needed:.1f}")
        print(f"   Ready at: {datetime.fromtimestamp(ready_time/1000, tz=timezone.utc).strftime('%d/%m %H:%M')}")
        print(f"   Flower expires: {datetime.fromtimestamp(earliest_expiry/1000, tz=timezone.utc).strftime('%d/%m %H:%M')}")
        print(f"   In 'In corso'? {'✅ SI' if will_appear_in_corso else '❌ NO'}")

if __name__ == "__main__":
    asyncio.run(test_in_corso_beehives())