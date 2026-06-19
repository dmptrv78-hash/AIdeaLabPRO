import asyncio
from main import bot, dp, init_db

async def main():
    """Запуск бота в режиме polling (без вебхука)"""
    print("🔄 Инициализация базы данных...")
    await init_db()
    print("✅ База данных инициализирована")
    print("🚀 Запуск бота в режиме polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
