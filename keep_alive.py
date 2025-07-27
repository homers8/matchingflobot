from fastapi import FastAPI, Request
import asyncio
from telegram import Update

app = FastAPI()
application = None  # Telegram Application-Instanz (später setzen)

@app.get("/")
async def home():
    return {"message": "Bot läuft! ✅"}

@app.post("/webhook")
async def webhook(request: Request):
    if application:
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            # Update in die Telegram-Update-Queue einfügen (async)
            await application.update_queue.put(update)
        except Exception as e:
            print(f"Webhook-Fehler: {e}")
            return {"status": "error", "message": str(e)}, 500
    return {"status": "ok"}

def keep_alive(app_instance):
    global application
