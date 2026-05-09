import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# CARICA IL .env PRIMA DI TUTTO!
load_dotenv()

# Configurazione Bot Telegram
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── Generali ───────────────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Rome")        # timezone locale
GROUP_THRESHOLD_MS = 60_000         # raggruppo elementi entro 1 minuto
MAX_LINES = 30                      # numero massimo righe per sezione
SFL_BASE_URL = os.getenv("SFL_BASE_URL", "https://api.sunflower-land.com/community")
# Preesistente (compatibilità): API_BASE kept for older code
API_BASE = os.getenv("API_BASE", f"{SFL_BASE_URL}/farms/")  # usato da api.py

# Chiave API server-side (opzionale). Non è obbligatorio: gli utenti devono fornire la propria SFL_API_KEY
SFL_API_KEY = os.getenv("SFL_API_KEY")


# Admin IDs (dal .env, separati da virgola)
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if admin_ids_str:
    ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]

# Configurazione API SFL
API_URL = "https://api.sunflower-land.com"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "SFLTelegramBot/1.0"
}

# ── TEMPI COLTURE (millisecondi) ──────────────────────────────────────────────
# IMPORTANTE: Tutti i tempi sono in MILLISECONDI per coerenza con l'API
GROWTH_MS = {
    # Base crops
    "Sunflower":       60_000,        # 1min
    "Potato":         300_000,        # 5min
    "Rhubarb":        600_000,        # 10min
    "Pumpkin":      1_800_000,        # 30min
    "Zucchini":     1_800_000,        # 30min
    
    # Medium crops
    "Carrot":       3_600_000,        # 1h
    "Yam":          3_600_000,        # 1h
    "Cabbage":      7_200_000,        # 2h
    "Broccoli":     7_200_000,        # 2h
    "Soybean":     10_800_000,        # 3h
    "Beetroot":    14_400_000,        # 4h
    "Pepper":      14_400_000,        # 4h
    "Cauliflower": 28_800_000,        # 8h
    
    # Advanced crops
    "Parsnip":     43_200_000,        # 12h
    "Eggplant":    57_600_000,        # 16h
    "Corn":        72_000_000,        # 20h
    "Onion":       72_000_000,        # 20h
    "Radish":      86_400_000,        # 24h
    "Wheat":       86_400_000,        # 24h
    "Turnip":      86_400_000,        # 24h
    "Kale":       129_600_000,        # 36h
    "Artichoke":  129_600_000,        # 36h
    "Barley":     172_800_000,        # 48h
}

# Helper per conversione (se serve per debugging)
def ms_to_hours(ms: int) -> float:
    """Converti millisecondi in ore"""
    return ms / (1000 * 60 * 60)

def hours_to_ms(hours: float) -> int:
    """Converti ore in millisecondi"""
    return int(hours * 60 * 60 * 1000)

# Definizione categorie crops
BASE_CROPS = {"Sunflower", "Potato", "Pumpkin", "Zucchini", "Rhubarb"}
MEDIUM_CROPS = {"Carrot", "Yam", "Cabbage", "Broccoli", "Soybean", "Beetroot", "Pepper", "Cauliflower", "Parsnip"}  
ADVANCED_CROPS = {"Eggplant", "Corn", "Onion", "Radish", "Wheat", "Kale", "Artichoke", "Barley", "Turnip"}

# Effetti spaventapasseri
SCARECROW_EFFECTS = {
    "Basic Scarecrow": {
        "type": "time_reduction",
        "value": 0.30,  # -30% tempo
        "affected_crops": BASE_CROPS
    },
    "Scary Mike": {
        "type": "yield_boost", 
        "value": 0.30,  # +0.3 crops
        "affected_crops": MEDIUM_CROPS
    },
    "Laurie the Chuckle Crow": {
        "type": "yield_boost",
        "value": 0.30,  # +0.3 crops
        "affected_crops": ADVANCED_CROPS
    }
}

# Percentuale riduzione Basic Scarecrow
BASIC_SCARECROW_REDUCTION_PERCENT = 0.30  # -30% del tempo base

# ── TEMPI FRUTTA (millisecondi) ───────────────────────────────────────────────
FRUIT_REGEN_MS = {
    "Tomato":      7_200_000,    # 2h
    "Lemon":      14_400_000,    # 4h
    "Blueberry":  21_600_000,    # 6h
    "Orange":     28_800_000,    # 8h
    "Apple":      43_200_000,    # 12h
    "Banana":     43_200_000,    # 12h
    "Celestine":  21_600_000,    # 6h
    "Lunara":     43_200_000,    # 12h
    "Duskberry":  86_400_000,    # 24h
}

# ── TEMPI FIORI (millisecondi) ────────────────────────────────────────────────
FLOWER_GROWTH_MS = {
    # Sunpetal seed - 24h
    "Red Pansy": 86_400_000, "Yellow Pansy": 86_400_000, "Purple Pansy": 86_400_000,
    "White Pansy": 86_400_000, "Blue Pansy": 86_400_000,
    "Red Cosmos": 86_400_000, "Yellow Cosmos": 86_400_000, "Purple Cosmos": 86_400_000,
    "White Cosmos": 86_400_000, "Blue Cosmos": 86_400_000,
    "Prisma Petal": 86_400_000,
    
    # Bloom Seed - 48h
    "Red Balloon Flower": 172_800_000, "Yellow Balloon Flower": 172_800_000,
    "Purple Balloon Flower": 172_800_000, "White Balloon Flower": 172_800_000,
    "Blue Balloon Flower": 172_800_000,
    "Red Daffodil": 172_800_000, "Yellow Daffodil": 172_800_000,
    "Purple Daffodil": 172_800_000, "White Daffodil": 172_800_000,
    "Blue Daffodil": 172_800_000,
    "Celestial Frostbloom": 172_800_000,
    
    # Lily Seed - 120h (5 giorni)
    "Red Carnation": 432_000_000, "Yellow Carnation": 432_000_000,
    "Purple Carnation": 432_000_000, "White Carnation": 432_000_000,
    "Blue Carnation": 432_000_000,
    "Red Lotus": 432_000_000, "Yellow Lotus": 432_000_000,
    "Purple Lotus": 432_000_000, "White Lotus": 432_000_000,
    "Blue Lotus": 432_000_000,
    "Primula Enigma": 432_000_000,
    
    # Altri semi - 72h (3 giorni)
    "Red Edelweiss": 259_200_000, "Yellow Edelweiss": 259_200_000,
    "Purple Edelweiss": 259_200_000, "White Edelweiss": 259_200_000,
    "Blue Edelweiss": 259_200_000,
    "Red Gladiolus": 259_200_000, "Yellow Gladiolus": 259_200_000,
    "Purple Gladiolus": 259_200_000, "White Gladiolus": 259_200_000,
    "Blue Gladiolus": 259_200_000,
    "Red Lavender": 259_200_000, "Yellow Lavender": 259_200_000,
    "Purple Lavender": 259_200_000, "White Lavender": 259_200_000,
    "Blue Lavender": 259_200_000,
    "Red Clover": 259_200_000, "Yellow Clover": 259_200_000,
    "Purple Clover": 259_200_000, "White Clover": 259_200_000,
    "Blue Clover": 259_200_000,
}

# ── TEMPI MINERALI (millisecondi) ─────────────────────────────────────────────
MINERAL_REGEN_MS = {
    "Stone":      14_400_000,   # 4h
    "Iron":       28_800_000,   # 8h
    "Gold":       86_400_000,   # 24h
    "Crimstone":  86_400_000,   # 24h
    "Sunstone":   259_200_000,  # 72h
    "Oil":        72_000_000    # 20h
}

# ── ALIAS E COMPATIBILITÀ ─────────────────────────────────────────────────────
CROP_ALIASES = {}
FRUIT_ALIASES = {}

# Alias per compatibilità con vecchio codice
FRUIT_GROWTH_MS = FRUIT_REGEN_MS
ALL_CROPS_L = sorted(set(GROWTH_MS.keys()))
AOE_COMBINE_ORDER = "POST"