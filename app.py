import os
import asyncio
import logging
from aiohttp import web
from aiogram.types import Update
from main import bot, dp, init_db

# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== ОБРАБОТЧИКИ =====================
async def handle_webhook(request):
    """Обработчик POST-запросов от Telegram"""
    try:
        data = await request.json()
        logger.info(f"Получен вебхук: {data.get('update_id')}")
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Ошибка в вебхуке: {e}", exc_info=True)
        return web.Response(text="Error", status=500)

async def health(request):
    """Проверка работоспособности для мониторинга"""
    return web.Response(text="OK", status=200)

async def index(request):
    """Корневой путь (для теста)"""
    return web.Response(text="Bot is running!", status=200)

# ===================== СТАРТ И ОСТАНОВКА =====================
async def on_startup(app):
    """Действия при запуске приложения"""
    logger.info("Инициализация базы данных...")
    await init_db()
    # Определяем URL для вебхука
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not webhook_url:
        # fallback, если переменная не задана
        webhook_url = "https://aidealabpro.onrender.com"
    webhook_url += "/webhook"
    logger.info(f"Установка вебхука на {webhook_url}")
    await bot.set_webhook(url=webhook_url)
    logger.info("✅ Вебхук установлен")

async def on_shutdown(app):
    """Действия при остановке приложения"""
    logger.info("Удаление вебхука...")
    await bot.delete_webhook()
    logger.info("Закрытие сессии бота...")
    await bot.session.close()
    logger.info("✅ Остановка завершена")

# ===================== ЗАПУСК =====================
def main():
    port = int(os.environ.get("PORT", 5000))
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_post("/webhook", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    logger.info(f"Запуск сервера на порту {port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
