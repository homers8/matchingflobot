from flask import Flask, request
from threading import Thread

app = Flask(__name__)
BOT = None  # Wird später vom Hauptprogramm gesetzt

@app.route('/', methods=['GET'])
def home():
    return "Bot läuft! ✅"

@app.route('/webhook', methods=['POST'])
def webhook():
    if BOT:
        update = BOT.update_queue.put(request.get_json(force=True))
    return '', 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive(application):
    global BOT
    BOT = application
    t = Thread(target=run)
    t.start()
