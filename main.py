import os
import asyncio
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, ApplicationBuilder

# === Konfiguration ===
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = f"https://matchingflobot.onrender.com/webhook"

# === Flask Setup ===
app = Flask(__name__)

# === Telegram Bot Setup ===
bot = Bot(token=TOKEN)
application = ApplicationBuilder().token(TOKEN).build()

# === Webhook-Route ===
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        application.create_task(application.update_queue.put(update))
        return "OK"
    except Exception as e:
        print(f"❌ Fehler im Webhook: {e}")
        return "Fehler", 500

# === Keep-Alive Route (optional) ===
@app.route("/")
def index():
    return "Bot läuft ✅"

# === Bot-Setup ===
async def setup():
    await application.initialize()
    await application.start()
    await bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook wurde gesetzt")

# === Main ===
if __name__ == "__main__":
    asyncio.run(setup())

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
