from flask import Flask, request
from threading import Thread
import asyncio
from telegram import Update

app = Flask(__name__)
application = None  # wird später gesetzt

@app.route('/', methods=['GET'])
def home():
    return "Bot läuft! ✅"

@app.route('/webhook', methods=['POST'])
def webhook():
    if application:
        try:
            update = Update.de_json(request.get_json(force=True), application.bot)
            asyncio.get_event_loop().create_task(application.update_queue.put(update))
        except Exception as e:
            print(f"Webhook-Fehler: {e}")
            return "Fehler", 500
    return '', 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive(app_instance):
    global application
    application = app_instance
    thread = Thread(target=run)
    thread.start()
