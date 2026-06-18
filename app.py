import os
import asyncio
import logging
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
async def webhook():
    update = Update.model_validate(await request.get_json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return "OK", 200

def set_webhook():
    """Устанавливает вебхук при запуске"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL", "https://aidealabpro-bot.onrender.com") + "/webhook"
    loop.run_until_complete(bot.set_webhook(url=webhook_url))
    print(f"✅ Webhook установлен на {webhook_url}")

if __name__ == "__main__":
    # Устанавливаем вебхук до запуска Flask
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
