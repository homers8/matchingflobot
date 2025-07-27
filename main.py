import os
import logging
import asyncio
from uuid import uuid4
from flask import Flask, request
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ContextTypes,
    InlineQueryHandler,
    CallbackQueryHandler,
)

# Konfiguration
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = f"https://matchingflobot.onrender.com/webhook"
app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Spielzustände (In-Memory)
games = {}  # session_id: {players, choices, message_id, chat_id, stats}

# Telegram Application
application = Application.builder().token(TOKEN).build()


def get_emoji(choice):
    return {"rock": "🪨", "paper": "📄", "scissors": "✂️"}.get(choice, "")


def determine_winner(choice1, choice2):
    if choice1 == choice2:
        return "draw"
    wins = {
        "rock": "scissors",
        "paper": "rock",
        "scissors": "paper",
    }
    return "player1" if wins[choice1] == choice2 else "player2"


async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = str(uuid4())
    games[session_id] = {
        "players": {},
        "choices": {},
        "message_id": None,
        "chat_id": None,
        "stats": {},
    }

    result = InlineQueryResultArticle(
        id=session_id,
        title="🪨📄✂️ Schere, Stein, Papier spielen",
        input_message_content=InputTextMessageContent("🕹 Spiel gestartet!"),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🪨", callback_data=f"{session_id}|rock"),
                InlineKeyboardButton("📄", callback_data=f"{session_id}|paper"),
                InlineKeyboardButton("✂️", callback_data=f"{session_id}|scissors"),
            ]
        ]),
    )

    await update.inline_query.answer([result], cache_time=0)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session_id, choice = query.data.split("|")
    user = query.from_user
    user_id = user.id
    user_name = user.first_name

    game = games.get(session_id)
    if not game:
        await query.edit_message_text("❌ Dieses Spiel existiert nicht mehr.")
        return

    if user_id not in game["players"]:
        if len(game["players"]) >= 2:
            await query.answer("❗️Nur zwei Spieler erlaubt", show_alert=True)
            return
        game["players"][user_id] = user_name

    if user_id in game["choices"]:
        await query.answer("❗️Du hast bereits gewählt", show_alert=True)
        return

    game["choices"][user_id] = choice
    game["stats"].setdefault(user_id, {"wins": 0, "losses": 0, "draws": 0})

    if len(game["choices"]) < 2:
        await query.answer("✅ Wahl gespeichert. Warte auf den Gegner...")
        return

    # Beide haben gewählt → auswerten
    players = list(game["choices"].keys())
    c1, c2 = game["choices"][players[0]], game["choices"][players[1]]
    name1, name2 = game["players"][players[0]], game["players"][players[1]]
    emoji1, emoji2 = get_emoji(c1), get_emoji(c2)
    result = determine_winner(c1, c2)

    if result == "draw":
        game["stats"][players[0]]["draws"] += 1
        game["stats"][players[1]]["draws"] += 1
        result_text = f"🤝 Unentschieden!\n\n{name1} {emoji1} vs {emoji2} {name2}"
    elif result == "player1":
        game["stats"][players[0]]["wins"] += 1
        game["stats"][players[1]]["losses"] += 1
        result_text = f"🎉 {name1} gewinnt!\n\n{emoji1} schlägt {emoji2}"
    else:
        game["stats"][players[1]]["wins"] += 1
        game["stats"][players[0]]["losses"] += 1
        result_text = f"🎉 {name2} gewinnt!\n\n{emoji2} schlägt {emoji1}"

    stats1 = game["stats"][players[0]]
    stats2 = game["stats"][players[1]]
    score_text = (
        f"\n\n🏅 Statistik:\n"
        f"{name1}: {stats1['wins']}W / {stats1['losses']}L / {stats1['draws']}D\n"
        f"{name2}: {stats2['wins']}W / {stats2['losses']}L / {stats2['draws']}D"
    )

    await query.edit_message_text(
        result_text + score_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔁 Nochmal spielen", switch_inline_query=""),
        ]])
    )


# Webhook-Endpunkt für Telegram
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    except Exception as e:
        logger.error("❌ Fehler im Webhook:", exc_info=e)
    return "OK"


# Root-Route für Render-Healthcheck
@app.route("/", methods=["GET", "HEAD"])
def index():
    return "✅ Bot läuft"


if __name__ == "__main__":
    # Telegram-Webhook setzen
    import telegram
    bot = telegram.Bot(token=TOKEN)
    try:
        bot.delete_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        print("✅ Webhook wurde gesetzt")
    except Exception as e:
        print(f"❌ Fehler beim Setzen des Webhooks: {e}")

    # WICHTIG: Telegram-App manuell initialisieren
    asyncio.run(application.initialize())

    # Starte Flask-Server
    app.run(host="0.0.0.0", port=10000)
