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

        # Spiel initialisieren
        games[game_id] = {
            "players": {},  # user_id: {"name": ..., "choice": ...}
        }

        result = InlineQueryResultArticle(
            id=game_id,
            title="🎮 Starte Schere, Stein, Papier",
            input_message_content=InputTextMessageContent("👥 Spiel gestartet. Bitte wähle eine Option."),
            reply_markup=choice_keyboard(game_id),
        )

        await update.inline_query.answer([result], cache_time=0, is_personal=True)
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

    players = game["players"]

    # Wahl speichern
    if user.id not in players:
        players[user.id] = {
            "name": f"{user.first_name} {user.last_name or ''}".strip(),
            "choice": emoji,
        }
    else:
        await query.answer("✅ Deine Wahl wurde bereits registriert.", show_alert=False)
        return

    # Wenn erst ein Spieler gewählt hat
    if len(players) == 1:
        await query.edit_message_text(
            text=f"✅ {players[user.id]['name']} hat gewählt.",
            reply_markup=choice_keyboard(game_id),
        )

    elif len(players) == 2:
        # Zwei Spieler haben gewählt → Spiel auswerten
        users = list(players.values())
        name1, choice1 = users[0]["name"], users[0]["choice"]
        name2, choice2 = users[1]["name"], users[1]["choice"]

        result = evaluate_game(choice1, choice2)
        text = (
            f"{name1} wählte {CHOICES[choice1]} {choice1}\n"
            f"{name2} wählte {CHOICES[choice2]} {choice2}\n\n"
            f"{result}"
        )
        await query.edit_message_text(text)

        # Hinweis: Spiel bleibt gespeichert (kann später per TTL gelöscht werden)

# Spielauswertung
def evaluate_game(c1, c2):
    if c1 == c2:
        return "🤝 Unentschieden!"
    beats = {"✂️": "📄", "📄": "🪨", "🪨": "✂️"}
    return "🏆 Spieler 1 gewinnt!" if beats[c1] == c2 else "🏆 Spieler 2 gewinnt!"

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
    return "✅ MatchingFloBot läuft mit stabilem Spielablauf."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
