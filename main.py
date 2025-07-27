import asyncio
import logging
from fastapi import FastAPI, Request
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "8010815430:AAFfc0QxiqgSdrJA5Ndu5MXDJsnLr0OFvNw"
WEBHOOK_URL = "https://matchingflobot.onrender.com/webhook"

app = FastAPI()
application = Application.builder().token(TOKEN).build()

games = {}

# --- Telegram Handler ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Willkommen zum Schere-Stein-Papier Spiel!\n"
        "Starte eine Partie mit /play"
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    games[chat_id] = {
        "player1": user_id,
        "player1_choice": None,
        "player2": None,
        "player2_choice": None,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Schere ✂️", callback_data="choice_scissors"),
                InlineKeyboardButton("Stein 🪨", callback_data="choice_rock"),
                InlineKeyboardButton("Papier 📄", callback_data="choice_paper"),
            ]
        ]
    )

    await update.message.reply_text(
        "Du bist Spieler 1. Warte auf Spieler 2 und wähle deine Option:",
        reply_markup=keyboard,
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if chat_id not in games:
        await query.answer("Keine laufende Partie in diesem Chat. Starte mit /play")
        return

    game = games[chat_id]

    if game["player2"] is None and user_id != game["player1"]:
        game["player2"] = user_id

    if user_id != game["player1"] and user_id != game["player2"]:
        await query.answer("Du bist kein Teilnehmer dieses Spiels.")
        return

    choice_map = {
        "choice_scissors": "Schere",
        "choice_rock": "Stein",
        "choice_paper": "Papier",
    }

    choice = choice_map.get(data)
    if choice is None:
        await query.answer("Ungültige Auswahl.")
        return

    if user_id == game["player1"]:
        if game["player1_choice"] is not None:
            await query.answer("Du hast schon gewählt!")
            return
        game["player1_choice"] = choice
    else:
        if game["player2_choice"] is not None:
            await query.answer("Du hast schon gewählt!")
            return
        game["player2_choice"] = choice

    await query.answer(f"Deine Wahl: {choice}")

    if game["player1_choice"] and game["player2_choice"]:
        result_text = determine_winner(game["player1_choice"], game["player2_choice"])
        await query.message.reply_text(
            f"Ergebnis:\n"
            f"Spieler 1: {game['player1_choice']}\n"
            f"Spieler 2: {game['player2_choice']}\n\n"
            f"{result_text}"
        )
        del games[chat_id]
    else:
        await query.message.reply_text("Warte auf die Wahl des anderen Spielers...")

def determine_winner(choice1, choice2):
    if choice1 == choice2:
        return "Unentschieden!"
    wins = {
        "Schere": "Papier",
        "Stein": "Schere",
        "Papier": "Stein",
    }
    if wins[choice1] == choice2:
        return "Spieler 1 gewinnt!"
    else:
        return "Spieler 2 gewinnt!"

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    results = [
        InlineQueryResultArticle(
            id="1",
            title="Schere-Stein-Papier Spiel starten",
            input_message_content=InputTextMessageContent("/play"),
            description="Starte ein Schere-Stein-Papier Spiel mit /play",
        )
    ]
    await update.inline_query.answer(results, cache_time=0)

# --- Handler registrieren ---

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("play", play))
application.add_handler(CallbackQueryHandler(callback_handler))
application.add_handler(InlineQueryHandler(inline_query))

# --- FastAPI Webhook Endpoint ---

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    logger.info(f"📬 Webhook empfangen: {data}")
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Telegram Bot läuft mit FastAPI"}

@app.on_event("startup")
async def on_startup():
    await application.bot.set_webhook(WEBHOOK_URL)
    print(f"🌐 Webhook gesetzt auf: {WEBHOOK_URL}")

# --- Server starten ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
