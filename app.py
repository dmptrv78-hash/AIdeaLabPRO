# app.py - обертка для main.py с фильтром сообщений
import main
from aiogram import types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

# ===================== ОТКЛЮЧЕНИЕ ПРОВЕРКИ ПОДПИСКИ =====================
# Переопределяем обработчик /start
@main.dp.message(Command("start"))
async def new_start(message: types.Message, state: FSMContext):
    """Новый обработчик /start без проверки подписки"""
    user_id = message.from_user.id
    main.logger.info(f"🔄 /start от {user_id}")
    
    await state.clear()
    await main.clear_user_state(user_id)
    user = await main.get_or_create_user(user_id, message.from_user.username, message.from_user.full_name)
    
    if not user.consent_given:
        kb = main.InlineKeyboardMarkup(inline_keyboard=[
            [main.InlineKeyboardButton(text="📄 Политика", callback_data="show_privacy")],
            [main.InlineKeyboardButton(text="📄 Оферта", callback_data="show_offer")],
            [main.InlineKeyboardButton(text="✅ Согласен", callback_data="accept_consent")],
            [main.InlineKeyboardButton(text="❌ Не согласен", callback_data="decline_consent")]
        ])
        await main.safe_send_message(
            user_id,
            "🔐 **Для продолжения необходимо ваше согласие**\n\n"
            "Мы собираем только имя, телефон и email для связи.\n\n"
            "Ознакомьтесь с документами и нажмите «Согласен».",
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

# Переопределяем обработчик callback_query для согласия
@main.dp.callback_query(lambda c: c.data == "accept_consent")
async def new_accept_consent(callback: main.types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with main.AsyncSessionLocal() as session:
        user = await session.execute(main.select(main.User).where(main.User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        if user:
            user.consent_given = True
            await session.commit()
    
    await callback.message.delete()
    await state.set_state(main.CommonStates.ask_email)
    await main.safe_send_message(
        user_id,
        "✅ **Спасибо!**\n\n📧 Укажите ваш email или нажмите «Пропустить».",
        reply_markup=main.nav_keyboard()
    )
    await callback.answer()

# Переопределяем обработчик callback_query для отказа
@main.dp.callback_query(lambda c: c.data == "decline_consent")
async def new_decline_consent(callback: main.types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
    await main.safe_send_message(
        callback.from_user.id,
        "❌ Без согласия мы не можем работать.\n\nЕсли передумаете, напишите /start."
    )
    await callback.answer()

# Переопределяем обработчик для email
@main.dp.message(main.CommonStates.ask_email)
async def new_process_email(message: main.types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await main.clear_and_go_home(message, state)
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        async with main.AsyncSessionLocal() as session:
            user = await session.execute(main.select(main.User).where(main.User.telegram_id == user_id))
            user = user.scalar_one_or_none()
            if user:
                user.email = None
                await session.commit()
        
        await state.clear()
        await main.show_main_menu(user_id, "✅ **Email пропущен.**\n\nВыберите услугу:")
        return
    
    if "@" not in text or "." not in text:
        await main.safe_send_message(
            user_id,
            "❌ **Некорректный email**\n\nВведите email в формате: name@domain.com\nИли нажмите «Пропустить».",
            reply_markup=main.nav_keyboard()
        )
        return
    
    async with main.AsyncSessionLocal() as session:
        user = await session.execute(main.select(main.User).where(main.User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        if user:
            user.email = text
            await session.commit()
    
    await state.clear()
    await main.show_main_menu(user_id, f"✅ **Email {text} сохранён!**\n\nВыберите услугу:")

# Запускаем бота
if __name__ == "__main__":
    main.logger.info("🚀 Запуск сервера на порту 10000")
    app = main.create_app()
    main.web.run_app(app, host="0.0.0.0", port=main.PORT)
