import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, ApplicationBuilder

# === Logging aktivieren ===
logging.basicConfig(level=logging.INFO)

# === Konfiguration ===
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = f"https://matchingflobot.onrender.com/webhook"

# === Flask Setup ===
app = Flask(__name__)

# === Telegram Bot Setup ===
bot = Bot(token=TOKEN)
application = ApplicationBuilder().token(TOKEN).build()

# === Webhook Route (mit logging.exception) ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run_coroutine_threadsafe(
            application.update_queue.put(update),
            asyncio.get_event_loop()
        )
        return "OK"
    except Exception:
        logging.exception("❌ Fehler im Webhook:")
        return "Fehler", 500

# === Keep-Alive Route ===
@app.route('/')
def index():
    return "Bot läuft ✅"

# === Bot-Initialisierung ===
async def setup():
    await application.initialize()
    await bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook wurde gesetzt")

# === Startpunkt ===
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(setup())
    except RuntimeError as e:
        print(f"Fehler beim Setup: {e}")

    # Flask starten
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
