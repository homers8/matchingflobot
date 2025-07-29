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
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery
)
from telegram.ext import (
    Application,
    ContextTypes,
    InlineQueryHandler,
    CallbackQueryHandler
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Bot-Konfiguration
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://matchingflobot.onrender.com/webhook")
if not TOKEN:
    raise RuntimeError("❌ TOKEN fehlt!")

# Session-Speicher (im RAM)
games = {}       # game_id -> {"players": {user_id: choice}, "message_id": int}
statistics = {}  # user_id -> {"wins": int, "losses": int, "draws": int}

# Telegram App
application = Application.builder().token(TOKEN).updater(None).build()

# Spiel-Logik
CHOICES = {
    "rock": "🪨",
    "paper": "📄",
    "scissors": "✂️"
}

WIN_MAP = {
    "rock": "scissors",
    "scissors": "paper",
    "paper": "rock"
}


def evaluate_game(game):
    players = list(game["players"].keys())
    if len(players) < 2:
        return None  # noch nicht alle gewählt

    user1, user2 = players
    choice1 = game["players"][user1]
    choice2 = game["players"][user2]

    emoji1 = CHOICES[choice1]
    emoji2 = CHOICES[choice2]

    result_msg = f"{emoji1} vs {emoji2}\n"

    if choice1 == choice2:
        update_stats(user1, draw=1)
        update_stats(user2, draw=1)
        return result_msg + "🤝 Unentschieden!"
    elif WIN_MAP[choice1] == choice2:
        update_stats(user1, win=1)
        update_stats(user2, loss=1)
        return result_msg + f"🎉 Spieler 1 gewinnt!"
    else:
        update_stats(user2, win=1)
        update_stats(user1, loss=1)
        return result_msg + f"🎉 Spieler 2 gewinnt!"


def update_stats(user_id, win=0, loss=0, draw=0):
    stats = statistics.setdefault(user_id, {"wins": 0, "losses": 0, "draws": 0})
    stats["wins"] += win
    stats["losses"] += loss
    stats["draws"] += draw


def stats_text(user_id):
    stats = statistics.get(user_id, {"wins": 0, "losses": 0, "draws": 0})
    medals = "🏅" * stats["wins"]
    return f"🏆 {stats['wins']} W / ❌ {stats['losses']} L / 🤝 {stats['draws']} D\n{medals or 'Noch keine Medaille'}"


# Inline-Query Handler
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_id = str(uuid.uuid4())
    games[game_id] = {"players": {}, "message_id": None}

    buttons = [
        [
            InlineKeyboardButton("🪨", callback_data=f"{game_id}:rock"),
            InlineKeyboardButton("📄", callback_data=f"{game_id}:paper"),
            InlineKeyboardButton("✂️", callback_data=f"{game_id}:scissors")
        ]
    ]

    result = InlineQueryResultArticle(
        id=game_id,
        title="🎮 Schere, Stein, Papier spielen",
        input_message_content=InputTextMessageContent("🕹 Wähle deine Option:"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await update.inline_query.answer([result], cache_time=0, is_personal=True)


# Callback-Handler für Button-Klicks
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    await query.answer()

    if ":" not in query.data:
        return

    game_id, choice = query.data.split(":")
    user_id = query.from_user.id
    game = games.get(game_id)

    if not game:
        await query.edit_message_text("❌ Dieses Spiel ist abgelaufen.")
        return

    if user_id in game["players"]:
        await query.answer("✅ Auswahl bereits getroffen", show_alert=False)
        return

    game["players"][user_id] = choice

    if len(game["players"]) < 2:
        await query.edit_message_text("⏳ Warte auf den zweiten Spieler...")
    else:
        result_text = evaluate_game(game)
        await query.edit_message_text(result_text + "\n\n" +
                                      stats_text(list(game["players"].keys())[0]) +
                                      "\n" +
                                      stats_text(list(game["players"].keys())[1]))


# Handler registrieren
application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback))

# FastAPI mit Lifespan (Webhook setzen)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.shutdown()

app = FastAPI(lifespan=lifespan)

# Telegram Webhook Endpoint
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logger.info(f"📬 Webhook empfangen: {data}")
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

# Health Check
@app.get("/", response_class=PlainTextResponse)
async def root():
    return "✅ MatchingFloBot läuft!"

# Lokaler Start
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
