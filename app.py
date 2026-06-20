# app.py - обертка для main.py с фильтрацией сообщений
import main
from aiogram import types
from aiogram.filters import Command

# Переопределяем обработчик /start
@main.dp.message(Command("start"))
async def new_start(message: types.Message, state: main.FSMContext):
    """Новый обработчик /start без проверки подписки"""
    user_id = message.from_user.id
    main.logger.info(f"🔄 /start от {user_id}")
    
    await state.clear()
    await main.clear_user_state(user_id)
    user = await main.get_or_create_user(user_id, message.from_user.username, message.from_user.full_name)
    
    if not user.consent_given:
        kb = main.InlineKeyboardMarkup(inline_keyboard=[
            [main.InlineKeyboardButton(text="✅ Согласен", callback_data="accept_consent")],
            [main.InlineKeyboardButton(text="❌ Не согласен", callback_data="decline_consent")]
        ])
        await main.safe_send_message(
            user_id,
            "🔐 **Для продолжения необходимо ваше согласие**\n\n"
            "Мы собираем только имя, телефон и email для связи.",
            reply_markup=kb
        )
        await state.set_state(main.CommonStates.ask_consent)
        return
    
    if user.email is None:
        await state.set_state(main.CommonStates.ask_email)
        await main.safe_send_message(
            user_id,
            "📧 **Укажите ваш email для связи**\n\n"
            "На него придёт подтверждение заявки.\n"
            "Если не хотите, нажмите «Пропустить».",
            reply_markup=main.nav_keyboard()
        )
        return
    
    await main.show_main_menu(user_id, "👋 **Добро пожаловать в AIdea Lab PRO!**\n\nВыберите услугу:")

# Запускаем бота
if __name__ == "__main__":
    main.logger.info(f"🚀 Запуск сервера на порту {main.PORT}")
    app = main.create_app()
    main.web.run_app(app, host="0.0.0.0", port=main.PORT)
