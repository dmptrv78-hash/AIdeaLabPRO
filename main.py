# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 8.0 – РАБОЧАЯ ДЛЯ RENDER (вебхуки)
# ============================================================

import os
import sys
import json
import asyncio
import logging
import datetime
import re
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.enums import ChatMemberStatus  # <-- ПРАВИЛЬНЫЙ ИМПОРТ!

from aiohttp import web
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# ===================== НАСТРОЙКА ЛОГИРОВАНИЯ =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8802501314:AAG0L8mrwSTNUqhrsHWIWGarw8QlZgtJXGQ")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1636715304").split(',')))
MANAGER_EMAIL = "dmptrv78@gmail.com"

# Настройки для вебхуков
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "https://aidealabpro.onrender.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

# ===================== ИНИЦИАЛИЗАЦИЯ =====================
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=storage)

# ===================== БАЗА ДАННЫХ =====================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}?check_same_thread=False"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ===================== МОДЕЛИ =====================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    consent_given = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(Integer, nullable=False)
    service = Column(String, nullable=False)
    status = Column(String, default="NEW")
    data = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class UserState(Base):
    __tablename__ = "user_states"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(Integer, unique=True, nullable=False)
    state = Column(String, nullable=True)
    data = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# ===================== ФУНКЦИИ БД =====================
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ База данных инициализирована")

async def get_or_create_user(telegram_id, username=None, full_name=None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            session.add(user)
            await session.commit()
            logger.info(f"✅ Новый пользователь: {telegram_id}")
        return user

async def save_user_state(user_id, state, data):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
        user_state = result.scalar_one_or_none()
        if user_state:
            user_state.state = state
            user_state.data = json.dumps(data, ensure_ascii=False)
            user_state.updated_at = datetime.datetime.utcnow()
        else:
            user_state = UserState(
                user_telegram_id=user_id,
                state=state,
                data=json.dumps(data, ensure_ascii=False)
            )
            session.add(user_state)
        await session.commit()

async def get_user_state(user_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
        user_state = result.scalar_one_or_none()
        if user_state:
            try:
                data = json.loads(user_state.data) if user_state.data else {}
            except:
                data = {}
            return user_state.state, data
        return None, None

async def clear_user_state(user_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
        user_state = result.scalar_one_or_none()
        if user_state:
            await session.delete(user_state)
            await session.commit()

async def save_order(user_telegram_id, service, data_json, price=0):
    async with AsyncSessionLocal() as session:
        order = Order(
            user_telegram_id=user_telegram_id,
            service=service,
            status="NEW",
            data=data_json,
            price=price
        )
        session.add(order)
        await session.commit()
        return order.id

# ===================== КЛАВИАТУРЫ =====================
def main_menu_keyboard():
    kb = [
        [KeyboardButton(text="📋 Техническое задание")],
        [KeyboardButton(text="📊 ТЭО")],
        [KeyboardButton(text="💰 Финансовая модель")],
        [KeyboardButton(text="📈 Бизнес-план")],
        [KeyboardButton(text="📦 Полный пакет")],
        [KeyboardButton(text="🔍 Проверка документов")],
        [KeyboardButton(text="✏️ Доработка документов")],
        [KeyboardButton(text="💬 Консультация")],
        [KeyboardButton(text="📋 Мои заявки")],
        [KeyboardButton(text="📩 Написать разработчику")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def nav_keyboard():
    kb = [
        [KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🏠 Главное меню")],
        [KeyboardButton(text="⏭ Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def feedback_keyboard():
    kb = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ===================== СОСТОЯНИЯ =====================
class TZStates(StatesGroup):
    name = State()
    essence = State()
    audience = State()
    features = State()
    competitors = State()
    tech_limits = State()
    deadline = State()
    budget = State()
    files = State()

class CommonStates(StatesGroup):
    ask_consent = State()
    ask_email = State()

class FeedbackStates(StatesGroup):
    waiting_for_message = State()

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
async def safe_send_message(user_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False

async def show_main_menu(user_id: int, text: str = "🏠 Главное меню\n\nВыберите услугу:"):
    await safe_send_message(user_id, text, reply_markup=main_menu_keyboard())

async def clear_and_go_home(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    await clear_user_state(user_id)
    await show_main_menu(user_id)

def calculate_price(service, data=None):
    prices = {
        "Техническое задание": 1250,
        "ТЭО": 3500,
        "Финансовая модель": 2500,
        "Бизнес-план": 3500,
        "Полный пакет": 9000,
        "Проверка": 750,
        "Доработка": 1000,
        "Консультация": 500,
    }
    return prices.get(service, 1500)

# ===================== ОБРАБОТЧИКИ =====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"🔄 /start от {user_id}")
    
    await state.clear()
    await clear_user_state(user_id)
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.full_name)
    
    if not user.consent_given:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Политика", callback_data="show_privacy")],
            [InlineKeyboardButton(text="📄 Оферта", callback_data="show_offer")],
            [InlineKeyboardButton(text="✅ Согласен", callback_data="accept_consent")],
            [InlineKeyboardButton(text="❌ Не согласен", callback_data="decline_consent")]
        ])
        await safe_send_message(
            user_id,
            "🔐 **Для продолжения необходимо ваше согласие**\n\n"
            "Мы собираем только имя, телефон и email для связи.\n\n"
            "Ознакомьтесь с документами и нажмите «Согласен».",
            reply_markup=kb
        )
        await state.set_state(CommonStates.ask_consent)
        return
    
    if user.email is None:
        await state.set_state(CommonStates.ask_email)
        await safe_send_message(
            user_id,
            "📧 **Укажите ваш email для связи**\n\n"
            "На него придёт подтверждение заявки.\n"
            "Если не хотите, нажмите «Пропустить».",
            reply_markup=nav_keyboard()
        )
        return
    
    await show_main_menu(user_id, "👋 **Добро пожаловать в AIdea Lab PRO!**\n\nВыберите услугу:")

@dp.callback_query(lambda c: c.data == "accept_consent")
async def accept_consent(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        if user:
            user.consent_given = True
            await session.commit()
    
    await callback.message.delete()
    await state.set_state(CommonStates.ask_email)
    await safe_send_message(
        user_id,
        "✅ **Спасибо!**\n\n📧 Укажите ваш email или нажмите «Пропустить».",
        reply_markup=nav_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "decline_consent")
async def decline_consent(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
    await safe_send_message(
        callback.from_user.id,
        "❌ Без согласия мы не можем работать.\n\nЕсли передумаете, напишите /start."
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "show_privacy")
async def show_privacy(callback: types.CallbackQuery):
    await callback.message.answer("📄 **Политика конфиденциальности**\n\nМы собираем только минимальные данные для связи. Подробнее: support@aidealab.pro")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "show_offer")
async def show_offer(callback: types.CallbackQuery):
    await callback.message.answer("📄 **Публичная оферта**\n\nУслуги оказываются в соответствии с законодательством РФ. Подробнее: support@aidealab.pro")
    await callback.answer()

@dp.message(CommonStates.ask_email)
async def process_email(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        async with AsyncSessionLocal() as session:
            user = await session.execute(select(User).where(User.telegram_id == user_id))
            user = user.scalar_one_or_none()
            if user:
                user.email = None
                await session.commit()
        
        await state.clear()
        await show_main_menu(user_id, "✅ **Email пропущен.**\n\nВыберите услугу:")
        return
    
    if "@" not in text or "." not in text:
        await safe_send_message(
            user_id,
            "❌ **Некорректный email**\n\nВведите email в формате: name@domain.com\nИли нажмите «Пропустить».",
            reply_markup=nav_keyboard()
        )
        return
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        if user:
            user.email = text
            await session.commit()
    
    await state.clear()
    await show_main_menu(user_id, f"✅ **Email {text} сохранён!**\n\nВыберите услугу:")

@dp.message(lambda msg: msg.text == "🏠 Главное меню")
async def go_home(message: types.Message, state: FSMContext):
    await clear_and_go_home(message, state)

@dp.message(lambda msg: msg.text == "🔙 Назад")
async def go_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if not current_state:
        await show_main_menu(message.from_user.id)
        return
    
    await safe_send_message(
        message.from_user.id,
        "🔙 **Вернулись на шаг назад.**\n\nПродолжайте заполнение.",
        reply_markup=nav_keyboard()
    )

@dp.message(lambda msg: msg.text == "📋 Техническое задание")
async def start_tz(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.set_state(TZStates.name)
    await safe_send_message(
        user_id,
        "📝 **Шаг 1 из 9: Название проекта**\n\nКак назовём ваш проект?",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.name)
async def tz_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if not text or len(text) < 2:
        await safe_send_message(
            user_id,
            "❌ Введите название (минимум 2 символа)",
            reply_markup=nav_keyboard()
        )
        return
    
    await state.update_data(name=text)
    await state.set_state(TZStates.essence)
    await safe_send_message(
        user_id,
        "📝 **Шаг 2 из 9: Суть проекта**\n\nОпишите свою идею: что вы хотите создать и кому это поможет?",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.essence)
async def tz_essence(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.name)
        await safe_send_message(user_id, "🔙 Вернулись. Введите название:", reply_markup=nav_keyboard())
        return
    
    if not text or len(text) < 5:
        await safe_send_message(
            user_id,
            "❌ Опишите суть подробнее (минимум 5 символов)",
            reply_markup=nav_keyboard()
        )
        return
    
    await state.update_data(essence=text)
    await state.set_state(TZStates.audience)
    await safe_send_message(
        user_id,
        "📝 **Шаг 3 из 9: Целевая аудитория**\n\nКто ваши клиенты? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.audience)
async def tz_audience(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.essence)
        await safe_send_message(user_id, "🔙 Вернулись. Опишите суть:", reply_markup=nav_keyboard())
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(audience="")
    else:
        await state.update_data(audience=text)
    
    await state.set_state(TZStates.features)
    await safe_send_message(
        user_id,
        "📝 **Шаг 4 из 9: Функциональность**\n\nКакие главные возможности? Напишите через запятую.",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.features)
async def tz_features(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.audience)
        await safe_send_message(user_id, "🔙 Вернулись. Кто ваши клиенты?", reply_markup=nav_keyboard())
        return
    
    if not text or len(text) < 3:
        await safe_send_message(
            user_id,
            "❌ Перечислите функции (минимум 3 символа)",
            reply_markup=nav_keyboard()
        )
        return
    
    await state.update_data(features=text)
    await state.set_state(TZStates.competitors)
    await safe_send_message(
        user_id,
        "📝 **Шаг 5 из 9: Конкуренты**\n\nЕсть ли конкуренты? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.competitors)
async def tz_competitors(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.features)
        await safe_send_message(user_id, "🔙 Вернулись. Перечислите функции:", reply_markup=nav_keyboard())
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=text)
    
    await state.set_state(TZStates.tech_limits)
    await safe_send_message(
        user_id,
        "📝 **Шаг 6 из 9: Технические ограничения**\n\nЕсть ли технические рамки? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.tech_limits)
async def tz_tech_limits(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.competitors)
        await safe_send_message(user_id, "🔙 Вернулись. Есть конкуренты?", reply_markup=nav_keyboard())
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(tech_limits="")
    else:
        await state.update_data(tech_limits=text)
    
    await state.set_state(TZStates.deadline)
    await safe_send_message(
        user_id,
        "📝 **Шаг 7 из 9: Сроки**\n\nКогда нужен результат? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.deadline)
async def tz_deadline(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.tech_limits)
        await safe_send_message(user_id, "🔙 Вернулись. Есть технические рамки?", reply_markup=nav_keyboard())
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(deadline="")
    else:
        await state.update_data(deadline=text)
    
    await state.set_state(TZStates.budget)
    await safe_send_message(
        user_id,
        "📝 **Шаг 8 из 9: Бюджет**\n\nЕсть ли бюджет? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.budget)
async def tz_budget(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip().lower() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.deadline)
        await safe_send_message(user_id, "🔙 Вернулись. Когда нужен результат?", reply_markup=nav_keyboard())
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(budget="")
    elif text in ["нет", "нисколько", "0", "без бюджета"]:
        await state.update_data(budget="0 (не указан)")
    else:
        try:
            digits = re.sub(r'[^0-9]', '', text)
            if digits:
                await state.update_data(budget=f"{int(digits)} руб.")
            else:
                await state.update_data(budget=text)
        except:
            await state.update_data(budget=text)
    
    await state.set_state(TZStates.files)
    await safe_send_message(
        user_id,
        "📝 **Шаг 9 из 9: Файлы**\n\nПриложите файлы или нажмите «Пропустить».",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.files)
async def tz_files(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    
    if text == "🔙 Назад":
        await state.set_state(TZStates.budget)
        await safe_send_message(user_id, "🔙 Вернулись. Укажите бюджет:", reply_markup=nav_keyboard())
        return
    
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(file_url=None)
    elif message.document:
        await state.update_data(file_url="file_uploaded")
        await state.update_data(file_name=message.document.file_name)
        await safe_send_message(user_id, "✅ Файл загружен!")
    else:
        await safe_send_message(
            user_id,
            "❌ Загрузите файл или нажмите «Пропустить».",
            reply_markup=nav_keyboard()
        )
        return
    
    # Завершение
    data = await state.get_data()
    order_id = await save_order(
        user_id,
        "Техническое задание",
        json.dumps(data, ensure_ascii=False),
        calculate_price("Техническое задание", data)
    )
    
    logger.info(f"✅ Заказ #{order_id} от {user_id}")
    
    # Уведомление админам
    for admin_id in ADMIN_IDS:
        await safe_send_message(
            admin_id,
            f"📋 **Новая заявка #{order_id}**\n\n"
            f"Услуга: Техническое задание\n"
            f"Пользователь: {message.from_user.full_name or 'Неизвестно'}\n"
            f"Telegram: @{message.from_user.username or 'нет'}\n"
            f"ID: {user_id}\n\n"
            f"Название: {data.get('name', '—')}\n"
            f"Суть: {data.get('essence', '—')[:100]}..."
        )
    
    await state.clear()
    await clear_user_state(user_id)
    await show_main_menu(
        user_id,
        f"✅ **Заявка #{order_id} принята!**\n\n"
        f"📋 Техническое задание\n"
        f"💰 Стоимость: {calculate_price('Техническое задание', data)} руб.\n\n"
        f"Менеджер свяжется с вами в ближайшее время."
    )

# ===================== НАСТРОЙКА ВЕБХУКОВ =====================
async def on_startup():
    """Действия при запуске"""
    logger.info("🚀 Запуск бота...")
    await init_db()
    
    # Установка вебхука
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types()
    )
    logger.info(f"✅ Вебхук установлен: {WEBHOOK_URL}")
    
    # Уведомление админов
    for admin_id in ADMIN_IDS:
        await safe_send_message(
            admin_id,
            f"🤖 **Бот запущен!**\n"
            f"Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Вебхук: {WEBHOOK_URL}"
        )

async def on_shutdown():
    """Действия при остановке"""
    logger.info("👋 Остановка бота...")
    await bot.delete_webhook()
    await bot.session.close()

# ===================== ЗАПУСК =====================
def create_app():
    """Создание aiohttp приложения"""
    app = web.Application()
    
    # Настройка обработчика вебхуков
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=os.getenv("WEBHOOK_SECRET", ""),
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Setup application
    setup_application(app, dp, bot=bot)
    
    # Обработчики событий
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    return app

if __name__ == "__main__":
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
