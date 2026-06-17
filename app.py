import os
import asyncio
import threading
from flask import Flask
from main import bot, dp, main as bot_main

app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running!"

@app.route("/health")
def health():
    return "OK", 200

def run_bot():
    asyncio.run(bot_main())

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
