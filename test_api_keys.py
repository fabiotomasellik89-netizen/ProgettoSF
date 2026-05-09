#!/usr/bin/env python3
"""
Script di test per verificare API keys e notifiche
"""
import asyncio
import logging
from storage import get_api_key, get_all_subscribed
from api import fetch_farm_with_user_key

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def test_all():
    print("=" * 60)
    print("TEST API KEYS E NOTIFICHE")
    print("=" * 60)
    
    # Test 1: Verifica utenti iscritti
    print("\n📋 UTENTI ISCRITTI:")
    subscribed = get_all_subscribed()
    print(f"   Totale: {len(subscribed)}")
    
    # Test 2: Verifica API keys
    print("\n🔑 VERIFICA API KEYS:")
    for chat_id, land_id in subscribed:
        api_key = get_api_key(chat_id)
        if api_key:
            print(f"   ✅ Chat {chat_id} (Farm {land_id}): {api_key[:20]}...")
        else:
            print(f"   ❌ Chat {chat_id} (Farm {land_id}): MANCANTE")
    
    # Test 3: Prova fetch per ogni farm
    print("\n🌐 TEST FETCH API:")
    for chat_id, land_id in subscribed:
        try:
            print(f"   Testing farm {land_id}...", end=" ")
            payload, url, _ = await fetch_farm_with_user_key(land_id, chat_id, force=True)
            
            if payload and "farm" in payload:
                print(f"✅ OK")
                
                # Mostra alcune info
                farm = payload.get("farm", {})
                crops_count = len(farm.get("crops", {}))
                trees_count = len(farm.get("trees", {}))
                print(f"      └─ Crops: {crops_count}, Trees: {trees_count}")
            else:
                print(f"⚠️  Payload vuoto")
                
        except Exception as e:
            print(f"❌ ERRORE: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETATO")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_all())