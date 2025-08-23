import os
import logging
import time
import requests
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

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Telegram-Konfiguration ----------------
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://matchingflobot.onrender.com/webhook")
if not TOKEN:
    raise RuntimeError("❌ TOKEN fehlt!")

application = Application.builder().token(TOKEN).updater(None).build()

# ---------------- Spieloptionen ----------------
CHOICES_CLASSIC = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier"}
CHOICES_BRUNNEN = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier", "⛲": "Brunnen"}

games = {}
session_stats = {}

def choice_keyboard(mode: str):
    choices = CHOICES_CLASSIC if mode == "classic" else CHOICES_BRUNNEN
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=emoji, callback_data=f"{mode}:{emoji}") for emoji in choices]
    ])

def play_again_keyboard(mode: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🔁 Nochmal spielen", switch_inline_query_current_chat="")]
    ])

def evaluate_game(choice1, choice2, mode):
    if choice1 == choice2:
        return None

    if mode == "classic":
        beats = {"✂️": ["📄"], "📄": ["🪨"], "🪨": ["✂️"]}
    else:  # brunnen
        beats = {
            "✂️": ["📄"],
            "📄": ["🪨", "⛲"],
            "🪨": ["✂️"],
            "⛲": ["✂️", "🪨"]
        }

    return choice2 in beats.get(choice1, [])

def cleanup_old_games():
    now = time.time()
    to_delete = [gid for gid, g in games.items() if now - g.get("timestamp", 0) > 600]
    for gid in to_delete:
        del games[gid]
        logger.info(f"🧹 Altes Spiel gelöscht: {gid}")

# ---------------- Telegram Handler ----------------
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_old_games()
    query = update.inline_query.query.strip().lower()

    # Standardmäßig beide Modi anbieten
    if query not in ["classic", "brunnen"]:
        results = [
            InlineQueryResultArticle(
                id="start-classic",
                title="🎮 Starte Schere, Stein, Papier",
                description="Klassisch: ✂️🪨📄",
                input_message_content=InputTextMessageContent("👥 Spiel gestartet (Klassisch). Bitte wähle eine Option."),
                reply_markup=choice_keyboard("classic"),
            ),
            InlineQueryResultArticle(
                id="start-brunnen",
                title="🎮 Starte Schere, Stein, Papier, Brunnen",
                description="Mit Brunnen: ✂️🪨📄⛲",
                input_message_content=InputTextMessageContent("👥 Spiel gestartet (mit Brunnen). Bitte wähle eine Option."),
                reply_markup=choice_keyboard("brunnen"),
            ),
        ]
    else:
        # Wenn der "Nochmal spielen"-Button einen Modus vorgibt
        results = [
            InlineQueryResultArticle(
                id=f"start-{query}",
                title=f"🎮 Starte Schere, Stein, Papier{' + Brunnen' if query == 'brunnen' else ''}",
                input_message_content=InputTextMessageContent(f"👥 Spiel gestartet ({'mit Brunnen' if query == 'brunnen' else 'Klassisch'}). Bitte wähle eine Option."),
                reply_markup=choice_keyboard(query),
            )
        ]

    await update.inline_query.answer(results, cache_time=0, is_personal=True)
    logger.info("✅ Inline-Query beantwortet")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    name = user.first_name
    data = query.data
    game_id = query.inline_message_id

    if ":" not in data:
        return

    mode, emoji = data.split(":")
    game = games.setdefault(game_id, {"players": {}, "timestamp": time.time(), "mode": mode})
    players = game["players"]
    game["timestamp"] = time.time()

    if user_id in players:
        await query.answer("✅ Deine Wahl wurde bereits registriert.")
        return

    players[user_id] = {"name": name, "choice": emoji}
    logger.info(f"👤 {name} ({user_id}) hat gewählt: {emoji} [{mode}]")

    if len(players) == 1:
        await context.bot.edit_message_text(
            inline_message_id=game_id,
            text=f"✅ {name} hat gewählt.\n⏳ Warte auf zweiten Spieler…",
            reply_markup=choice_keyboard(mode),
        )
        return

    if len(players) < 2:
        return

    (id1, p1), (id2, p2) = players.items()
    stats_key = frozenset([id1, id2])

    if stats_key not in session_stats:
        session_stats[stats_key] = {
            id1: {"name": p1["name"], "win": 0, "lose": 0, "draw": 0},
            id2: {"name": p2["name"], "win": 0, "lose": 0, "draw": 0},
        }

    winner_flag = evaluate_game(p1["choice"], p2["choice"], mode)
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

    choices = CHOICES_CLASSIC if mode == "classic" else CHOICES_BRUNNEN
    text = (
        f"{medal1} {p1['name']} wählte {choices[p1['choice']]} {p1['choice']}\n"
        f"{medal2} {p2['name']} wählte {choices[p2['choice']]} {p2['choice']}\n\n"
        f"{result_text}\n\n"
        f"📊 Statistik (Session):\n"
        f"• {session_stats[stats_key][id1]['name']}: 🏆 {session_stats[stats_key][id1]['win']}  ❌ {session_stats[stats_key][id1]['lose']}  🤝 {session_stats[stats_key][id1]['draw']}\n"
        f"• {session_stats[stats_key][id2]['name']}: 🏆 {session_stats[stats_key][id2]['win']}  ❌ {session_stats[stats_key][id2]['lose']}  🤝 {session_stats[stats_key][id2]['draw']}"
    )

    await context.bot.edit_message_text(
        inline_message_id=game_id,
        text=text,
        reply_markup=play_again_keyboard(mode),
    )

application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback))

# ---------------- WhatsApp-Konfiguration ----------------
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "testtoken123")

# ---------------- Lifespan für FastAPI ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Telegram Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.stop()
    await application.shutdown()

app = FastAPI(lifespan=lifespan)

# ---------------- Telegram Webhook ----------------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

# ---------------- WhatsApp Webhook Verify ----------------
@app.get("/whatsapp")
async def verify_whatsapp(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ WhatsApp Webhook erfolgreich verifiziert")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning("❌ WhatsApp Webhook-Verifizierung fehlgeschlagen")
    return PlainTextResponse(content="Verification failed", status_code=403)

# ---------------- WhatsApp Webhook Messages ----------------
@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    data = await request.json()
    logger.info(f"📩 WhatsApp Webhook: {data}")

    try:
        entry = data["entry"][0]["changes"][0]["value"]["messages"][0]
        from_number = entry["from"]
        msg_text = entry["text"]["body"]

        url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": from_number,
            "type": "text",
            "text": {"body": f"Hallo! Du hast geschrieben: {msg_text}"}
        }
        requests.post(url, headers=headers, json=payload)

    except Exception as e:
        logger.error(f"Fehler im WhatsApp-Webhook: {e}")

    return {"status": "ok"}

# ---------------- Root Keep-Alive ----------------
@app.get("/", response_class=PlainTextResponse)
async def keep_alive():
    return "✅ MatchingFloBot läuft – Telegram + WhatsApp aktiv"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
