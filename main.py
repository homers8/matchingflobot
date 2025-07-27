import os
import logging
import asyncio
from flask import Flask, request
from telegram import (
    InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton, Update
)
from telegram.ext import (
    Application, ContextTypes, InlineQueryHandler,
    CallbackQueryHandler
)
from uuid import uuid4

# === Bot-Konfiguration ===
TOKEN = os.environ.get("BOT_TOKEN") or "DEIN_BOT_TOKEN_HIER"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or "https://matchingflobot.onrender.com/webhook"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

application = Application.builder().token(TOKEN).build()

# === Spiellogik ===

games = {}
stats = {}

CHOICES = {
    "rock": "🪨 Stein",
    "paper": "📄 Papier",
    "scissors": "✂️ Schere"
}

WINNING_COMBOS = {
    ("rock", "scissors"),
    ("paper", "rock"),
    ("scissors", "paper")
}

def evaluate_game(choice1, choice2):
    if choice1 == choice2:
        return 0
    if (choice1, choice2) in WINNING_COMBOS:
        return 1
    return 2

def get_medal(wins):
    if wins >= 5:
        return "🏆"
    elif wins >= 3:
        return "🥈"
    elif wins >= 1:
        return "🥉"
    else:
        return ""

# === Inline-Handler ===

async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_id = str(uuid4())
    games[query_id] = {
        "players": {},
        "votes": {},
        "message_id": None
    }

    button_texts = ["🪨", "📄", "✂️"]
    button_data = ["rock", "paper", "scissors"]

    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"{query_id}|{data}")]
        for text, data in zip(button_texts, button_data)
    ]

    result = InlineQueryResultArticle(
        id=query_id,
        title="Schere, Stein, Papier spielen",
        input_message_content=InputTextMessageContent("Wähle deine Waffe:"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.inline_query.answer([result], cache_time=0)

# === Button-Handler ===

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        query_id, choice = query.data.split("|")
        user = query.from_user
        game = games.get(query_id)

        if not game:
            await query.edit_message_text("❌ Spiel nicht gefunden.")
            return

        user_id = user.id
        if user_id in game["votes"]:
            await query.answer("Du hast bereits gewählt!", show_alert=True)
            return

        game["votes"][user_id] = choice
        game["players"][user_id] = user.first_name

        # Zwei Spieler?
        if len(game["votes"]) == 2:
            ids = list(game["votes"].keys())
            c1, c2 = game["votes"][ids[0]], game["votes"][ids[1]]
            n1, n2 = game["players"][ids[0]], game["players"][ids[1]]

            result = evaluate_game(c1, c2)
            stats.setdefault(ids[0], {"wins": 0})
            stats.setdefault(ids[1], {"wins": 0})

            if result == 0:
                text = f"🤝 Unentschieden!\nBeide wählten {CHOICES[c1]}"
            elif result == 1:
                stats[ids[0]]["wins"] += 1
                text = f"{CHOICES[c1]} schlägt {CHOICES[c2]}!\n🏅 {n1} gewinnt! {get_medal(stats[ids[0]]['wins'])}"
            else:
                stats[ids[1]]["wins"] += 1
                text = f"{CHOICES[c2]} schlägt {CHOICES[c1]}!\n🏅 {n2} gewinnt! {get_medal(stats[ids[1]]['wins'])}"

            again_button = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔁 Nochmal spielen", switch_inline_query_current_chat="")
            ]])

            await query.edit_message_text(text, reply_markup=again_button)
            del games[query_id]
        else:
            await query.edit_message_text("✅ Deine Wahl wurde gespeichert.\nWarte auf den Mitspieler...")

    except Exception as e:
        logging.exception("Fehler im Callback:", exc_info=e)
        await query.edit_message_text("❌ Ein Fehler ist aufgetreten.")

# === Webhook-Route ===

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    except Exception as e:
        logging.exception("❌ Fehler im Webhook:", exc_info=e)
    return "OK"

@app.route("/", methods=["GET"])
def home():
    return "MatchingFloBot läuft ✅"

# === Startup-Funktionen ===

async def setup_webhook():
    await application.bot.delete_webhook()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook wurde gesetzt")

async def main():
    await application.initialize()
    await setup_webhook()

# === Handler registrieren ===

application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback_query))

# === Main Startpunkt ===

if __name__ == "__main__":
    asyncio.run(main())
    app.run(host="0.0.0.0", port=10000)
