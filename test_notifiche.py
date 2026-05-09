# test_notifiche_simple.py
import json
import time
import logging
from pathlib import Path
import sys
import os

# Aggiungi la cartella corrente al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test")

def test_direct_notifications():
    """Testa direttamente le funzioni di notifica alveari"""
    print("🔍 TEST DIRETTO SISTEMA NOTIFICHE ALVEARI")
    print("=" * 60)
    
    # 1. PRIMA troviamo un file payload esistente
    data_dir = Path("data")
    if not data_dir.exists():
        print("❌ Cartella 'data/' non esiste!")
        return
    
    payload_files = list(data_dir.glob("payload_*.json"))
    if not payload_files:
        print("❌ Nessun file payload trovato!")
        print("💡 Esegui prima: /payload dal bot per generare un file")
        return
    
    # Usa il file più recente
    latest_file = max(payload_files, key=lambda p: p.stat().st_mtime)
    print(f"📂 Usando file: {latest_file.name}")
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    
    now_ms = int(time.time() * 1000)
    
    # 2. TESTA BEE SWARM
    print("\n🐝 TEST BEE SWARM:")
    beehives = payload.get("farm", {}).get("beehives", {})
    
    if not beehives:
        print("   ❌ Nessun alveare trovato nel payload!")
        return
    
    swarm_count = 0
    for hive_id, hive in beehives.items():
        if isinstance(hive, dict):
            swarm = hive.get("swarm")
            if swarm and isinstance(swarm, dict) and swarm.get("active", False):
                swarm_count += 1
                x = hive.get("x", "?")
                y = hive.get("y", "?")
                print(f"   ✅ SWARM ATTIVO in alveare ({x},{y})")
    
    if swarm_count == 0:
        print("   ℹ️ Nessuno swarm attivo trovato")
    
    # 3. TESTA ALVEARI PIENI (98%)
    print("\n🍯 TEST ALVEARI PIENI (98%):")
    BEEHIVE_MAX_HONEY = 68664000
    THRESHOLD = BEEHIVE_MAX_HONEY * 0.98  # 98%
    
    full_count = 0
    for hive_id, hive in beehives.items():
        if isinstance(hive, dict):
            honey = hive.get("honey", {})
            produced = honey.get("produced", 0) or 0
            
            percent = (produced / BEEHIVE_MAX_HONEY) * 100
            
            if produced >= THRESHOLD:
                full_count += 1
                x = hive.get("x", "?")
                y = hive.get("y", "?")
                print(f"   ✅ ALVEARE PIENO ({x},{y}): {percent:.1f}%")
            elif percent > 50:  # Mostra quelli sopra il 50%
                x = hive.get("x", "?")
                y = hive.get("y", "?")
                print(f"   ⚠️  Alveare ({x},{y}): {percent:.1f}%")
    
    if full_count == 0:
        print("   ℹ️ Nessun alveare pieno trovato (soglia 98%)")
    
    # 4. TESTA SE IL SISTEMA NOTIFICHE FUNZIONA
    print("\n🔔 TEST SISTEMA NOTIFICHE ATTUALE:")
    try:
        # Importa le funzioni dal file esistente
        from notifications_old import NotificationManager
        
        print("   ✅ Importato NotificationManager")
        
        # Testa _check_bee_swarm
        manager = NotificationManager([123], "test_farm", None)
        
        swarm_result = manager._check_bee_swarm(payload)
        print(f"   _check_bee_swarm: {len(swarm_result)} risultati")
        
        if swarm_result:
            for item in swarm_result:
                print(f"     - {item[0]}: {item[1]}")
        
        # Testa _check_beehive_full
        full_result = manager._check_beehive_full(payload)
        print(f"   _check_beehive_full: {len(full_result)} risultati")
        
        if full_result:
            for item in full_result:
                print(f"     - {item[0]}: {item[1]}")
        
    except ImportError as e:
        print(f"   ❌ Non riesco a importare notifications_old.py: {e}")
    except Exception as e:
        print(f"   ❌ Errore nel test: {e}")
    
    # 5. VERIFICA SE CI SONO DATI DI PRODUZIONE
    print("\n📊 VERIFICA DATI PRODUZIONE:")
    for hive_id, hive in list(beehives.items())[:3]:  # Primi 3
        if isinstance(hive, dict):
            honey = hive.get("honey", {})
            produced = honey.get("produced", 0) or 0
            updated_at = honey.get("updatedAt", 0)
            
            x = hive.get("x", "?")
            y = hive.get("y", "?")
            
            # Converti timestamp in data
            if updated_at:
                from datetime import datetime
                dt = datetime.fromtimestamp(updated_at/1000)
                time_str = dt.strftime("%d/%m %H:%M")
            else:
                time_str = "N/A"
            
            print(f"   Alveare ({x},{y}):")
            print(f"     Produced: {produced:,}")
            print(f"     Last update: {time_str}")
            print(f"     Flowers: {len(hive.get('flowers', []))}")
            
            if hive.get("swarm"):
                print(f"     ⚡ SWARM PRESENTE!")

if __name__ == "__main__":
    test_direct_notifications()