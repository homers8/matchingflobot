import os
import logging
import time
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
application = Application.builder().token(TOKEN).updater(None).build()

CHOICES = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier"}
games = {}  # game_id → { players: {user_id → {"name": ..., "choice": ...}}, timestamp }
session_stats = {}  # frozenset(user_id1, user_id2) → {user_id → {"name": ..., "win": ..., "lose": ..., "draw": ...}}

def choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=emoji, callback_data=f"choice:{emoji}") for emoji in CHOICES]
    ])

def play_again_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🔁 Nochmal spielen", switch_inline_query_current_chat="")]
    ])

def evaluate_game(choice1, choice2):
    if choice1 == choice2:
        return None
    beats = {"✂️": "📄", "📄": "🪨", "🪨": "✂️"}
    return True if beats[choice1] == choice2 else False

def cleanup_old_games():
    now = time.time()
    to_delete = [gid for gid, g in games.items() if now - g.get("timestamp", 0) > 600]
    for gid in to_delete:
        del games[gid]
        logger.info(f"🧹 Altes Spiel gelöscht: {gid}")

async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_old_games()
    result = InlineQueryResultArticle(
        id="start-game",
        title="🎮 Starte Schere, Stein, Papier",
        input_message_content=InputTextMessageContent("👥 Spiel gestartet. Bitte wähle eine Option."),
        reply_markup=choice_keyboard(),
    )
    await update.inline_query.answer([result], cache_time=0, is_personal=True)
    logger.info("✅ Inline-Query beantwortet")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    name = user.first_name
    data = query.data
    game_id = query.inline_message_id

    if not data.startswith("choice:"):
        return

    emoji = data.split(":")[1]

    # Spiel laden oder neu anlegen
    game = games.setdefault(game_id, {"players": {}, "timestamp": time.time()})
    players = game["players"]
    game["timestamp"] = time.time()  # Refresh timestamp bei Interaktion

    if user_id in players:
        await query.answer("✅ Deine Wahl wurde bereits registriert.", show_alert=False)
        return

    players[user_id] = {"name": name, "choice": emoji}
    logger.info(f"👤 {name} ({user_id}) hat gewählt: {emoji}")

    if len(players) == 1:
        await context.bot.edit_message_text(
            inline_message_id=game_id,
            text=f"✅ {name} hat gewählt.\n⏳ Warte auf zweiten Spieler…",
            reply_markup=choice_keyboard(),
        )
        return

    if len(players) < 2:
        return  # Sicherheitscheck

    # Zwei Spieler vorhanden → auswerten
    (id1, p1), (id2, p2) = players.items()
    result_text = ""
    stats_key = frozenset([id1, id2])

    # Initialisiere paarweise Statistik
    if stats_key not in session_stats:
        session_stats[stats_key] = {
            id1: {"name": p1["name"], "win": 0, "lose": 0, "draw": 0},
            id2: {"name": p2["name"], "win": 0, "lose": 0, "draw": 0},
        }

    winner_flag = evaluate_game(p1["choice"], p2["choice"])
    if winner_flag is None:
        result_text = "🤝 Unentschieden!"
        session_stats[stats_key][id1]["draw"] += 1
        session_stats[stats_key][id2]["draw"] += 1
        medal1 = medal2 = "🤝"
    elif winner_flag:
        result_text = f"🏆 {p1['name']} gewinnt!"
        session_stats[stats_key][id1]["win"] += 1
        session_stats[stats_key][id2]["lose"] += 1
        medal1, medal2 = "🥇", "🥈"
    else:
        result_text = f"🏆 {p2['name']} gewinnt!"
        session_stats[stats_key][id2]["win"] += 1
        session_stats[stats_key][id1]["lose"] += 1
        medal2, medal1 = "🥇", "🥈"

    text = (
        f"{medal1} {p1['name']} wählte {CHOICES[p1['choice']]} {p1['choice']}\n"
        f"{medal2} {p2['name']} wählte {CHOICES[p2['choice']]} {p2['choice']}\n\n"
        f"{result_text}\n\n"
        f"📊 Statistik (Session):\n"
        f"• {session_stats[stats_key][id1]['name']}: 🏆 {session_stats[stats_key][id1]['win']}  ❌ {session_stats[stats_key][id1]['lose']}  🤝 {session_stats[stats_key][id1]['draw']}\n"
        f"• {session_stats[stats_key][id2]['name']}: 🏆 {session_stats[stats_key][id2]['win']}  ❌ {session_stats[stats_key][id2]['lose']}  🤝 {session_stats[stats_key][id2]['draw']}"
    )

    await context.bot.edit_message_text(
        inline_message_id=game_id,
        text=text,
        reply_markup=play_again_keyboard(),
    )

# Handler registrieren
application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.stop()
    await application.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/", response_class=PlainTextResponse)
async def keep_alive():
    print("✅ Keep-alive Ping erhalten!")
    return "✅ MatchingFloBot läuft – aktiv durch echten Ping"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
