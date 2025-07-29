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

# Telegram-App ohne Updater
application = Application.builder().token(TOKEN).updater(None).build()

# Spieloptionen
CHOICES = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier"}

# In-Memory Spielstand
games = {}  # game_id → { players: {}, timestamp, stats: {} }

# Tastatur mit Wahlmöglichkeiten
def choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=emoji, callback_data=f"choice:{emoji}") for emoji in CHOICES]
    ])

# Tastatur für "Nochmal spielen"
def play_again_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🔁 Nochmal spielen", switch_inline_query_current_chat="")]
    ])

# Spielauswertung + Statistik
def evaluate_game(name1, choice1, name2, choice2):
    if choice1 == choice2:
        return None  # Unentschieden
    beats = {"✂️": "📄", "📄": "🪨", "🪨": "✂️"}
    return name1 if beats[choice1] == choice2 else name2

# Cleanup: Entferne alte Spiele (älter als 10 Min)
def cleanup_old_games():
    now = time.time()
    to_delete = [gid for gid, g in games.items() if now - g.get("timestamp", 0) > 600]
    for gid in to_delete:
        del games[gid]
        logger.info(f"🧹 Altes Spiel gelöscht: {gid}")

# Inline-Query-Handler
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

# Callback-Handler (Button-Klicks)
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data
    game_id = query.inline_message_id

    if not data.startswith("choice:"):
        return

    emoji = data.split(":")[1]

    # Neues Spiel anlegen oder laden
    if game_id not in games:
        games[game_id] = {"players": {}, "timestamp": time.time(), "stats": {}}
    game = games[game_id]
    players = game["players"]
    stats = game["stats"]

    logger.info(f"👤 Spieler klickt: {user.id} - {user.first_name} - Wahl: {emoji}")

    if user.id in players:
        await query.answer("✅ Deine Wahl wurde bereits registriert.", show_alert=False)
        return

    # Spieler speichern
    name = f"{user.first_name} {user.last_name or ''}".strip()
    players[user.id] = {"name": name, "choice": emoji}
    stats.setdefault(user.id, {"name": name, "win": 0, "lose": 0, "draw": 0})

    logger.info(f"🔄 Spielstand für {game_id}: {players}")

    if len(players) == 1:
        await context.bot.edit_message_text(
            inline_message_id=game_id,
            text=f"✅ {name} hat gewählt.\n⏳ Warte auf zweiten Spieler…",
            reply_markup=choice_keyboard(),
        )
    elif len(players) == 2:
        # Spiel auswerten
        (id1, p1), (id2, p2) = players.items()
        winner = evaluate_game(p1["name"], p1["choice"], p2["name"], p2["choice"])

        if not winner:
            stats[id1]["draw"] += 1
            stats[id2]["draw"] += 1
            medal1 = medal2 = "🤝"
            result = "🤝 Unentschieden!"
        elif winner == p1["name"]:
            stats[id1]["win"] += 1
            stats[id2]["lose"] += 1
            medal1, medal2 = "🥇", "🥈"
            result = f"🏆 {p1['name']} gewinnt!"
        else:
            stats[id2]["win"] += 1
            stats[id1]["lose"] += 1
            medal2, medal1 = "🥇", "🥈"
            result = f"🏆 {p2['name']} gewinnt!"

        # Ergebnis-Text
        full_text = (
            f"{medal1} {p1['name']} wählte {CHOICES[p1['choice']]} {p1['choice']}\n"
            f"{medal2} {p2['name']} wählte {CHOICES[p2['choice']]} {p2['choice']}\n\n"
            f"{result}\n\n"
            f"📊 Statistik:\n"
            f"• {stats[id1]['name']}: 🏆 {stats[id1]['win']}  ❌ {stats[id1]['lose']}  🤝 {stats[id1]['draw']}\n"
            f"• {stats[id2]['name']}: 🏆 {stats[id2]['win']}  ❌ {stats[id2]['lose']}  🤝 {stats[id2]['draw']}"
        )

        await context.bot.edit_message_text(
            inline_message_id=game_id,
            text=full_text,
            reply_markup=play_again_keyboard(),
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
    await application.stop()
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
