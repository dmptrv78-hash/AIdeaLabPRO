import os
import asyncio
from flask import Flask, request
from main import bot, dp, init_db
from aiogram.types import Update

app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running!"

@app.route("/health")
def health():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "Bad request", 400
    update = Update.model_validate(data, context={"bot": bot})
    # Выполняем асинхронную обработку синхронно
    asyncio.run(dp.feed_update(bot, update))
    return "OK", 200

def set_webhook():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL", "https://aidealabpro-bot.onrender.com") + "/webhook"
    loop.run_until_complete(bot.set_webhook(url=webhook_url))
    print(f"✅ Webhook установлен на {webhook_url}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
