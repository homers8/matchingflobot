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

# In-Memory Stores
games = {}         # game_id → Spielzustand
stats = {}         # user_id → {"wins": 0, "losses": 0, "draws": 0}

# Telegram App
application = Application.builder().token(TOKEN).updater(None).build()

# === SPIELABLAUF ===
CHOICES = {"✂️": "Schere", "🪨": "Stein", "📄": "Papier"}

# Auswahl-Tastatur erzeugen
def choice_keyboard(game_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=emoji, callback_data=f"{game_id}:{emoji}") for emoji in CHOICES.keys()]
    ])

# Inline-Query verarbeiten
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("⚙️ Inline-Query Verarbeitung gestartet")
    try:
        game_id = str(uuid.uuid4())

        games[game_id] = {
            "players": {},  # user_id → {"name": str, "choice": str}
        }

        result = InlineQueryResultArticle(
            id=game_id,
            title="🎮 Starte Schere, Stein, Papier",
            input_message_content=InputTextMessageContent("👥 Spiel gestartet. Bitte wähle eine Option."),
            reply_markup=choice_keyboard(game_id),
        )

        await update.inline_query.answer([result], cache_time=0, is_personal=True)
        logger.info("✅ Inline-Query erfolgreich beantwortet")
    except Exception as e:
        logger.exception(f"❌ Fehler bei Inline-Query: {e}")

# Callback bei Button-Klick
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    game_id, emoji = query.data.split(":")

    game = games.get(game_id)
    if not game:
        await query.edit_message_text("❌ Spiel nicht gefunden oder abgelaufen.")
        return

    players = game["players"]

    # Wahl speichern
    if user.id not in players:
        players[user.id] = {"name": user.first_name, "choice": emoji}
    else:
        await query.answer("✅ Deine Wahl wurde bereits registriert.", show_alert=False)
        return

    # Wenn erst ein Spieler gewählt hat
    if len(players) == 1:
        await query.edit_message_text(
            text=f"✅ {user.first_name} hat gewählt.",
            reply_markup=choice_keyboard(game_id),
        )
    elif len(players) == 2:
        # Auswertung
        ids = list(players.keys())
        user1, user2 = ids[0], ids[1]
        p1, p2 = players[user1], players[user2]
        name1, choice1 = p1["name"], p1["choice"]
        name2, choice2 = p2["name"], p2["choice"]

        result = evaluate_game(choice1, choice2)

        # Statistik aktualisieren
        update_stats(user1, user2, result)

        # Stats abrufen
        s1 = stats[user1]
        s2 = stats[user2]

        # Ergebnis anzeigen inkl. Stats
        text = (
            f"{name1} wählte {CHOICES[choice1]} {choice1}\n"
            f"{name2} wählte {CHOICES[choice2]} {choice2}\n\n"
            f"{result}\n\n"
            f"📊 {name1}: {s1['wins']}🏆 {s1['losses']}❌ {s1['draws']}🤝\n"
            f"📊 {name2}: {s2['wins']}🏆 {s2['losses']}❌ {s2['draws']}🤝"
        )

        await query.edit_message_text(text)
        games.pop(game_id, None)

# Spielauswertung
def evaluate_game(c1, c2):
    if c1 == c2:
        return "🤝 Unentschieden!"
    beats = {"✂️": "📄", "📄": "🪨", "🪨": "✂️"}
    return "🏆 Spieler 1 gewinnt!" if beats[c1] == c2 else "🏆 Spieler 2 gewinnt!"

# Statistik aktualisieren
def update_stats(uid1, uid2, result):
    stats.setdefault(uid1, {"wins": 0, "losses": 0, "draws": 0})
    stats.setdefault(uid2, {"wins": 0, "losses": 0, "draws": 0})

    if "Unentschieden" in result:
        stats[uid1]["draws"] += 1
        stats[uid2]["draws"] += 1
    elif "Spieler 1 gewinnt" in result:
        stats[uid1]["wins"] += 1
        stats[uid2]["losses"] += 1
    elif "Spieler 2 gewinnt" in result:
        stats[uid1]["losses"] += 1
        stats[uid2]["wins"] += 1

# Handler registrieren
application.add_handler(InlineQueryHandler(handle_inline_query))
application.add_handler(CallbackQueryHandler(handle_callback))

# FastAPI-Lebenszyklus
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.shutdown()

# FastAPI App
app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logger.info(f"📬 Webhook empfangen: {data}")
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "✅ MatchingFloBot läuft mit Statistik."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
