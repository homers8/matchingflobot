from flask import Flask, request
from threading import Thread

app = Flask(__name__)
application = None  # wird gesetzt

@app.route('/', methods=['GET'])
def home():
    return "Bot läuft! ✅"

@app.route('/webhook', methods=['POST'])
async def webhook():
    if application:
        update = request.get_json(force=True)
        await application.update_queue.put(update)
    return '', 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive(app_instance):
    global application
    application = app_instance
    thread = Thread(target=run)
    thread.start()
