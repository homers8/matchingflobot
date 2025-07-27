import os
import asyncio
from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Bot,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    InlineQueryHandler,
)
from telegram.constants import ParseMode

# === Konfiguration ===
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = "https://matchingflobot.onrender.com/webhook"

app = Flask(__name__)
bot = Bot(token=TOKEN)
application = ApplicationBuilder().token(TOKEN).build()

# === Spiel-Variablen (flüchtig, nur Session) ===
games = {}       # {message_id: {user_id: choice}}
game_stats = {}  # {chat_id: {user_id: {"win": int, "loss": int, "draw": int}}}

choices = {
    "rock": "🪨",
    "paper": "📄",
    "scissors": "✂️",
}

def get_result(choice1, choice2):
    if choice1 == choice2:
        return "draw"
    wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    return "win" if wins[choice1] == choice2 else "loss"

def stats_text(chat_id):
    if chat_id not in game_stats:
        return ""
    lines = []
    for user_id, stats in game_stats[chat_id].items():
        lines.append(f"<b>{stats['name']}</b>: 🏆 {stats['win']} | 😢 {stats['loss']} | 🤝 {stats['draw']}")
    return "\n".join(lines)

# === Inline-Spielstart ===
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    keyboard = [
        [
            InlineKeyboardButton("🪨", callback_data="move:rock"),
            InlineKeyboardButton("📄", callback_data="move:paper"),
            InlineKeyboardButton("✂️", callback_data="move:scissors"),
        ]
    ]
    results = [
        {
            "type": "article",
            "id": "ssp1",
            "title": "Schere, Stein, Papier spielen",
            "input_message_content": {
                "message_text": "👥 Spiel gestartet – wähle deine Figur!",
                "parse_mode": "HTML",
            },
            "reply_markup": InlineKeyboardMarkup(keyboard),
        }
    ]
    await update.inline_query.answer(results, cache_time=0)

# === Zugverarbeitung ===
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if not data.startswith("move:"):
        return

    move = data.split(":")[1]
    msg_id = query.message.message_id
    chat_id = query.message.chat.id

    if msg_id not in games:
        games[msg_id] = {}
    if chat_id not in game_stats:
        game_stats[chat_id] = {}
    if user.id not in game_stats[chat_id]:
        game_stats[chat_id][user.id] = {"win": 0, "loss": 0, "draw": 0, "name": user.first_name}

    games[msg_id][user.id] = move

    # Status anzeigen
    players = list(games[msg_id].keys())
    if len(players) == 1:
        await query.edit_message_text(
            f"🕹️ {user.first_name} hat gewählt...\n\nWarte auf den zweiten Spieler.",
            reply_markup=query.message.reply_markup,
        )
    elif len(players) == 2:
        # Auswertung
        p1, p2 = players
        c1, c2 = games[msg_id][p1], games[msg_id][p2]
        name1 = game_stats[chat_id][p1]["name"]
        name2 = game_stats[chat_id][p2]["name"]

        result1 = get_result(c1, c2)
        result2 = get_result(c2, c1)

        if result1 == "win":
            game_stats[chat_id][p1]["win"] += 1
            game_stats[chat_id][p2]["loss"] += 1
            result_text = f"🏆 <b>{name1}</b> gewinnt!"
        elif result1 == "loss":
            game_stats[chat_id][p2]["win"] += 1
            game_stats[chat_id][p1]["loss"] += 1
            result_text = f"🏆 <b>{name2}</b> gewinnt!"
        else:
            game_stats[chat_id][p1]["draw"] += 1
            game_stats[chat_id][p2]["draw"] += 1
            result_text = "🤝 Unentschieden!"

        stats = stats_text(chat_id)
        keyboard = [
            [InlineKeyboardButton("🔁 Nochmal spielen", switch_inline_query_current_chat="")],
        ]
        await query.edit_message_text(
            f"{choices[c1]} {name1} vs {name2} {choices[c2]}\n\n{result_text}\n\n<b>Statistik:</b>\n{stats}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        del games[msg_id]  # Spiel löschen

# === Webhook-Route ===
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.get_event_loop().create_task(application.update_queue.put(update))
        return "OK"
    except Exception as e:
        print(f"❌ Fehler im Webhook: {e}")
        return "Fehler", 500

# === Status-Route ===
@app.route("/")
def index():
    return "Bot läuft ✅"

# === Setup ===
async def setup():
    await application.initialize()
    application.add_handler(InlineQueryHandler(inline_query_handler))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    await bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook wurde gesetzt")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup())

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
