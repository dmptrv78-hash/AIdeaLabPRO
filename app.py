import os
import asyncio
import threading
import time
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
    print("🔄 Запуск бота...")
    # Создаём новый цикл событий в этом потоке
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot_main())
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()
    finally:
        loop.close()

if __name__ == "__main__":
    print("🚀 Запуск Flask-сервера...")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("✅ Поток бота запущен")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
