import logging
import asyncio
import json
import os
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.error import TelegramError

from storage import get_land, set_land, get_notifications, set_notifications, get_all_subscribed, get_api_key, set_api_key, validate_api_key

# In-memory state: quale utente sta inviando la SFL API key in questo momento
awaiting_api_key = {}  # chat_id -> True

from tempo import in_corso_forland
from notifications import NotificationManager
from whitelist import init_whitelist, is_owner, is_allowed, is_banned, add_user, ban_user, unban_user, list_allowed_detailed, note_seen
from config import BOT_TOKEN, ADMIN_IDS
from isola_fluttuante import render_isola_fluttuante

# ← NUOVI IMPORT PER STATISTICHE
from stats_tracker import start_tracker_for_farm, stop_all_trackers

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sflbot")

MENU_USER = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🔑 Imposta API Key")],
        [KeyboardButton("📋 In corso")],
        [KeyboardButton("Statistiche"), KeyboardButton("Isola fluttuante")],
        [KeyboardButton("⚙️ Impostazioni")],
    ],
    resize_keyboard=True
)

MENU_ADMIN = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🔑 Imposta API Key")],
        [KeyboardButton("📋 In corso")],
        [KeyboardButton("Statistiche"), KeyboardButton("Isola fluttuante")],
        [KeyboardButton("⚙️ Impostazioni")],
        [KeyboardButton("👥 Whitelist"), KeyboardButton("🔨 Ban Utenti")],
    ],
    resize_keyboard=True
)

MENU_ADMIN_REGISTERED = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📋 In corso")],
        [KeyboardButton("Statistiche"), KeyboardButton("Isola fluttuante")],
        [KeyboardButton("⚙️ Impostazioni")],
        [KeyboardButton("👥 Whitelist"), KeyboardButton("🔨 Ban Utenti")],
    ],
    resize_keyboard=True
)

def _menu_for(user):
    """Costruisce il menu principale. Mostra pulsante API Key SOLO se non registrato."""
    try:
        from storage import get_api_key
    except Exception:
        get_api_key = lambda _: None

    uid = int(getattr(user, "id", 0) or 0)
    try:
        admin_ids = {int(x) for x in ADMIN_IDS} if ADMIN_IDS else set()
    except Exception:
        admin_ids = set(ADMIN_IDS or [])

    is_admin = is_owner(uid) or (uid in admin_ids)

    # Verifica se l'utente ha già una API key
    try:
        api_key = get_api_key(uid)
    except Exception:
        api_key = None

    # Menu admin (con pulsante API Key solo se non registrato)
    if is_admin:
        if api_key:
            # Admin registrato - menu completo senza pulsante API Key
            return MENU_ADMIN_REGISTERED
        else:
            # Admin non registrato - con pulsante API Key
            return MENU_ADMIN

    # Menu utente normale
    if api_key:
        # Utente registrato - menu senza pulsante API Key
        kb = [
            [KeyboardButton("📋 In corso")],
            [KeyboardButton("Statistiche"), KeyboardButton("Isola fluttuante")],
            [KeyboardButton("⚙️ Impostazioni")],
        ]
    else:
        # Utente non registrato - con pulsante API Key
        kb = [
            [KeyboardButton("🔑 Imposta API Key")],
            [KeyboardButton("📋 In corso")],
            [KeyboardButton("Statistiche"), KeyboardButton("Isola fluttuante")],
            [KeyboardButton("⚙️ Impostazioni")],
        ]

    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def _owner_guard(update: Update) -> bool:
    user = update.effective_user

    if not is_owner(user.id):
        try:
            update.message.reply_text(
                "Solo l'owner può usare questo comando.",
                reply_markup=_menu_for(user)
            )
        except Exception:
            pass
        return False

    return True

def _guard_or_hint(update: Update) -> bool:
    user = update.effective_user

    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = (user.username or "").strip()

    note_seen(user.id, name=name, username=username)

    if is_allowed(user.id):
        return True

    shown_name = name or (("@" + username) if username else "")
    txt = (
        "🚫 *Non sei autorizzato a usare questo bot.*\n\n"
        f"User: {shown_name}\n"
        f"user_id: `{user.id}`\n"
        "Contatta l'admin per essere whitelisted."
    )

    try:
        update.message.reply_text(
            txt, parse_mode=ParseMode.MARKDOWN, reply_markup=_menu_for(user)
        )
    except Exception:
        pass

    return False

notification_managers: dict[str, NotificationManager] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = (user.username or "").strip()

    note_seen(user.id, name=name, username=username)

    if not is_banned(user.id):
        add_user(user.id, name=name, username=username)

    menu = _menu_for(user)

    if context.args:
        api_key = context.args[0].strip()
        
        try:
            # Valida e salva la API key
            from storage import set_api_key, validate_api_key
            
            if not validate_api_key(api_key):
                await update.message.reply_text(
                    "❌ API Key non valida!\n\n"
                    "Assicurati di copiare la chiave completa da Sunflower Land.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=menu
                )
                return
            
            set_api_key(chat.id, api_key)
            land_id = get_land(chat.id)
            
            await update.message.reply_text(
                f"👋 Benvenuto {name or (('@' + username) if username else 'utente')}!\n\n"
                f"✅ API Key salvata\n"
                f"🆔 Farm ID: `{land_id}`\n"
                "🔔 Notifiche attivate automaticamente\n\n"
                "*Cosa puoi fare:*\n"
                "• 📋 Vedere cosa è *In corso* nella farm\n"
                "• ⏰ Ricevere notifiche quando le risorse sono pronte\n"
                "• 📊 Vedere le *Statistiche* giornaliere\n\n"
                "Usa i pulsanti qui sotto per iniziare!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=menu
            )

            await ensure_notification_manager(context.application, chat.id, land_id)
            # ← AVVIA STATS TRACKER
            await start_tracker_for_farm(land_id, chat.id)
            
        except Exception as e:
            log.error(f"Errore nel salvare API key: {e}")
            await update.message.reply_text(
                "❌ Errore nel salvare la API Key. Riprova.",
                reply_markup=menu
            )
        return

    await update.message.reply_text(
        f"👋 Benvenuto {name or (('@'+username) if username else 'utente')}!\n\n"
        "*Per iniziare, imposta la tua SFL API Key:*\n\n"
        "1. *🔑 Imposta API Key* (pulsante qui sotto)\n"
        "2. `/start TUA_API_KEY` (comando rapido)\n\n"
        "*Dove trovare la API Key:*\n"
        "• Vai su Sunflower Land\n"
        "• Apri le impostazioni ⚙️\n"
        "• Copia la tua API Key\n\n"
        "⚠️ *IMPORTANTE:* La API Key è personale, non condividerla!\n\n"
        "Una volta impostata, riceverai notifiche automatiche! 🔔",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu
    )

async def imposta_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il pulsante 'Imposta API Key'"""
    if not _guard_or_hint(update):
        return

    global awaiting_api_key
    chat_id = update.effective_chat.id
    awaiting_api_key[chat_id] = True

    await update.message.reply_text(
        "🔑 *Imposta la tua SFL API Key*\n\n"
        "Invia la tua API Key di Sunflower Land.\n\n"
        "*Dove trovarla:*\n"
        "• Apri Sunflower Land\n"
        "• Vai nelle impostazioni ⚙️\n"
        "• Copia la tua API Key\n\n"
        "⚠️ *ATTENZIONE:*\n"
        "• Questa chat è privata e sicura\n"
        "• La chiave verrà salvata cifrata\n"
        "• Non condividere la tua API Key con altri\n"
        "• Il messaggio verrà eliminato per sicurezza\n\n"
        "Invia la tua API Key ora:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )

async def set_api_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /setkey"""
    if not _guard_or_hint(update):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Uso corretto: `/setkey TUA_API_KEY`\n\n"
            "⚠️ Ricorda: non condividere mai la tua API Key!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
        return

    api_key = context.args[0].strip()
    chat_id = update.effective_chat.id
    
    try:
        from storage import set_api_key, validate_api_key
        
        # Valida la API key
        if not validate_api_key(api_key):
            await update.message.reply_text(
                "❌ API Key non valida!\n\n"
                "Assicurati di copiare la chiave completa da Sunflower Land.",
                reply_markup=_menu_for(update.effective_user)
            )
            return
        
        # Salva la API key (cifrata)
        set_api_key(chat_id, api_key)
        land_id = get_land(chat_id)
        
        # Elimina il messaggio con la API key per sicurezza
        try:
            await update.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ API Key salvata con successo!\n"
                 f"🆔 Farm ID: `{land_id}`\n"
                 "🔔 Notifiche attivate automaticamente!\n\n"
                 "Il tuo messaggio è stato eliminato per sicurezza.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )

        await ensure_notification_manager(context.application, chat_id, land_id)
        # ← AVVIA STATS TRACKER
        await start_tracker_for_farm(land_id, chat_id)
        
    except ValueError as e:
        log.error(f"Errore validazione API key: {e}")
        await update.message.reply_text(
            f"❌ {str(e)}",
            reply_markup=_menu_for(update.effective_user)
        )
    except Exception as e:
        log.error(f"Errore nel salvare la API key: {e}")
        await update.message.reply_text(
            "❌ Errore nel salvare la API key. Riprova.",
            reply_markup=_menu_for(update.effective_user)
        )

async def payload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salva il payload API per debugging nella cartella data/"""
    if not _guard_or_hint(update):
        return

    chat_id = update.effective_chat.id
    land = get_land(chat_id)

    if not land:
        await update.message.reply_text(
            "❌ Devi prima impostare la tua API Key!",
            reply_markup=_menu_for(update.effective_user)
        )
        return

    try:
        # Fetch del payload
        from api import fetch_farm_with_user_key
        payload, url, timestamp = await fetch_farm_with_user_key(land, chat_id, force=True)
        
        # Crea cartella data/ se non esiste
        if not os.path.exists("data"):
            os.makedirs("data")
        
        # Crea nome file con data/ora
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"payload_{land}_{timestamp_str}.json"
        filepath = os.path.join("data", filename)
        
        # Salva il file in data/
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        
        # Invia il file all'utente
        await update.message.reply_document(
            document=open(filepath, 'rb'),
            filename=filename,
            caption=f"📁 Payload API per farm {land}\n📍 Salvato in: data/{filename}",
            reply_markup=_menu_for(update.effective_user)
        )
        
        log.info(f"Payload salvato in: {filepath}")
        
    except Exception as e:
        log.error(f"Errore in /payload: {e}")
        await update.message.reply_text(
            f"❌ Errore nel recuperare il payload: {str(e)}",
            reply_markup=_menu_for(update.effective_user)
        )

async def in_corso_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il pulsante 'In corso'"""
    if not _guard_or_hint(update):
        return

    chat_id = update.effective_chat.id
    land = get_land(chat_id)

    if not land:
        await update.message.reply_text(
            "❌ Devi prima impostare la tua API Key!\n\n"
            "Usa il pulsante *🔑 Imposta API Key* qui sotto.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
        return

    try:
        msg = await in_corso_forland(land, chat_id)
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
    except Exception as e:
        log.error(f"Errore in in_corso_handler: {e}")
        await update.message.reply_text(
            "❌ Errore nel recuperare i dati della farm.",
            reply_markup=_menu_for(update.effective_user)
        )

# Nuovo handler statistiche per main.py

async def statistiche_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il pulsante 'Statistiche' - Confronto con snapshot delle 1:00"""
    if not _guard_or_hint(update):
        return

    chat_id = update.effective_chat.id
    land = get_land(chat_id)

    if not land:
        await update.message.reply_text(
            "❌ Devi prima impostare la tua API Key!\n\n"
            "Usa il pulsante *🔑 Imposta API Key* qui sotto.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
        return

    try:
        # Messaggio di caricamento
        loading_msg = await update.message.reply_text(
            "⏳ Analizzando farm...",
            reply_markup=_menu_for(update.effective_user)
        )
        
        # Calcola delta 24h
        from farm_delta_24h import calculate_delta_today
        result = await calculate_delta_today(land, chat_id)
        
        # Cancella messaggio di caricamento
        try:
            await loading_msg.delete()
        except Exception:
            pass
        
        # Invia risultato
        await update.message.reply_text(
            result["summary"],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
        
    except Exception as e:
        log.error(f"Errore in statistiche_handler: {e}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        
        try:
            await loading_msg.delete()
        except Exception:
            pass
        
        await update.message.reply_text(
            "❌ Errore nel recuperare le statistiche.\n"
            "Riprova tra qualche secondo.",
            reply_markup=_menu_for(update.effective_user)
        )

async def isola_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il pulsante 'Isola fluttuante'"""
    if not _guard_or_hint(update):
        return

    chat_id = update.effective_chat.id
    land = get_land(chat_id)

    if not land:
        await update.message.reply_text(
            "❌ Devi prima impostare la tua API Key!\n\n"
            "Usa il pulsante *🔑 Imposta API Key* qui sotto.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
        return

    try:
        msg = await render_isola_fluttuante(land, chat_id)
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_menu_for(update.effective_user)
        )
    except Exception as e:
        log.error(f"Errore in isola_handler: {e}")
        await update.message.reply_text(
            "❌ Errore nel recuperare i dati dell'isola.",
            reply_markup=_menu_for(update.effective_user)
        )

async def impostazioni_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il pulsante 'Impostazioni'"""
    if not _guard_or_hint(update):
        return

    chat_id = update.effective_chat.id
    notif_enabled = get_notifications(chat_id)
    
    # Verifica se l'utente ha una API key
    from storage import has_api_key
    has_key = has_api_key(chat_id)

    kb = [
        [KeyboardButton("🔔 Attiva notifiche" if not notif_enabled else "🔕 Disattiva notifiche")],
    ]
    
    # Se l'utente ha una API key, mostra opzione per cambiarla
    if has_key:
        kb.append([KeyboardButton("🔄 Cambia API Key")])
    
    kb.append([KeyboardButton("◀️ Torna al menu")])

    await update.message.reply_text(
        "⚙️ *Impostazioni*\n\n"
        f"Notifiche: {'🔔 Attive' if notif_enabled else '🔕 Disattivate'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle delle notifiche"""
    if not _guard_or_hint(update):
        return

    chat_id = update.effective_chat.id
    current = get_notifications(chat_id)
    set_notifications(chat_id, not current)

    await update.message.reply_text(
        f"✅ Notifiche {'attivate' if not current else 'disattivate'}!",
        reply_markup=_menu_for(update.effective_user)
    )

async def whitelist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per la gestione whitelist (solo admin)"""
    if not _owner_guard(update):
        return

    users = list_allowed_detailed()
    if not users:
        msg = "📝 *Whitelist*\n\nNessun utente nella whitelist."
    else:
        msg = "📝 *Whitelist*\n\n"
        for u in users:
            msg += f"• {u['name'] or 'N/A'} (@{u['username'] or 'N/A'}) - ID: `{u['user_id']}`\n"

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_menu_for(update.effective_user)
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler generico per i messaggi di testo"""
    global awaiting_api_key
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # Se l'utente sta inviando la API key
    if chat_id in awaiting_api_key and awaiting_api_key[chat_id]:
        awaiting_api_key[chat_id] = False
        
        try:
            from storage import set_api_key, validate_api_key
            
            api_key = text.strip()
            
            # Valida la API key
            if not validate_api_key(api_key):
                await update.message.reply_text(
                    "❌ API Key non valida!\n\n"
                    "Assicurati di copiare la chiave completa da Sunflower Land.\n"
                    "Formato atteso: `sfl.xxxxx.xxxxx`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=_menu_for(update.effective_user)
                )
                return
            
            # Salva la API key (cifrata)
            set_api_key(chat_id, api_key)
            land_id = get_land(chat_id)
            
            # Elimina il messaggio con la API key per sicurezza
            try:
                await update.message.delete()
            except Exception:
                pass
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ API Key salvata con successo!\n"
                     f"🆔 Farm ID: `{land_id}`\n"
                     "🔔 Notifiche attivate automaticamente!\n\n"
                     "Il tuo messaggio è stato eliminato per sicurezza.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_menu_for(update.effective_user)
            )
            
            await ensure_notification_manager(context.application, chat_id, land_id)
            # ← AVVIA STATS TRACKER
            await start_tracker_for_farm(land_id, chat_id)
            
        except ValueError as e:
            log.error(f"Errore validazione API key: {e}")
            await update.message.reply_text(
                f"❌ {str(e)}",
                reply_markup=_menu_for(update.effective_user)
            )
        except Exception as e:
            log.error(f"Errore nel salvare la API key: {e}")
            await update.message.reply_text(
                "❌ Errore nel salvare la API key. Riprova.",
                reply_markup=_menu_for(update.effective_user)
            )
        return

    # Gestione pulsanti menu
    if text == "🔑 Imposta API Key":
        await imposta_api_key(update, context)
    elif text == "🔐 Registra API Key":
        await imposta_api_key(update, context)
    elif text == "🔄 Cambia API Key":
        await imposta_api_key(update, context)
    elif text == "📋 In corso":
        await in_corso_handler(update, context)
    elif text == "Statistiche":
        await statistiche_handler(update, context)
    elif text == "Isola fluttuante":
        await isola_handler(update, context)
    elif text == "⚙️ Impostazioni":
        await impostazioni_handler(update, context)
    elif text in ["🔔 Attiva notifiche", "🔕 Disattiva notifiche"]:
        await toggle_notifications(update, context)
    elif text == "👥 Whitelist":
        await whitelist_handler(update, context)
    elif text == "◀️ Torna al menu":
        await update.message.reply_text(
            "Menu principale:",
            reply_markup=_menu_for(update.effective_user)
        )

async def ensure_notification_manager(app, chat_id: int, land_id: str):
    global notification_managers
    if not get_notifications(chat_id):
        log.info(f"Notifiche disattivate per {chat_id}")
        return
    if land_id in notification_managers:
        manager = notification_managers[land_id]
        if chat_id not in manager.chat_ids:
            manager.chat_ids.append(chat_id)
            log.info(f"Aggiunto chat_id {chat_id} al manager esistente per farm {land_id}")
        return

    async def bot_send(cid: int, text: str):
        try:
            await app.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            log.error(f"Errore invio a {cid}: {e}")

    manager = NotificationManager([chat_id], land_id, bot_send)
    notification_managers[land_id] = manager
    await manager.start()
    log.info(f"Creato nuovo NotificationManager per farm {land_id}")

async def init_all_notification_managers(app):
    """Inizializza i notification manager per tutti gli utenti iscritti"""
    global notification_managers
    try:
        subscribed = get_all_subscribed()  # Returns List[Tuple[int, str]]
        log.info(f"Caricamento {len(subscribed)} utenti con notifiche attive...")
        
        for chat_id, land_id in subscribed:
            if land_id:
                try:
                    await ensure_notification_manager(app, chat_id, land_id)
                    log.info(f"✅ Manager caricato per chat {chat_id}, farm {land_id}")
                    await asyncio.sleep(3)  # ← AGGIUNGI QUESTA RIGA
                except Exception as e:
                    log.error(f"❌ Errore caricamento manager per {chat_id}: {e}")
        
        log.info(f"✅ Inizializzati {len(notification_managers)} notification managers")
    except Exception as e:
        log.error(f"Errore inizializzazione notification managers: {e}")

# ← NUOVA FUNZIONE: Inizializza stats trackers
async def init_all_stats_trackers(app):
    """Inizializza i tracker statistiche per tutti gli utenti iscritti"""
    try:
        subscribed = get_all_subscribed()
        log.info(f"Inizializzazione stats tracker per {len(subscribed)} farm...")
        
        # Circa riga 762-769  
        for chat_id, land_id in subscribed:
            if land_id:
                try:
                    await start_tracker_for_farm(land_id, chat_id)
                    log.info(f"✅ Stats tracker avviato per farm {land_id}")
                    await asyncio.sleep(3)  # ← AGGIUNGI QUESTA RIGA
                except Exception as e:
                    log.error(f"❌ Errore avvio tracker per farm {land_id}: {e}")
        
        log.info(f"✅ Inizializzati stats tracker")
    except Exception as e:
        log.error(f"Errore inizializzazione stats trackers: {e}")

async def main():
    global notification_managers
    if not BOT_TOKEN:
        raise SystemExit("Errore: TELEGRAM_BOT_TOKEN mancante in .env")

    init_whitelist(ADMIN_IDS[0] if ADMIN_IDS else None)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Registrazione handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setkey", set_api_key_command))
    app.add_handler(CommandHandler("payload", payload_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    async def shutdown():
        log.info("Shutdown in corso...")
        
        # ← FERMA STATS TRACKERS
        await stop_all_trackers()
        
        for land_id, manager in list(notification_managers.items()):
            try:
                await manager.stop()
                log.info(f"Manager {land_id} fermato")
            except Exception as e:
                log.error(f"Errore stop manager {land_id}: {e}")

        try:
            if app.updater and app.updater.running:
                await app.updater.stop()
        except Exception:
            pass

        try:
            if app.running:
                await app.stop()
        except Exception:
            pass

        try:
            await app.shutdown()
        except Exception:
            pass

    try:
        log.info("Bot avviato!")
        await app.initialize()
        await app.start()
        
        # Inizializza notification managers per tutti gli utenti
        await init_all_notification_managers(app)
        
        # ← INIZIALIZZA STATS TRACKERS
        await init_all_stats_trackers(app)
        
        await app.updater.start_polling()

        while True:
            await asyncio.sleep(3600)

    except KeyboardInterrupt:
        log.info("Bot fermato dall'utente")

    except Exception as e:
        log.error(f"Errore imprevisto: {e}")

    finally:
        await shutdown()

def run_bot():
    asyncio.run(main())

if __name__ == "__main__":
    run_bot()