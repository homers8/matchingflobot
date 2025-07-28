import os
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
)

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Konfiguration ---
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = "https://matchingflobot.onrender.com/webhook"

if not TOKEN:
    raise ValueError("❌ TOKEN muss als Environment Variable gesetzt sein.")

# --- Telegram Application ---
application = Application.builder().token(TOKEN).updater(None).build()

# --- Spielzustände ---
games = {}

# --- Lifespan (Startup + Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt auf: {WEBHOOK_URL}")
    yield
    await application.shutdown()

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)

# --- Telegram Handler Registrierungen ---
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("play", play_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(InlineQueryHandler(handle_inline_query))

# --- /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Willkommen bei MatchingFloBot!\n\nStarte ein Spiel mit /play oder über Inline-Nutzung (@MatchingFloBot)."
    )

# --- /play ---
async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    games[chat_id] = {
        "player1": user_id,
        "player1_choice": None,
        "player2": None,
        "player2_choice": None,
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Schere ✂️", callback_data="choice_scissors"),
        InlineKeyboardButton("Stein 🪨", callback_data="choice_rock"),
        InlineKeyboardButton("Papier 📄", callback_data="choice_paper"),
    ]])

    await update.message.reply_text(
        "🧑‍🎮 Du bist Spieler 1. Warte auf Spieler 2 und wähle deine Option:",
        reply_markup=keyboard
    )

# --- Callback-Handling ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    data = query.data

    if chat_id not in games:
        await query.message.reply_text("⚠️ Keine laufende Partie. Starte mit /play.")
        return

    game = games[chat_id]

    if game["player2"] is None and user_id != game["player1"]:
        game["player2"] = user_id

    if user_id not in [game["player1"], game["player2"]]:
        await query.message.reply_text("⚠️ Du bist kein Teilnehmer dieses Spiels.")
        return

    choice_map = {
        "choice_scissors": "Schere",
        "choice_rock": "Stein",
        "choice_paper": "Papier",
    }

    choice = choice_map.get(data)
    if not choice:
        await query.message.reply_text("⚠️ Ungültige Auswahl.")
        return

    if user_id == game["player1"]:
        if game["player1_choice"]:
            await query.message.reply_text("Du hast bereits gewählt!")
            return
        game["player1_choice"] = choice
    else:
        if game["player2_choice"]:
            await query.message.reply_text("Du hast bereits gewählt!")
            return
        game["player2_choice"] = choice

    await query.answer(f"✅ Deine Wahl: {choice}", show_alert=True)

    if game["player1_choice"] and game["player2_choice"]:
        result = determine_winner(game["player1_choice"], game["player2_choice"])
        await query.message.reply_text(
            f"🎮 Ergebnis:\n"
            f"Spieler 1: {game['player1_choice']}\n"
            f"Spieler 2: {game['player2_choice']}\n\n"
            f"{result}"
        )
        del games[chat_id]
    else:
        await query.message.reply_text("⏳ Warte auf die Wahl des anderen Spielers...")

# --- Gewinnerlogik ---
def determine_winner(choice1, choice2):
    if choice1 == choice2:
        return "🔁 Unentschieden!"
    beats = {
        "Schere": "Papier",
        "Stein": "Schere",
        "Papier": "Stein",
    }
    if beats[choice1] == choice2:
        return "🏆 Spieler 1 gewinnt!"
    else:
        return "🏆 Spieler 2 gewinnt!"

# --- Inline Query ---
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.inline_query.from_user
    logger.info(f"⚙️ Inline-Query von {user.first_name} ({user.id}) mit query='{update.inline_query.query}'")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Schere ✂️", callback_data="choice_scissors"),
        InlineKeyboardButton("Stein 🪨", callback_data="choice_rock"),
        InlineKeyboardButton("Papier 📄", callback_data="choice_paper"),
    ]])

    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="🕹️ Schere-Stein-Papier starten",
            input_message_content=InputTextMessageContent(
                f"{user.first_name} hat ein Spiel gestartet! Wähle deine Option:"
            ),
            reply_markup=keyboard,
            description="Starte ein Spiel mit Auswahlbuttons.",
        )
    ]

    await update.inline_query.answer(results, cache_time=0, is_personal=True)

# --- FastAPI Endpunkte ---
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logger.info(f"📬 Webhook empfangen: {data}")
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "✅ MatchingFloBot is running."

# --- Optionaler manueller Start (lokal) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
