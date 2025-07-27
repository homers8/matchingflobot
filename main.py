import os
import logging
from telegram.ext import (
    Application, CommandHandler, InlineQueryHandler,
    CallbackQueryHandler, ContextTypes
)
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQueryResultArticle, InputTextMessageContent
)
from uuid import uuid4
from keep_alive import keep_alive  # falls du Flask für Render nutzt

# Bot-Token aus Umgebungsvariable
TOKEN = os.environ.get("TOKEN")  # bei Render als Umgebungsvariable setzen

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHOICES = ["🪨 Stein", "📄 Papier", "✂️ Schere"]
games = {}
statistics = {}

def determine_winner(c1: str, c2: str) -> int:
    if c1 == c2:
        return 0
    wins = {"🪨 Stein": "✂️ Schere", "✂️ Schere": "📄 Papier", "📄 Papier": "🪨 Stein"}
    return 1 if wins[c1] == c2 else 2

def get_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=c, callback_data=f"choice:{c}") for c in CHOICES]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tippe @DeinBotName in einen Chat, um Schere, Stein, Papier zu spielen.")

async def inlinequery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = InlineQueryResultArticle(
        id=str(uuid4()),
        title="🕹️ Schere, Stein, Papier spielen",
        input_message_content=InputTextMessageContent("🕹️ Spiel gestartet: Wähle deine Option!"),
        reply_markup=get_choice_keyboard()
    )
    await update.inline_query.answer([result], cache_time=0)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if not data.startswith("choice:"):
        return

    choice = data.split(":")[1]
    game_id = query.inline_message_id or query.message.message_id
    logger.info(f"{user.first_name} wählt {choice}")

    if game_id not in games:
        games[game_id] = {}

    games[game_id][user.id] = {"name": user.first_name, "choice": choice}
    players = games[game_id]
    names = list(players.values())

    if len(players) == 1:
        text = f"{names[0]['name']} hat gewählt. ⏳ Warte auf den zweiten Spieler…"
    elif len(players) == 2:
        p1, p2 = names[0], names[1]
        result = determine_winner(p1["choice"], p2["choice"])
        if result == 0:
            outcome = "🤝 Unentschieden!"
        elif result == 1:
            outcome = f"🏆 {p1['name']} gewinnt!"
            statistics[p1["name"]] = statistics.get(p1["name"], 0) + 1
        else:
            outcome = f"🏆 {p2['name']} gewinnt!"
            statistics[p2["name"]] = statistics.get(p2["name"], 0) + 1

        text = (f"{p1['name']} wählte {p1['choice']}\n"
                f"{p2['name']} wählte {p2['choice']}\n\n"
                f"{outcome}\n\n"
                f"📊 Statistik:\n"
                f"🥇 {p1['name']}: {statistics.get(p1['name'], 0)}\n"
                f"🥇 {p2['name']}: {statistics.get(p2['name'], 0)}")
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Nochmal", switch_inline_query_current_chat="")]])
        await query.edit_message_text(text=text, reply_markup=keyboard)
        del games[game_id]
        return
    else:
        text = "⚠️ Zu viele Spieler."

    already_chosen = "\n".join(f"{info['name']} hat gewählt. ✅" for info in players.values())
    await query.edit_message_text(text=already_chosen, reply_markup=get_choice_keyboard())

async def main():
    keep_alive()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(InlineQueryHandler(inlinequery))
    application.add_handler(CallbackQueryHandler(button))

    print("Bot läuft…")
    await application.run_polling()
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
