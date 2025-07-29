import os
import logging
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

# Telegram-App ohne Updater
application = Application.builder().token(TOKEN).updater(None).build()

# In-Memory Spielstand
games = {}

# Spieloptionen
CHOICES = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier"}

# Tastatur mit Wahlmöglichkeiten
def choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=emoji, callback_data=f"choice:{emoji}") for emoji in CHOICES]
    ])

# Spielauswertung
def evaluate_game(c1, c2):
    if c1 == c2:
        return "🤝 Unentschieden!"
    beats = {"✂️": "📄", "📄": "🪨", "🪨": "✂️"}
    return "🏆 Spieler 1 gewinnt!" if beats[c1] == c2 else "🏆 Spieler 2 gewinnt!"

# Inline-Query-Handler
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = InlineQueryResultArticle(
            id="start-game",
            title="🎮 Starte Schere, Stein, Papier",
            input_message_content=InputTextMessageContent("👥 Spiel gestartet. Bitte wähle eine Option."),
            reply_markup=choice_keyboard(),
        )
        await update.inline_query.answer([result], cache_time=0, is_personal=True)
        logger.info("✅ Inline-Query beantwortet")
    except Exception as e:
        logger.exception(f"❌ Fehler bei Inline-Query: {e}")

# Button-Klick-Handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data
    if not data.startswith("choice:"):
        return

    emoji = data.split(":")[1]
    game_id = query.inline_message_id  # ← entscheidend!

    if game_id not in games:
        games[game_id] = {"players": {}}

    players = games[game_id]["players"]

    if user.id in players:
        await query.answer("✅ Deine Wahl wurde bereits registriert.", show_alert=False)
        return

    players[user.id] = {
        "name": f"{user.first_name} {user.last_name or ''}".strip(),
        "choice": emoji,
    }

    if len(players) == 1:
        await context.bot.edit_message_text(
            inline_message_id=game_id,
            text=f"✅ {players[user.id]['name']} hat gewählt.\n⏳ Warte auf zweiten Spieler…",
            reply_markup=choice_keyboard(),
        )

    elif len(players) == 2:
        p1, p2 = list(players.values())
        result_text = evaluate_game(p1["choice"], p2["choice"])
        full_text = (
            f"{p1['name']} wählte {CHOICES[p1['choice']]} {p1['choice']}\n"
            f"{p2['name']} wählte {CHOICES[p2['choice']]} {p2['choice']}\n\n"
            f"{result_text}"
        )
        await context.bot.edit_message_text(
            inline_message_id=game_id,
            text=full_text,
        )

# Handler registrieren
application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback))

# FastAPI-Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.shutdown()

# FastAPI-App
app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "✅ MatchingFloBot läuft erfolgreich auf Render."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
