import os
import logging
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from telegram.ext import (
    Application,
    ContextTypes,
    InlineQueryHandler,
    CallbackQueryHandler,
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot-Konfiguration
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://matchingflobot.onrender.com/webhook")

if not TOKEN:
    raise RuntimeError("❌ TOKEN fehlt!")

# In-Memory Game Store
games = {}

# Telegram App
application = Application.builder().token(TOKEN).updater(None).build()

# === SPIELABLAUF ===
CHOICES = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier"}

# Auswahl-Tastatur erzeugen
def choice_keyboard(game_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=emoji, callback_data=f"{game_id}:{emoji}") for emoji in CHOICES.keys()]
    ])

# Inline-Query verarbeiten
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("⚙️ Inline-Query Verarbeitung gestartet")
    try:
        game_id = str(uuid.uuid4())
        games[game_id] = {}

        results = [
            InlineQueryResultArticle(
                id=game_id,
                title="🎮 Starte Schere, Stein, Papier",
                input_message_content=InputTextMessageContent("👥 Spiel gestartet. Bitte wähle eine Option."),
                reply_markup=choice_keyboard(game_id),
            )
        ]
        await update.inline_query.answer(results, cache_time=0, is_personal=True)
        logger.info("✅ Inline-Query erfolgreich beantwortet")
    except Exception as e:
        logger.exception(f"❌ Fehler bei Inline-Query: {e}")

# Callback bei Button-Klick
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    game_id, emoji = query.data.split(":")

    game = games.get(game_id)
    if not game:
        await query.edit_message_text("❌ Spiel nicht gefunden oder abgelaufen.")
        return

    # Wahl speichern, falls nicht schon gewählt
    if user.id not in game:
        game[user.id] = emoji
    else:
        await query.answer("✅ Deine Wahl wurde bereits registriert.", show_alert=False)
        return

    # Wenn erst ein Spieler gewählt hat
    if len(game) == 1:
        await query.edit_message_text(
            text=f"✅ {user.first_name} hat gewählt.",
            reply_markup=choice_keyboard(game_id),
        )
    # Wenn beide gewählt haben: Ergebnis anzeigen
    elif len(game) == 2:
        players = list(game.items())
        (id1, choice1), (id2, choice2) = players

        name1 = context.bot_data.get(id1, user.full_name)
        name2 = context.bot_data.get(id2, user.full_name)

        result = evaluate_game(choice1, choice2)
        result_text = f"{name1} wählte {CHOICES[choice1]} {choice1}\n{name2} wählte {CHOICES[choice2]} {choice2}\n\n{result}"

        await query.edit_message_text(result_text)
        games.pop(game_id, None)

# Spielauswertung
def evaluate_game(choice1, choice2):
    if choice1 == choice2:
        return "🤝 Unentschieden!"
    wins = {"✂️": "📄", "📄": "🪨", "🪨": "✂️"}
    if wins[choice1] == choice2:
        return "🏆 Spieler 1 gewinnt!"
    else:
        return "🏆 Spieler 2 gewinnt!"

# Handler registrieren
application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback))

# FastAPI-Lebenszyklus
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.shutdown()

# FastAPI App
app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logger.info(f"📬 Webhook empfangen: {data}")
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "✅ MatchingFloBot läuft mit Spielwahl."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
