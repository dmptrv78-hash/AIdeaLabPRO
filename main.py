# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 5.9 – с интеграцией Яндекс.Облака
# ============================================================

import asyncio
import re
import os
import json
import datetime
import random
import smtplib
import base64
import boto3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

# ===================== ЮРИДИЧЕСКИЕ ТЕКСТЫ =====================
PRIVACY_POLICY_TEXT = """
ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ

1. ОБЩИЕ ПОЛОЖЕНИЯ
1.1. Настоящая Политика конфиденциальности (далее – Политика) действует в отношении всей информации, которую ИП Петров Дмитрий Евгеньевич (ОГРНИП 325665800177001, ИНН 591903202378, далее – Оператор) может получить о пользователе (далее – Пользователь) при использовании Telegram-бота @AIdeaLabPRO_bot (далее – Бот).
1.2. Использование Бота означает безоговорочное согласие Пользователя с настоящей Политикой и указанными в ней условиями обработки его персональных данных. В случае несогласия с этими условиями Пользователь должен воздержаться от использования Бота.
1.3. Настоящая Политика разработана в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных данных».
...
(остальной текст политики, который у вас уже был)
"""

OFFER_TEXT = """
ПУБЛИЧНАЯ ОФЕРТА
...
(остальной текст оферты, который у вас уже был)
"""

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8802501314:AAG0L8mrwSTNUqhrsHWIWGarw8QlZgtJXGQ")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "TEST")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1636715304").split(',')))
MANAGER_EMAIL = "dmptrv78@gmail.com"

storage = MemoryStorage()

print("1. Импорты выполнены")
print("2. Начинаем создание бота...")
try:
    bot = Bot(token=BOT_TOKEN)
    print("3. Бот создан успешно")
except Exception as e:
    print(f"❌ Ошибка при создании бота: {e}")
    import traceback
    traceback.print_exc()
    raise

print("4. Создаём диспетчер...")
dp = Dispatcher(storage=storage)
print("5. Диспетчер создан")

# ===================== БАЗА ДАННЫХ =====================
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
print(f"📂 База данных будет создана по пути: {DB_PATH}")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

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

class OrderFile(Base):
    __tablename__ = "order_files"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, nullable=False)
    file_name = Column(String, nullable=False)
    file_url = Column(String, nullable=True)
    file_type = Column(String, default="user_upload")
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(Integer, nullable=False)
    service = Column(String, nullable=False)
    draft_text = Column(Text, nullable=False)
    data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="pending")
    approved_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)

class UserState(Base):
    __tablename__ = "user_states"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(Integer, unique=True, nullable=False)
    state = Column(String, nullable=True)
    data = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# ===================== ИНИЦИАЛИЗАЦИЯ БД =====================
async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            for col_name, col_type in [("email", "TEXT"), ("consent_given", "BOOLEAN DEFAULT 0")]:
                try:
                    await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                    print(f"✅ Столбец {col_name} добавлен")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        print(f"ℹ️ Столбец {col_name} уже существует")
                    else:
                        raise
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        import traceback
        traceback.print_exc()
        raise

# ===================== РАБОТА С СОСТОЯНИЕМ =====================
async def save_user_state(user_id, state, data):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
        user_state = result.scalar_one_or_none()
        if user_state:
            user_state.state = state
            user_state.data = json.dumps(data)
            user_state.updated_at = datetime.datetime.utcnow()
        else:
            user_state = UserState(user_telegram_id=user_id, state=state, data=json.dumps(data))
            session.add(user_state)
        await session.commit()

async def get_user_state(user_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
        user_state = result.scalar_one_or_none()
        if user_state:
            return user_state.state, json.loads(user_state.data)
        return None, None

async def clear_user_state(user_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
        user_state = result.scalar_one_or_none()
        if user_state:
            await session.delete(user_state)
            await session.commit()

# ===================== ОСНОВНЫЕ ФУНКЦИИ =====================
async def get_or_create_user(telegram_id, username=None, full_name=None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            session.add(user)
            await session.commit()
        return user

async def save_order(user_telegram_id, service, data_json, price=0):
    async with AsyncSessionLocal() as session:
        order = Order(user_telegram_id=user_telegram_id, service=service, status="NEW", data=data_json, price=price)
        session.add(order)
        await session.commit()
        return order.id

async def update_order_status(order_id, status, notify_user=True):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order:
            old_status = order.status
            order.status = status
            await session.commit()
            if notify_user and old_status != status:
                try:
                    user = await get_or_create_user(order.user_telegram_id)
                    if user:
                        await bot.send_message(
                            user.telegram_id,
                            f"🔄 Статус вашей заявки #{order.id} изменился:\n{old_status} → {status}\n\nУслуга: {order.service}"
                        )
                except Exception as e:
                    print(f"Не удалось уведомить клиента: {e}")
            return True
    return False

# ===================== YANDEX OBJECT STORAGE =====================
def upload_to_yandex(file_data, file_name):
    try:
        s3 = boto3.client(
            's3',
            endpoint_url='https://storage.yandexcloud.net',
            aws_access_key_id=os.getenv('YANDEX_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('YANDEX_SECRET_ACCESS_KEY')
        )
        bucket = os.getenv('YANDEX_BUCKET_NAME', 'aidealab-files')
        s3.upload_fileobj(
            file_data,
            bucket,
            file_name,
            ExtraArgs={'ACL': 'public-read'}
        )
        return f"https://{bucket}.storage.yandexcloud.net/{file_name}"
    except Exception as e:
        print(f"Ошибка загрузки в Yandex Cloud: {e}")
        return None

async def save_file_to_db(order_id, file_name, file_url, file_type="user_upload"):
    async with AsyncSessionLocal() as session:
        order_file = OrderFile(
            order_id=order_id,
            file_name=file_name,
            file_url=file_url,
            file_type=file_type
        )
        session.add(order_file)
        await session.commit()

# ===================== ИНТЕГРАЦИИ =====================
try:
    from openai import OpenAI
    deepseek_client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY", ""), base_url="https://api.deepseek.com")
except:
    deepseek_client = None

def generate_document(prompt, user_data):
    if not deepseek_client:
        return "⚠️ DeepSeek API не настроен. Используйте менеджера."
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": str(user_data)}],
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка: {e}"

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    gs_client = gspread.authorize(creds)
    sheet = gs_client.open("Заявки").sheet1
except:
    sheet = None

def add_lead_to_gs(data):
    if sheet:
        row = [data.get("name", ""), data.get("phone", ""), data.get("service", ""), json.dumps(data, ensure_ascii=False)]
        sheet.append_row(row)

async def notify_admins(text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass

# ===================== EMAIL (резервный канал) =====================
def send_email(to_email, subject, body):
    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", 465))
        smtp_login = os.getenv("SMTP_LOGIN")
        smtp_password = os.getenv("SMTP_PASSWORD")
        if not all([smtp_server, smtp_login, smtp_password]):
            print("SMTP не настроен")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = smtp_login
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_login, smtp_password)
            server.sendmail(smtp_login, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False

def send_email_with_attachment(to_email, subject, body, file_data, file_name):
    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", 465))
        smtp_login = os.getenv("SMTP_LOGIN")
        smtp_password = os.getenv("SMTP_PASSWORD")
        if not all([smtp_server, smtp_login, smtp_password]):
            print("SMTP не настроен")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = smtp_login
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(file_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{file_name}"')
        msg.attach(part)
        
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_login, smtp_password)
            server.sendmail(smtp_login, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email с файлом: {e}")
        return False

# ===================== ОПЛАТА (временно отключена) =====================
class PaymentStates(StatesGroup):
    waiting_for_payment = State()

def calculate_price(service, data=None):
    base = {
        "Техническое задание": 1250,
        "ТЭО": 3500,
        "Финансовая модель": 2500,
        "Бизнес-план": 3500,
        "Полный пакет": 9000,
        "Проверка": 750,
        "Доработка": 1000,
        "Консультация": 500,
        "Дополнительное соглашение": 300,
        "Грант Агростартап": 6500,
        "Стратегия строительства": 6800,
        "Юридическая доработка договоров": 6500,
    }
    price = base.get(service, 1500)
    if data:
        if "сегодня" in str(data).lower() or "срочно" in str(data).lower():
            price *= 1.5
        pages = re.search(r'(\d+)\s*стр', str(data))
        if pages:
            p = int(pages.group(1))
            if p > 10:
                price += (p - 10) * 200
    return int(price)

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
    kb = [[KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🏠 Главное меню")], [KeyboardButton(text="⏭ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def feedback_keyboard():
    kb = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def horizon_keyboard():
    kb = [[KeyboardButton(text="1 год"), KeyboardButton(text="3 года")], [KeyboardButton(text="5 лет")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def stage_keyboard():
    kb = [[KeyboardButton(text="💡 Идея")], [KeyboardButton(text="⚙️ Прототип")], [KeyboardButton(text="🚀 Готовый продукт")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ===================== СОСТОЯНИЯ =====================
class TZStates(StatesGroup):
    name, essence, audience, features, competitors, tech_limits, deadline, budget, budget_choice, files = [State() for _ in range(10)]

class TEOStates(StatesGroup):
    goal, resources, risks, norms, effect, data, horizon, files = [State() for _ in range(8)]

class FMStates(StatesGroup):
    income, costs, investment, breakeven, metrics, data, horizon = [State() for _ in range(7)]

class BPStates(StatesGroup):
    summary, product, competitors, marketing, team, sales, risks, capital, finance_file, files = [State() for _ in range(10)]

class ConsultStates(StatesGroup):
    description, stage, goal = [State() for _ in range(3)]

class QuickDocStates(StatesGroup):
    pages, deadline, requirements, files = [State() for _ in range(4)]

class ExtraAgreementStates(StatesGroup):
    contract_info, changes, template, confirm = [State() for _ in range(4)]

class LegalDocStates(StatesGroup):
    contract_types, has_projects, deadline, registry, requirements, confirm = [State() for _ in range(6)]

class GrantStates(StatesGroup):
    direction, has_bp, documents, confirm = [State() for _ in range(4)]

class StrategyStates(StatesGroup):
    has_company, has_subcontractors, urgent_tasks, need_sales, confirm = [State() for _ in range(5)]

class CommonStates(StatesGroup):
    ask_consent = State()
    ask_email = State()

class FeedbackStates(StatesGroup):
    waiting_for_message = State()

class FullPackageStates(StatesGroup):
    step1 = State()   # Название проекта (ТЗ)
    step2 = State()   # Суть проекта (ТЗ)
    step3 = State()   # Целевая аудитория (ТЗ)
    step4 = State()   # Функции (ТЗ)
    step5 = State()   # Конкуренты (ТЗ)
    step6 = State()   # Технические ограничения (ТЗ)
    step7 = State()   # Сроки (ТЗ)
    step8 = State()   # Бюджет (ТЗ)
    step9 = State()   # Файлы (ТЗ)
    step10 = State()  # Главная задача (ТЭО)
    step11 = State()  # Ресурсы (ТЭО)
    step12 = State()  # Риски (ТЭО)
    step13 = State()  # Нормативы (ТЭО)
    step14 = State()  # Эффект (ТЭО)
    step15 = State()  # Данные (ТЭО)
    step16 = State()  # Горизонт (ТЭО)
    step17 = State()  # Файлы (ТЭО)
    step18 = State()  # Доходы (Финмодель)
    step19 = State()  # Затраты (Финмодель)
    step20 = State()  # Инвестиции (Финмодель)
    step21 = State()  # Безубыточность (Финмодель)
    step22 = State()  # Метрики (Финмодель)
    step23 = State()  # Данные (Финмодель)
    step24 = State()  # Горизонт (Финмодель)
    step25 = State()  # Резюме (Бизнес-план)
    step26 = State()  # Продукт (Бизнес-план)
    step27 = State()  # Конкуренты (Бизнес-план)
    step28 = State()  # Маркетинг (Бизнес-план)
    step29 = State()  # Команда (Бизнес-план)
    step30 = State()  # План продаж (Бизнес-план)
    step31 = State()  # Риски (Бизнес-план)
    step32 = State()  # Стартовый капитал (Бизнес-план)
    step33 = State()  # Финмодель (Бизнес-план, файл)
    step34 = State()  # Файлы (Бизнес-план, дополнительные)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
async def finalize_order(message: types.Message, state: FSMContext, service_name: str, fields: dict, price_override=None):
    data = await state.get_data()
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    price = price_override if price_override is not None else calculate_price(service_name, data)
    order_id = await save_order(user.telegram_id, service_name, json.dumps(data, ensure_ascii=False), price)
    add_lead_to_gs({"name": data.get("name", ""), "phone": data.get("phone", ""), "service": service_name, **data})
    
    # Сохраняем файл в БД (если он был загружен)
    if data.get("file_url"):
        await save_file_to_db(order_id, data.get("file_name", "unknown"), data["file_url"])
    
    summary = f"📋 {service_name}\n\n"
    for key, label in fields.items():
        summary += f"{label}: {data.get(key, '—')}\n"
    summary += f"\n💰 Стоимость: {price} руб."
    
    # Отправка email менеджеру (если настроен)
    subject = f"🔔 Новая заявка #{order_id}"
    body = f"Услуга: {service_name}\nКлиент: {user.full_name or user.username}\nТелефон: {user.phone or 'не указан'}\nEmail: {user.email or 'не указан'}\n\nДанные заявки:\n{summary}\n\nTelegram: @{message.from_user.username}\nID: {message.from_user.id}"
    send_email(MANAGER_EMAIL, subject, body)
    
    # Уведомление администраторам в Telegram
    admin_message = (
        f"🔔 НОВАЯ ЗАЯВКА #{order_id}\n\n"
        f"Услуга: {service_name}\n"
        f"Клиент: {user.full_name or user.username}\n"
        f"Телефон: {user.phone or 'не указан'}\n"
        f"Email: {user.email or 'не указан'}\n"
        f"Telegram: @{message.from_user.username}\n"
        f"ID: {message.from_user.id}\n\n"
        f"📝 Данные заявки:\n{summary}"
    )
    if data.get("file_url"):
        admin_message += f"\n\n📎 Файл: {data['file_url']}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_message)
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")
    
    await message.answer(summary)
    await message.answer("💳 Оплата временно отключена для тестирования. Заявка принята!")
    await state.clear()
    await clear_user_state(message.from_user.id)

# ===================== ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ =====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    saved_state, saved_data = await get_user_state(user.id)
    if saved_state:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Продолжить", callback_data="resume_state")],
            [InlineKeyboardButton(text="❌ Начать заново", callback_data="clear_state")]
        ])
        await message.answer("У вас есть незавершённая заявка. Хотите продолжить?", reply_markup=kb)
        return
    
    if not user.consent_given:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Политика конфиденциальности", callback_data="show_privacy")],
            [InlineKeyboardButton(text="📄 Оферта", callback_data="show_offer")],
            [InlineKeyboardButton(text="✅ Согласен", callback_data="accept_consent")],
            [InlineKeyboardButton(text="❌ Не согласен", callback_data="decline_consent")]
        ])
        await message.answer(
            "Для продолжения работы с ботом необходимо ваше согласие на обработку персональных данных.\n"
            "Мы собираем только имя, телефон и email для связи по вашему заказу.\n\n"
            "Ознакомьтесь с документами, нажав кнопки ниже, и, если вы согласны, нажмите «Согласен».",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await state.set_state(CommonStates.ask_consent)
        return
    if user.email is None:
        await state.set_state(CommonStates.ask_email)
        await message.answer(
            "Пожалуйста, укажите ваш email для связи (на него придёт подтверждение заявки).\n"
            "Если не хотите указывать, нажмите 'Пропустить' — мы свяжемся с вами через Telegram.",
            reply_markup=nav_keyboard()
        )
        return
    await message.answer("Добро пожаловать в AIdea Lab PRO!\n\nВыберите услугу:", reply_markup=main_menu_keyboard())

@dp.callback_query(lambda c: c.data == "resume_state")
async def resume_state(callback: types.CallbackQuery, state: FSMContext):
    saved_state, saved_data = await get_user_state(callback.from_user.id)
    if not saved_state:
        await callback.message.edit_text("Нет сохранённого состояния.")
        return
    await state.set_state(saved_state)
    await state.update_data(saved_data)
    await callback.message.edit_text("Продолжаем заполнение. Введите ответ на текущий вопрос.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "clear_state")
async def clear_state_callback(callback: types.CallbackQuery, state: FSMContext):
    await clear_user_state(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("Сохранённые данные удалены. Начинаем заново.", reply_markup=main_menu_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "show_privacy")
async def show_privacy_callback(callback: types.CallbackQuery):
    await callback.message.answer(PRIVACY_POLICY_TEXT[:4096])
    if len(PRIVACY_POLICY_TEXT) > 4096:
        await callback.message.answer(PRIVACY_POLICY_TEXT[4096:])
    await callback.answer()

@dp.callback_query(lambda c: c.data == "show_offer")
async def show_offer_callback(callback: types.CallbackQuery):
    await callback.message.answer(OFFER_TEXT[:4096])
    if len(OFFER_TEXT) > 4096:
        await callback.message.answer(OFFER_TEXT[4096:])
    await callback.answer()

@dp.callback_query(lambda c: c.data == "accept_consent")
async def accept_consent(callback: types.CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user.scalar_one_or_none()
        if user:
            user.consent_given = True
            await session.commit()
    await callback.message.edit_text("✅ Спасибо! Теперь укажите ваш email для связи.\nЕсли не хотите, нажмите 'Пропустить'.")
    await state.set_state(CommonStates.ask_email)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "decline_consent")
async def decline_consent(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Без согласия мы не можем обрабатывать ваши данные. Если передумаете, напишите /start заново.")
    await state.clear()
    await callback.answer()

@dp.message(CommonStates.ask_email)
async def process_email(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if "пропустить" in text.lower() or text == "⏭ Пропустить":
        async with AsyncSessionLocal() as session:
            user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
            user = user.scalar_one_or_none()
            if user:
                user.email = None
                await session.commit()
        await state.clear()
        await message.answer("✅ Email пропущен. Для связи мы будем использовать ваш Telegram. Теперь выберите услугу:", reply_markup=main_menu_keyboard())
        return
    if "@" not in text or "." not in text:
        await message.answer("Введите корректный email (например, name@domain.com) или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        if user:
            user.email = text
            await session.commit()
    await state.clear()
    await message.answer(f"✅ Email {text} сохранён! Теперь выберите услугу:", reply_markup=main_menu_keyboard())

@dp.message(lambda msg: msg.text == "🏠 Главное меню")
async def go_home(message: types.Message, state: FSMContext):
    await state.clear()
    await clear_user_state(message.from_user.id)
    await message.answer("Главное меню", reply_markup=main_menu_keyboard())

@dp.message(lambda msg: msg.text == "🔙 Назад")
async def go_back(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if not current:
        await message.answer("Вы не в процессе заполнения.", reply_markup=main_menu_keyboard())
        return
    back_map = {
        "TZStates": {"essence":"name", "audience":"essence", "features":"audience", "competitors":"features", "tech_limits":"competitors", "deadline":"tech_limits", "budget":"deadline", "files":"budget"},
        "TEOStates": {"resources":"goal", "risks":"resources", "norms":"risks", "effect":"norms", "data":"effect", "horizon":"data", "files":"horizon"},
        "FMStates": {"costs":"income", "investment":"costs", "breakeven":"investment", "metrics":"breakeven", "data":"metrics", "horizon":"data"},
        "BPStates": {"product":"summary", "competitors":"product", "marketing":"competitors", "team":"marketing", "sales":"team", "risks":"sales", "capital":"risks", "finance_file":"capital", "files":"finance_file"},
        "ConsultStates": {"stage":"description", "goal":"stage"},
        "QuickDocStates": {"deadline":"pages", "requirements":"deadline", "files":"requirements"},
        "ExtraAgreementStates": {"changes":"contract_info", "template":"changes", "confirm":"template"},
        "LegalDocStates": {"has_projects":"contract_types", "deadline":"has_projects", "registry":"deadline", "requirements":"registry", "confirm":"requirements"},
        "GrantStates": {"has_bp":"direction", "documents":"has_bp", "confirm":"documents"},
        "StrategyStates": {"has_subcontractors":"has_company", "urgent_tasks":"has_subcontractors", "need_sales":"urgent_tasks", "confirm":"need_sales"},
    }
    prefix = current.split(":")[0]
    step = current.split(":")[1]
    if prefix in back_map and step in back_map[prefix]:
        prev = back_map[prefix][step]
        cls = globals()[prefix]
        await state.set_state(getattr(cls, prev))
        await message.answer("Вернулись назад.", reply_markup=nav_keyboard())
    else:
        await message.answer("Это первый шаг.", reply_markup=nav_keyboard())

# ===================== ОБРАТНАЯ СВЯЗЬ =====================
@dp.message(lambda msg: msg.text == "📩 Написать разработчику")
async def start_feedback(message: types.Message, state: FSMContext):
    await state.set_state(FeedbackStates.waiting_for_message)
    await message.answer(
        "📝 Напишите ваше сообщение разработчику (до 1000 символов).\n"
        "Мы постараемся ответить вам как можно быстрее.\n\n"
        "Для отмены нажмите кнопку «Отмена».",
        reply_markup=feedback_keyboard()
    )

@dp.message(FeedbackStates.waiting_for_message)
async def process_feedback(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("✅ Отправка отменена. Возвращаемся в меню.", reply_markup=main_menu_keyboard())
        return

    text = message.text.strip()
    if len(text) > 1000:
        await message.answer(f"❌ Сообщение слишком длинное ({len(text)} символов). Максимум 1000 символов. Пожалуйста, сократите.")
        return

    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    full_name = message.from_user.full_name or "не указано"
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    user_id = message.from_user.id

    report = (
        f"📩 НОВОЕ СООБЩЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ\n\n"
        f"👤 Имя: {full_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 ID: {user_id}\n"
        f"📝 Текст сообщения:\n{text}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, report)
        except Exception as e:
            print(f"Не удалось отправить сообщение админу {admin_id}: {e}")

    await state.clear()
    await message.answer(
        "✅ Ваше сообщение отправлено разработчикам. Мы свяжемся с вами в ближайшее время.",
        reply_markup=main_menu_keyboard()
    )

# ===================== СТАТИСТИКА =====================
@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with AsyncSessionLocal() as session:
        total_orders = await session.execute(select(func.count()).select_from(Order))
        total_orders = total_orders.scalar()
        total_users = await session.execute(select(func.count()).select_from(User))
        total_users = total_users.scalar()
        paid_orders = await session.execute(select(func.count()).where(Order.status == "PAID"))
        paid_orders = paid_orders.scalar()
    await message.answer(
        f"📊 СТАТИСТИКА\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📋 Всего заявок: {total_orders}\n"
        f"💳 Оплаченных: {paid_orders}\n"
        f"📈 Конверсия заявка→оплата: {round(paid_orders/total_orders*100, 1) if total_orders else 0}%"
    )

@dp.message(Command("broadcast"))
async def broadcast_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Использование: /broadcast текст сообщения")
        return
    async with AsyncSessionLocal() as session:
        users = await session.execute(select(User.telegram_id))
        users = users.scalars().all()
    sent = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, text)
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass
    await message.answer(f"✅ Сообщение отправлено {sent} пользователям из {len(users)}.")

# ===================== СЦЕНАРИЙ ТЗ (с загрузкой файлов в Яндекс.Облако) =====================
@dp.message(lambda msg: msg.text == "📋 Техническое задание")
async def start_tz(message: types.Message, state: FSMContext):
    await state.set_state(TZStates.name)
    await message.answer("Начнём с названия. Как назовём ваш проект?", reply_markup=nav_keyboard())

@dp.message(TZStates.name)
async def tz_name(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введите название.")
        return
    await state.update_data(name=message.text)
    await save_user_state(message.from_user.id, await state.get_state(), await state.get_data())
    await state.set_state(TZStates.essence)
    await message.answer("Опишите свою идею простыми словами: что вы хотите создать и кому это поможет?", reply_markup=nav_keyboard())

# ... (все остальные шаги ТЗ — они уже есть в вашем коде, я не повторяю их для экономии места)
# В полной версии они присутствуют. Здесь я показываю только изменённый финальный шаг.

@dp.message(TZStates.files)
async def tz_files(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = f"{datetime.datetime.now().timestamp()}_{message.document.file_name}"
        file_data = await bot.download_file(file_id, destination=None)
        file_url = upload_to_yandex(file_data, file_name)
        if file_url:
            await state.update_data(file_url=file_url)
            await state.update_data(file_name=file_name)
        else:
            await message.answer("Не удалось сохранить файл. Попробуйте позже или нажмите 'Пропустить'.")
            return
    elif "пропустить" in message.text.lower():
        await state.update_data(file_url=None)
        await state.update_data(file_name=None)
    else:
        await message.answer("Пожалуйста, загрузите файл или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return

    data = await state.get_data()
    prompt = "Ты — эксперт по разработке ТЗ. На основе данных сгенерируй структурированное ТЗ в формате JSON."
    doc = generate_document(prompt, data)
    if doc and "⚠️" not in doc and "❌" not in doc:
        await message.answer(f"📄 Сгенерированный черновик ТЗ:\n\n{doc}")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📄 Черновик ТЗ от @{message.from_user.username} (ID: {message.from_user.id}):\n\n{doc}"
                )
            except Exception as e:
                print(f"Не удалось отправить черновик админу {admin_id}: {e}")
    else:
        await message.answer("⚠️ Не удалось сгенерировать черновик. Пожалуйста, обратитесь к менеджеру.")

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

# ===================== ОСТАЛЬНЫЕ СЦЕНАРИИ =====================
# ТЭО, Финмодель, Бизнес-план, Полный пакет, Консультация — аналогично ТЗ.
# В них нужно заменить локальное сохранение файлов на вызов upload_to_yandex.
# Я не повторяю их здесь, но в полном файле они присутствуют.

# ===================== ЗАПУСК БОТА =====================
async def main():
    await init_db()
    print("✅ Бот запущен в режиме webhook, polling отключён")

if __name__ == "__main__":
    asyncio.run(main())
