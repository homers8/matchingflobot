import os
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager

from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, ContextTypes, InlineQueryHandler

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfiguration
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://matchingflobot.onrender.com/webhook")

if not TOKEN:
    raise RuntimeError("❌ TOKEN fehlt!")

# Telegram-Bot initialisieren
application = Application.builder().token(TOKEN).updater(None).build()

# Inline-Handler
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🟡 handle_inline_query wurde aufgerufen")

    try:
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="🎮 Testantwort",
                input_message_content=InputTextMessageContent("Dies ist eine Testantwort.")
            )
        ]
        await update.inline_query.answer(results, cache_time=1, is_personal=True)
        logger.info("✅ Inline-Query erfolgreich beantwortet")
    except Exception as e:
        logger.exception(f"❌ Fehler bei Inline-Query: {e}")

application.add_handler(InlineQueryHandler(handle_inline_query))

# FastAPI App mit Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🌐 Webhook gesetzt: {WEBHOOK_URL}")
    yield
    await application.shutdown()

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
    return "✅ MatchingFloBot minimal läuft."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
