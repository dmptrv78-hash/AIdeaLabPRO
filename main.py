# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 8.0 – ПОЛНАЯ (ТЗ + ТЭО + Финмодель + БП)
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
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from aiohttp import web
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, select, func, text
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

async def migrate_db():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN email TEXT"))
            logger.info("✅ Колонка email добавлена")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.warning(f"Ошибка добавления email: {e}")
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN consent_given BOOLEAN DEFAULT 0"))
            logger.info("✅ Колонка consent_given добавлена")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.warning(f"Ошибка добавления consent_given: {e}")
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN last_activity DATETIME"))
            logger.info("✅ Колонка last_activity добавлена")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.warning(f"Ошибка добавления last_activity: {e}")

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

class TEOStates(StatesGroup):
    goal = State()
    resources = State()
    risks = State()
    norms = State()
    effect = State()
    data = State()
    horizon = State()
    files = State()

class FMStates(StatesGroup):
    income = State()
    costs = State()
    investment = State()
    breakeven = State()
    metrics = State()
    data = State()
    horizon = State()

class BPStates(StatesGroup):
    summary = State()
    product = State()
    competitors = State()
    marketing = State()
    team = State()
    sales = State()
    risks = State()
    capital = State()
    finance_file = State()
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

async def finalize_order(message: types.Message, state: FSMContext, service_name: str, fields: dict, price_override=None):
    try:
        data = await state.get_data()
        user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        price = price_override if price_override is not None else calculate_price(service_name, data)
        order_id = await save_order(user.telegram_id, service_name, json.dumps(data, ensure_ascii=False), price)
        
        summary = f"📋 {service_name}\n\n"
        for key, label in fields.items():
            value = data.get(key, '—')
            if key == "file_url" and value:
                value = "📎 Файл загружен"
            summary += f"{label}: {value}\n"
        summary += f"\n💰 Стоимость: {price} руб."
        
        admin_message = (
            f"🔔 НОВАЯ ЗАЯВКА #{order_id}\n\n"
            f"Услуга: {service_name}\n"
            f"Клиент: {user.full_name or user.username}\n"
            f"ID: {message.from_user.id}\n\n"
            f"📝 Данные заявки:\n{summary}"
        )
        for admin_id in ADMIN_IDS:
            await safe_send_message(admin_id, admin_message)
        
        await safe_send_message(
            message.from_user.id,
            f"{summary}\n\n💳 Оплата временно отключена для тестирования. Заявка принята!"
        )
        
        await state.clear()
        await clear_user_state(message.from_user.id)
        await show_main_menu(message.from_user.id, "✅ Заявка принята! Выберите другую услугу или вернитесь в меню.")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в finalize_order: {e}", exc_info=True)
        await safe_send_message(
            message.from_user.id,
            "Произошла ошибка при создании заявки. Пожалуйста, попробуйте позже."
        )

# ===================== ОБЩИЕ ОБРАБОТЧИКИ =====================
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
    
    back_map = {
        "TZStates": {"essence":"name", "audience":"essence", "features":"audience", "competitors":"features", "tech_limits":"competitors", "deadline":"tech_limits", "budget":"deadline", "files":"budget"},
        "TEOStates": {"resources":"goal", "risks":"resources", "norms":"risks", "effect":"norms", "data":"effect", "horizon":"data", "files":"horizon"},
        "FMStates": {"costs":"income", "investment":"costs", "breakeven":"investment", "metrics":"breakeven", "data":"metrics", "horizon":"data"},
        "BPStates": {"product":"summary", "competitors":"product", "marketing":"competitors", "team":"marketing", "sales":"team", "risks":"sales", "capital":"risks", "finance_file":"capital", "files":"finance_file"},
    }
    prefix = current_state.split(":")[0]
    step = current_state.split(":")[1]
    if prefix in back_map and step in back_map[prefix]:
        prev = back_map[prefix][step]
        cls = globals()[prefix]
        await state.set_state(getattr(cls, prev))
        await safe_send_message(message.from_user.id, "🔙 Вернулись назад.", reply_markup=nav_keyboard())
    else:
        await safe_send_message(message.from_user.id, "Это первый шаг.", reply_markup=nav_keyboard())

@dp.message(lambda msg: msg.text == "📩 Написать разработчику")
async def start_feedback(message: types.Message, state: FSMContext):
    await state.set_state(FeedbackStates.waiting_for_message)
    await safe_send_message(
        message.from_user.id,
        "📝 Напишите ваше сообщение разработчику (до 1000 символов).\nДля отмены нажмите «Отмена».",
        reply_markup=feedback_keyboard()
    )

@dp.message(FeedbackStates.waiting_for_message)
async def process_feedback(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await safe_send_message(message.from_user.id, "✅ Отправка отменена.", reply_markup=main_menu_keyboard())
        return
    if not message.text:
        await safe_send_message(message.from_user.id, "Пожалуйста, напишите текст сообщения.")
        return
    text = message.text.strip()
    if len(text) > 1000:
        await safe_send_message(
            message.from_user.id,
            f"❌ Сообщение слишком длинное ({len(text)} символов). Максимум 1000."
        )
        return
    report = (
        f"📩 НОВОЕ СООБЩЕНИЕ\n\n"
        f"👤 {message.from_user.full_name}\n"
        f"🆔 {message.from_user.id}\n"
        f"📝 {text}"
    )
    for admin_id in ADMIN_IDS:
        await safe_send_message(admin_id, report)
    await state.clear()
    await safe_send_message(
        message.from_user.id,
        "✅ Сообщение отправлено. Мы свяжемся с вами.",
        reply_markup=main_menu_keyboard()
    )

# ===================== ТЕХНИЧЕСКОЕ ЗАДАНИЕ =====================
@dp.message(lambda msg: msg.text == "📋 Техническое задание")
async def start_tz(message: types.Message, state: FSMContext):
    await state.set_state(TZStates.name)
    await safe_send_message(
        message.from_user.id,
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
        await safe_send_message(user_id, "❌ Введите название (минимум 2 символа)", reply_markup=nav_keyboard())
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
        await safe_send_message(user_id, "❌ Опишите суть подробнее (минимум 5 символов)", reply_markup=nav_keyboard())
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
        await safe_send_message(user_id, "❌ Перечислите функции (минимум 3 символа)", reply_markup=nav_keyboard())
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
    
    data = await state.get_data()
    fields = {
        "name": "Название",
        "essence": "Суть проекта",
        "audience": "Клиенты",
        "features": "Функции",
        "competitors": "Конкуренты",
        "tech_limits": "Тех. рамки",
        "deadline": "Срок",
        "budget": "Бюджет",
        "file_url": "Ссылка на файл"
    }
    await finalize_order(message, state, "Техническое задание", fields)

# ===================== ТЭО =====================
@dp.message(lambda msg: msg.text == "📊 ТЭО")
async def start_teo(message: types.Message, state: FSMContext):
    await state.set_state(TEOStates.goal)
    await safe_send_message(
        message.from_user.id,
        "📊 **Шаг 1 из 8: Цель ТЭО**\n\nКакова основная цель вашего проекта?\n(например: запуск нового продукта, выход на рынок, привлечение инвестиций)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.goal)
async def teo_goal(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if not text or len(text) < 5:
        await safe_send_message(user_id, "❌ Опишите цель подробнее (минимум 5 символов)", reply_markup=nav_keyboard())
        return
    await state.update_data(goal=text)
    await state.set_state(TEOStates.resources)
    await safe_send_message(
        user_id,
        "📊 **Шаг 2 из 8: Ресурсы**\n\nКакие ресурсы вам нужны?\n(финансовые, людские, материальные)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.resources)
async def teo_resources(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.goal)
        await safe_send_message(user_id, "🔙 Вернулись. Опишите цель:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(resources="")
    else:
        await state.update_data(resources=text)
    await state.set_state(TEOStates.risks)
    await safe_send_message(
        user_id,
        "📊 **Шаг 3 из 8: Риски**\n\nКакие риски вы видите? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.risks)
async def teo_risks(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.resources)
        await safe_send_message(user_id, "🔙 Вернулись. Какие ресурсы нужны?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(risks="")
    else:
        await state.update_data(risks=text)
    await state.set_state(TEOStates.norms)
    await safe_send_message(
        user_id,
        "📊 **Шаг 4 из 8: Нормативная база**\n\nЕсть ли нормативные требования? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.norms)
async def teo_norms(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.risks)
        await safe_send_message(user_id, "🔙 Вернулись. Какие риски?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(norms="")
    else:
        await state.update_data(norms=text)
    await state.set_state(TEOStates.effect)
    await safe_send_message(
        user_id,
        "📊 **Шаг 5 из 8: Эффект**\n\nКакой экономический эффект ожидаете? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.effect)
async def teo_effect(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.norms)
        await safe_send_message(user_id, "🔙 Вернулись. Нормативные требования?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(effect="")
    else:
        await state.update_data(effect=text)
    await state.set_state(TEOStates.data)
    await safe_send_message(
        user_id,
        "📊 **Шаг 6 из 8: Данные**\n\nКакие исходные данные у вас есть? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.data)
async def teo_data(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.effect)
        await safe_send_message(user_id, "🔙 Вернулись. Какой эффект?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(data="")
    else:
        await state.update_data(data=text)
    await state.set_state(TEOStates.horizon)
    await safe_send_message(
        user_id,
        "📊 **Шаг 7 из 8: Горизонт планирования**\n\nНа какой срок планируете? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.horizon)
async def teo_horizon(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.data)
        await safe_send_message(user_id, "🔙 Вернулись. Какие данные?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(horizon="")
    else:
        await state.update_data(horizon=text)
    await state.set_state(TEOStates.files)
    await safe_send_message(
        user_id,
        "📊 **Шаг 8 из 8: Файлы**\n\nПриложите файлы или нажмите «Пропустить».",
        reply_markup=nav_keyboard()
    )

@dp.message(TEOStates.files)
async def teo_files(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(TEOStates.horizon)
        await safe_send_message(user_id, "🔙 Вернулись. Горизонт планирования?", reply_markup=nav_keyboard())
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
    data = await state.get_data()
    fields = {
        "goal": "Цель ТЭО",
        "resources": "Ресурсы",
        "risks": "Риски",
        "norms": "Нормативная база",
        "effect": "Ожидаемый эффект",
        "data": "Исходные данные",
        "horizon": "Горизонт планирования",
        "file_url": "Ссылка на файл"
    }
    await finalize_order(message, state, "ТЭО", fields)

# ===================== ФИНАНСОВАЯ МОДЕЛЬ =====================
@dp.message(lambda msg: msg.text == "💰 Финансовая модель")
async def start_fm(message: types.Message, state: FSMContext):
    await state.set_state(FMStates.income)
    await safe_send_message(
        message.from_user.id,
        "💰 **Шаг 1 из 7: Доходы**\n\nКакие источники доходов у проекта?\n(можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.income)
async def fm_income(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(income="")
    else:
        await state.update_data(income=text)
    await state.set_state(FMStates.costs)
    await safe_send_message(
        user_id,
        "💰 **Шаг 2 из 7: Расходы**\n\nКакие расходы вы ожидаете? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.costs)
async def fm_costs(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(FMStates.income)
        await safe_send_message(user_id, "🔙 Вернулись. Какие доходы?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(costs="")
    else:
        await state.update_data(costs=text)
    await state.set_state(FMStates.investment)
    await safe_send_message(
        user_id,
        "💰 **Шаг 3 из 7: Инвестиции**\n\nКакой объем инвестиций требуется? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.investment)
async def fm_investment(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(FMStates.costs)
        await safe_send_message(user_id, "🔙 Вернулись. Какие расходы?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(investment="")
    else:
        await state.update_data(investment=text)
    await state.set_state(FMStates.breakeven)
    await safe_send_message(
        user_id,
        "💰 **Шаг 4 из 7: Точка безубыточности**\n\nКогда планируете выйти на безубыточность? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.breakeven)
async def fm_breakeven(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(FMStates.investment)
        await safe_send_message(user_id, "🔙 Вернулись. Объем инвестиций?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(breakeven="")
    else:
        await state.update_data(breakeven=text)
    await state.set_state(FMStates.metrics)
    await safe_send_message(
        user_id,
        "💰 **Шаг 5 из 7: Ключевые метрики**\n\nКакие метрики важны? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.metrics)
async def fm_metrics(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(FMStates.breakeven)
        await safe_send_message(user_id, "🔙 Вернулись. Точка безубыточности?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(metrics="")
    else:
        await state.update_data(metrics=text)
    await state.set_state(FMStates.data)
    await safe_send_message(
        user_id,
        "💰 **Шаг 6 из 7: Данные для модели**\n\nКакие данные есть для расчетов? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.data)
async def fm_data(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(FMStates.metrics)
        await safe_send_message(user_id, "🔙 Вернулись. Какие метрики?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(data="")
    else:
        await state.update_data(data=text)
    await state.set_state(FMStates.horizon)
    await safe_send_message(
        user_id,
        "💰 **Шаг 7 из 7: Горизонт модели**\n\nНа какой срок строить модель? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(FMStates.horizon)
async def fm_horizon(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(FMStates.data)
        await safe_send_message(user_id, "🔙 Вернулись. Какие данные?", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(horizon="")
    else:
        await state.update_data(horizon=text)
    
    data = await state.get_data()
    fields = {
        "income": "Доходы",
        "costs": "Расходы",
        "investment": "Инвестиции",
        "breakeven": "Точка безубыточности",
        "metrics": "Ключевые метрики",
        "data": "Данные для модели",
        "horizon": "Горизонт модели"
    }
    await finalize_order(message, state, "Финансовая модель", fields)

# ===================== БИЗНЕС-ПЛАН =====================
@dp.message(lambda msg: msg.text == "📈 Бизнес-план")
async def start_bp(message: types.Message, state: FSMContext):
    await state.set_state(BPStates.summary)
    await safe_send_message(
        message.from_user.id,
        "📈 **Шаг 1 из 10: Резюме**\n\nКраткое описание бизнес-идеи (2-3 предложения)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.summary)
async def bp_summary(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if not text or len(text) < 5:
        await safe_send_message(user_id, "❌ Опишите резюме подробнее (минимум 5 символов)", reply_markup=nav_keyboard())
        return
    await state.update_data(summary=text)
    await state.set_state(BPStates.product)
    await safe_send_message(
        user_id,
        "📈 **Шаг 2 из 10: Продукт**\n\nЧто вы предлагаете? Опишите продукт или услугу.",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.product)
async def bp_product(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.summary)
        await safe_send_message(user_id, "🔙 Вернулись. Резюме:", reply_markup=nav_keyboard())
        return
    if not text or len(text) < 5:
        await safe_send_message(user_id, "❌ Опишите продукт подробнее (минимум 5 символов)", reply_markup=nav_keyboard())
        return
    await state.update_data(product=text)
    await state.set_state(BPStates.competitors)
    await safe_send_message(
        user_id,
        "📈 **Шаг 3 из 10: Конкуренты**\n\nКто ваши конкуренты? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.competitors)
async def bp_competitors(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.product)
        await safe_send_message(user_id, "🔙 Вернулись. Опишите продукт:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=text)
    await state.set_state(BPStates.marketing)
    await safe_send_message(
        user_id,
        "📈 **Шаг 4 из 10: Маркетинг**\n\nКак вы планируете привлекать клиентов?",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.marketing)
async def bp_marketing(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.competitors)
        await safe_send_message(user_id, "🔙 Вернулись. Конкуренты:", reply_markup=nav_keyboard())
        return
    if not text or len(text) < 3:
        await safe_send_message(user_id, "❌ Опишите маркетинговую стратегию (минимум 3 символа)", reply_markup=nav_keyboard())
        return
    await state.update_data(marketing=text)
    await state.set_state(BPStates.team)
    await safe_send_message(
        user_id,
        "📈 **Шаг 5 из 10: Команда**\n\nКто входит в команду проекта? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.team)
async def bp_team(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.marketing)
        await safe_send_message(user_id, "🔙 Вернулись. Маркетинг:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(team="")
    else:
        await state.update_data(team=text)
    await state.set_state(BPStates.sales)
    await safe_send_message(
        user_id,
        "📈 **Шаг 6 из 10: Продажи**\n\nКакой канал продаж вы используете? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.sales)
async def bp_sales(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.team)
        await safe_send_message(user_id, "🔙 Вернулись. Команда:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(sales="")
    else:
        await state.update_data(sales=text)
    await state.set_state(BPStates.risks)
    await safe_send_message(
        user_id,
        "📈 **Шаг 7 из 10: Риски**\n\nКакие риски вы видите? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.risks)
async def bp_risks(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.sales)
        await safe_send_message(user_id, "🔙 Вернулись. Продажи:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(risks="")
    else:
        await state.update_data(risks=text)
    await state.set_state(BPStates.capital)
    await safe_send_message(
        user_id,
        "📈 **Шаг 8 из 10: Капитал**\n\nКакой начальный капитал требуется? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.capital)
async def bp_capital(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.risks)
        await safe_send_message(user_id, "🔙 Вернулись. Риски:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(capital="")
    else:
        await state.update_data(capital=text)
    await state.set_state(BPStates.finance_file)
    await safe_send_message(
        user_id,
        "📈 **Шаг 9 из 10: Финансы**\n\nЕсть ли финансовые расчеты или файлы? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.finance_file)
async def bp_finance_file(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.capital)
        await safe_send_message(user_id, "🔙 Вернулись. Капитал:", reply_markup=nav_keyboard())
        return
    if text in ["⏭ Пропустить", "пропустить"]:
        await state.update_data(finance_file="")
    else:
        await state.update_data(finance_file=text)
    await state.set_state(BPStates.files)
    await safe_send_message(
        user_id,
        "📈 **Шаг 10 из 10: Файлы**\n\nПриложите файлы или нажмите «Пропустить».",
        reply_markup=nav_keyboard()
    )

@dp.message(BPStates.files)
async def bp_files(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text == "🏠 Главное меню":
        await clear_and_go_home(message, state)
        return
    if text == "🔙 Назад":
        await state.set_state(BPStates.finance_file)
        await safe_send_message(user_id, "🔙 Вернулись. Финансы:", reply_markup=nav_keyboard())
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
    data = await state.get_data()
    fields = {
        "summary": "Резюме",
        "product": "Продукт",
        "competitors": "Конкуренты",
        "marketing": "Маркетинг",
        "team": "Команда",
        "sales": "Продажи",
        "risks": "Риски",
        "capital": "Капитал",
        "finance_file": "Финансовые расчеты",
        "file_url": "Ссылка на файл"
    }
    await finalize_order(message, state, "Бизнес-план", fields)

# ===================== НАСТРОЙКА ВЕБХУКОВ =====================
async def on_startup(app: web.Application):
    """Действия при запуске"""
    logger.info("🚀 Запуск бота...")
    await init_db()
    await migrate_db()
    
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

async def on_shutdown(app: web.Application):
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
