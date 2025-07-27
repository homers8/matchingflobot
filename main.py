import os
import logging
import asyncio
from flask import Flask, request
from telegram import (
    Bot,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
)
from telegram.ext import (
    Application,
    ContextTypes,
    InlineQueryHandler,
    CallbackQueryHandler,
)
from uuid import uuid4

# Logging aktivieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Token und Bot initialisieren
TOKEN = os.environ["BOT_TOKEN"]
bot = Bot(token=TOKEN)
application = Application.builder().token(TOKEN).build()

# Spielzustand und Statistik
games = {}
stats = {}

# Spieloptionen
OPTIONS = {
    "rock": "🪨 Stein",
    "paper": "📄 Papier",
    "scissors": "✂️ Schere",
}

# Spielregeln
WIN_RULES = {
    "rock": "scissors",
    "scissors": "paper",
    "paper": "rock",
}

# HTML escapen
def esc(name):
    return name.replace("<", "&lt;").replace(">", "&gt;")

# Inline-Query-Handler
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query or "Schnick Schnack Schnuck"
    game_id = str(uuid4())

    keyboard = [
        [
            InlineKeyboardButton("🪨", callback_data=f"{game_id}|rock"),
            InlineKeyboardButton("📄", callback_data=f"{game_id}|paper"),
            InlineKeyboardButton("✂️", callback_data=f"{game_id}|scissors"),
        ]
    ]

    result = InlineQueryResultArticle(
        id=game_id,
        title="Spiele Schnick Schnack Schnuck!",
        input_message_content=InputTextMessageContent("Schnick Schnack Schnuck – wählt eure Option!"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    # Initialisiere das Spiel
    games[game_id] = {}

    await update.inline_query.answer([result], cache_time=0)
    logger.info(f"Neues Spiel gestartet: {game_id}")

# Callback-Handler
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name
    await query.answer()

    try:
        game_id, choice = query.data.split("|")
    except Exception:
        return

    if game_id not in games:
        return

    game = games[game_id]

    if user_id in game:
        await query.edit_message_text("Du hast bereits gewählt.")
        return

    game[user_id] = {"name": name, "choice": choice}

    # Wenn beide Spieler gewählt haben
    if len(game) == 2:
        players = list(game.values())
        p1, p2 = players[0], players[1]
        choice1, choice2 = p1["choice"], p2["choice"]
        name1, name2 = esc(p1["name"]), esc(p2["name"])

        result_text = f"{OPTIONS[choice1]} {name1} vs. {OPTIONS[choice2]} {name2}\n\n"

        if choice1 == choice2:
            result_text += "Unentschieden! 🤝"
        elif WIN_RULES[choice1] == choice2:
            result_text += f"{name1} gewinnt! 🏆"
            stats[name1] = stats.get(name1, 0) + 1
        else:
            result_text += f"{name2} gewinnt! 🏆"
            stats[name2] = stats.get(name2, 0) + 1

        # Füge Medaillen hinzu
        for p in [name1, name2]:
            if p in stats:
                result_text += f"\n🥇 {p}: {stats[p]}"

        # "Nochmal spielen"-Button
        again_btn = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("🔁 Nochmal spielen", switch_inline_query_current_chat="Schnick Schnack Schnuck")
        )

        await query.edit_message_text(result_text, reply_markup=again_btn, parse_mode="HTML")

        # Spiel löschen
        del games[game_id]
    else:
        await query.edit_message_text(f"{name} hat gewählt... ⏳")

# Flask Setup
app = Flask(__name__)

@app.route("/")
def index():
    return "MatchingFloBot ist live! 🚀"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    try:
        asyncio.run(application.process_update(update))
    except Exception as e:
        logger.error("❌ Fehler im Webhook:", exc_info=e)
    return "ok", 200

# Telegram Handler registrieren
application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback_query))

# Webhook setzen
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
if WEBHOOK_URL:
    asyncio.run(bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"))
    logger.info("✅ Webhook wurde gesetzt")

# Flask starten
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
