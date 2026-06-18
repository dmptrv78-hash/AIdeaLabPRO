import os
import asyncio
from aiohttp import web
from main import bot, dp, init_db
from aiogram.types import Update

async def handle_webhook(request):
    """Обработчик вебхука"""
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return web.Response(text="OK", status=200)

async def health(request):
    return web.Response(text="OK", status=200)

async def index(request):
    return web.Response(text="Bot is running!")

async def on_startup(app):
    """Инициализация БД и установка вебхука при старте"""
    await init_db()
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL", "https://aidealabpro-bot.onrender.com") + "/webhook"
    await bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook установлен на {webhook_url}")

async def on_shutdown(app):
    """Удаление вебхука при остановке"""
    await bot.delete_webhook()
    print("Webhook удалён")

def main():
    port = int(os.environ.get("PORT", 5000))
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_post("/webhook", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
