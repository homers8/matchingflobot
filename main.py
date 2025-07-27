import os
import asyncio
from flask import Flask, request
from telegram import (
    InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton,
    InlineKeyboardMarkup, Update
)
from telegram.ext import (
    Application, ApplicationBuilder, ContextTypes,
    InlineQueryHandler, CallbackQueryHandler
)
from uuid import uuid4

# === Konfiguration ===
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = f"https://matchingflobot.onrender.com/webhook"

# === Zustände speichern ===
games = {}       # message_id -> {player_id: choice, ...}
user_stats = {}  # user_id -> {"wins": x, "losses": y, "draws": z}

# === Flask Setup ===
app = Flask(__name__)
application = ApplicationBuilder().token(TOKEN).build()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
        return "OK"
    except Exception as e:
        print(f"❌ Fehler im Webhook: {e}")
        return "Fehler", 500

@app.route('/')
def index():
    return "Bot läuft ✅"

# === Spiel-Logik ===

CHOICES = {
    "rock": "🪨 Stein",
    "paper": "📄 Papier",
    "scissors": "✂️ Schere"
}

BEATS = {
    "rock": "scissors",
    "scissors": "paper",
    "paper": "rock"
}

def build_choice_keyboard(game_id, user_id):
    keyboard = [
        [InlineKeyboardButton(CHOICES[c], callback_data=f"{game_id}|{c}")]
        for c in CHOICES
    ]
    return InlineKeyboardMarkup(keyboard)

def build_result_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Nochmal spielen", switch_inline_query="")]
    ])

async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_id = str(uuid4())
    message_content = InputTextMessageContent("Wähle deine Figur:")
    keyboard = build_choice_keyboard(query_id, update.inline_query.from_user.id)

    result = InlineQueryResultArticle(
        id=query_id,
        title="Schere, Stein, Papier spielen",
        input_message_content=message_content,
        reply_markup=keyboard
    )
    await update.inline_query.answer([result], cache_time=0)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    game_id, choice = query.data.split("|")
    user = query.from_user
    message = query.message

    if game_id not in games:
        games[game_id] = {}
    players = games[game_id]

    if user.id in players:
        await query.edit_message_text(
            text="⏳ Du hast bereits gewählt. Warte auf den anderen Spieler...",
            reply_markup=None
        )
        return

    players[user.id] = choice

    if len(players) < 2:
        await query.edit_message_text(
            text="🕹️ Spieler 1 hat gewählt. Warte auf Spieler 2...",
            reply_markup=None
        )
        return

    # Beide haben gewählt → auswerten
    (id1, id2), (c1, c2) = list(players.items())[0], list(players.items())[1]

    name1 = (await context.bot.get_chat(id1)).first_name
    name2 = (await context.bot.get_chat(id2)).first_name

    def winner_text():
        if c1 == c2:
            return "🤝 Unentschieden!"
        elif BEATS[c1] == c2:
            return f"🏆 {name1} gewinnt!"
        else:
            return f"🏆 {name2} gewinnt!"

    # Statistik
    def update_stats(winner_id, loser_id):
        for uid in [winner_id, loser_id]:
            if uid not in user_stats:
                user_stats[uid] = {"wins": 0, "losses": 0, "draws": 0}
        if c1 == c2:
            user_stats[id1]["draws"] += 1
            user_stats[id2]["draws"] += 1
        elif BEATS[c1] == c2:
            user_stats[id1]["wins"] += 1
            user_stats[id2]["losses"] += 1
        else:
            user_stats[id2]["wins"] += 1
            user_stats[id1]["losses"] += 1

    update_stats(id1, id2)

    stats1 = user_stats[id1]
    stats2 = user_stats[id2]

    result_text = (
        f"{name1} wählte {CHOICES[c1]}\n"
        f"{name2} wählte {CHOICES[c2]}\n\n"
        f"{winner_text()}\n\n"
        f"📊 {name1}: {stats1['wins']}W / {stats1['losses']}L / {stats1['draws']}U\n"
        f"📊 {name2}: {stats2['wins']}W / {stats2['losses']}L / {stats2['draws']}U"
    )

    await query.edit_message_text(
        text=result_text,
        reply_markup=build_result_keyboard()
    )

# === Setup ===
async def setup():
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook wurde gesetzt")

application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback_query))

if __name__ == "__main__":
    asyncio.run(setup())
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
