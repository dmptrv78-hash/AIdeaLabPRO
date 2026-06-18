# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 4.1 – с email-уведомлениями
# ============================================================

import asyncio
import re
import os
import json
import datetime
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
    # LabeledPrice, PreCheckoutQuery, SuccessfulPayment  # временно отключены
)

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8802501314:AAG0L8mrwSTNUqhrsHWIWGarw8QlZgtJXGQ")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "TEST")
MANAGER_GROUP_ID = os.getenv("MANAGER_GROUP_ID", "-1001234567890")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(',')))

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
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite+aiosqlite:///bot.db"
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
    email = Column(String, nullable=True)   # <-- добавлено
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
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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

# ===================== ИНТЕГРАЦИИ =====================
# ---- DeepSeek API (опционально) ----
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

# ---- Google Sheets (опционально) ----
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

# ---- Уведомления менеджеров ----
async def notify_managers(text):
    try:
        await bot.send_message(chat_id=MANAGER_GROUP_ID, text=text)
    except Exception:
        pass

# ===================== EMAIL =====================
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
        "Бизнес-план конный спорт": 6500,
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
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def nav_keyboard():
    kb = [[KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🏠 Главное меню")], [KeyboardButton(text="⏭ Пропустить")]]
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

class BPSportsStates(StatesGroup):
    infrastructure, scale, data_available, confirm = [State() for _ in range(4)]

class CommonStates(StatesGroup):   # <-- новое состояние для запроса email
    ask_email = State()

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
async def finalize_order(message: types.Message, state: FSMContext, service_name: str, fields: dict, price_override=None):
    data = await state.get_data()
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    price = price_override if price_override is not None else calculate_price(service_name, data)
    order_id = await save_order(user.telegram_id, service_name, json.dumps(data, ensure_ascii=False), price)
    add_lead_to_gs({"name": data.get("name", ""), "phone": data.get("phone", ""), "service": service_name, **data})
    
    summary = f"📋 {service_name}\n\n"
    for key, label in fields.items():
        summary += f"{label}: {data.get(key, '—')}\n"
    summary += f"\n💰 Стоимость: {price} руб."
    
    await notify_managers(f"🔔 Новая заявка #{order_id}\nУслуга: {service_name}\nКлиент: @{message.from_user.username}\nДанные: {json.dumps(data, ensure_ascii=False)}")
    
    # Отправка email менеджеру
    manager_email = os.getenv("MANAGER_EMAIL")
    if manager_email:
        subject = f"🔔 Новая заявка #{order_id}"
        body = f"Услуга: {service_name}\nКлиент: {user.full_name or user.username}\nТелефон: {user.phone or 'не указан'}\nEmail: {user.email or 'не указан'}\n\nДанные заявки:\n{summary}\n\nTelegram: @{message.from_user.username}\nID: {message.from_user.id}"
        send_email(manager_email, subject, body)
    
    await message.answer(summary)
    # Временно отключаем отправку счёта
    await message.answer("💳 Оплата временно отключена для тестирования. Заявка принята!")
    await state.clear()

# ===================== ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ =====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    if not user.email:
        await state.set_state(CommonStates.ask_email)
        await message.answer("Пожалуйста, укажите ваш email для связи (на него придёт подтверждение заявки):")
        return
    await message.answer("Добро пожаловать в AIdea Lab PRO!\n\nВыберите услугу:", reply_markup=main_menu_keyboard())

@dp.message(CommonStates.ask_email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if "@" not in email or "." not in email:
        await message.answer("Введите корректный email (например, name@domain.com)")
        return
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        if user:
            user.email = email
            await session.commit()
    await state.clear()
    await message.answer(f"✅ Email {email} сохранён! Теперь выберите услугу:", reply_markup=main_menu_keyboard())

@dp.message(lambda msg: msg.text == "🏠 Главное меню")
async def go_home(message: types.Message, state: FSMContext):
    await state.clear()
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
        "BPSportsStates": {"scale":"infrastructure", "data_available":"scale", "confirm":"data_available"},
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

# ===================== СЦЕНАРИЙ ТЕХНИЧЕСКОЕ ЗАДАНИЕ =====================
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
    await state.set_state(TZStates.essence)
    await message.answer("Опишите свою идею простыми словами: что вы хотите создать и кому это поможет?", reply_markup=nav_keyboard())

@dp.message(TZStates.essence)
async def tz_essence(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите суть.")
        return
    await state.update_data(essence=message.text)
    await state.set_state(TZStates.audience)
    await message.answer("Кто ваши клиенты или пользователи? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.audience)
async def tz_audience(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(audience="")
    else:
        await state.update_data(audience=message.text)
    await state.set_state(TZStates.features)
    await message.answer("Какие главные возможности должно иметь ваше решение? Напишите список через запятую.", reply_markup=nav_keyboard())

@dp.message(TZStates.features)
async def tz_features(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, перечислите функции.")
        return
    await state.update_data(features=message.text)
    await state.set_state(TZStates.competitors)
    await message.answer("Есть ли у вас конкуренты? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.competitors)
async def tz_competitors(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=message.text)
    await state.set_state(TZStates.tech_limits)
    await message.answer("Есть ли технические рамки? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.tech_limits)
async def tz_tech_limits(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(tech_limits="")
    else:
        await state.update_data(tech_limits=message.text)
    await state.set_state(TZStates.deadline)
    await message.answer("Когда вы хотите получить готовый результат? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.deadline)
async def tz_deadline(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(deadline="")
    else:
        await state.update_data(deadline=message.text)
    await state.set_state(TZStates.budget)
    await message.answer("Есть ли у вас бюджет на этот проект? Если да, укажите сумму. Если нет, напишите 'нет' или выберите 'Пропустить'.", reply_markup=nav_keyboard())

@dp.message(TZStates.budget)
async def tz_budget(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if text == "пропустить":
        await state.update_data(budget="")
        await state.set_state(TZStates.files)
        await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())
        return
    if text in ["нет", "нисколько", "0", "без бюджета", "не готов", "не знаю", "нет бюджета"]:
        await state.update_data(budget="0 (не указан)")
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="💬 Консультация")], [KeyboardButton(text="Продолжить")]], resize_keyboard=True)
        await message.answer("Понимаю. Хотите перейти к консультации или продолжить?", reply_markup=kb)
        await state.set_state(TZStates.budget_choice)
        return
    try:
        digits = re.sub(r'[^0-9]', '', text)
        if digits:
            budget = int(digits)
            await state.update_data(budget=f"{budget} руб.")
        else:
            await state.update_data(budget=text)
    except:
        await state.update_data(budget=text)
    await state.set_state(TZStates.files)
    await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())

@dp.message(TZStates.budget_choice)
async def tz_budget_choice(message: types.Message, state: FSMContext):
    if message.text == "💬 Консультация":
        await state.clear()
        await start_consult(message, state)
    else:
        await state.set_state(TZStates.files)
        await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())

@dp.message(TZStates.files)
async def tz_files(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(files=file_name)
    elif message.text.lower() == "пропустить":
        await state.update_data(files="")
    else:
        await message.answer("Пожалуйста, загрузите файл или нажмите 'Пропустить'.")
        return
    data = await state.get_data()
    prompt = "Ты — эксперт по разработке ТЗ. На основе данных сгенерируй структурированное ТЗ в формате JSON."
    doc = generate_document(prompt, data)
    if doc and "⚠️" not in doc and "❌" not in doc:
        await message.answer(f"📄 Сгенерированный черновик ТЗ:\n\n{doc}")
    fields = {
        "name": "Название",
        "essence": "Суть проекта",
        "audience": "Клиенты",
        "features": "Функции",
        "competitors": "Конкуренты",
        "tech_limits": "Тех. рамки",
        "deadline": "Срок",
        "budget": "Бюджет",
        "files": "Файлы"
    }
    await finalize_order(message, state, "Техническое задание", fields)

# ===================== СЦЕНАРИЙ ТЭО (сокращённо) =====================
@dp.message(lambda msg: msg.text == "📊 ТЭО")
async def start_teo(message: types.Message, state: FSMContext):
    await state.set_state(TEOStates.goal)
    await message.answer("Какую главную задачу вы решаете с помощью этого проекта?", reply_markup=nav_keyboard())

@dp.message(TEOStates.goal)
async def teo_goal(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите цель.")
        return
    await state.update_data(goal=message.text)
    await state.set_state(TEOStates.resources)
    await message.answer("Какие ресурсы вам понадобятся? (люди, техника, программы)", reply_markup=nav_keyboard())

@dp.message(TEOStates.resources)
async def teo_resources(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, перечислите ресурсы.")
        return
    await state.update_data(resources=message.text)
    await state.set_state(TEOStates.risks)
    await message.answer("Видите ли вы какие-то риски? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.risks)
async def teo_risks(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(risks="")
    else:
        await state.update_data(risks=message.text)
    await state.set_state(TEOStates.norms)
    await message.answer("Нужно ли соблюдать законы или стандарты? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.norms)
async def teo_norms(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(norms="")
    else:
        await state.update_data(norms=message.text)
    await state.set_state(TEOStates.effect)
    await message.answer("Какой финансовый результат вы ожидаете? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.effect)
async def teo_effect(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(effect="")
    else:
        await state.update_data(effect=message.text)
    await state.set_state(TEOStates.data)
    await message.answer("У вас уже есть какие-то расчёты или файлы? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.data)
async def teo_data(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(data="")
    else:
        await state.update_data(data=message.text)
    await state.set_state(TEOStates.horizon)
    await message.answer("На какой срок вы строите план?", reply_markup=horizon_keyboard())

@dp.message(TEOStates.horizon)
async def teo_horizon(message: types.Message, state: FSMContext):
    if message.text not in ["1 год", "3 года", "5 лет"]:
        await message.answer("Выберите из предложенных вариантов.", reply_markup=horizon_keyboard())
        return
    await state.update_data(horizon=message.text)
    await state.set_state(TEOStates.files)
    await message.answer("Приложите дополнительные материалы (пока можно только пропустить).", reply_markup=nav_keyboard())

@dp.message(TEOStates.files)
async def teo_files(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(files=file_name)
    elif message.text.lower() == "пропустить":
        await state.update_data(files="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.")
        return
    fields = {
        "goal": "Главная задача",
        "resources": "Ресурсы",
        "risks": "Риски",
        "norms": "Нормативы",
        "effect": "Эффект",
        "data": "Данные",
        "horizon": "Горизонт",
        "files": "Файлы"
    }
    await finalize_order(message, state, "ТЭО", fields)

# ===================== СЦЕНАРИЙ ФИНАНСОВАЯ МОДЕЛЬ =====================
@dp.message(lambda msg: msg.text == "💰 Финансовая модель")
async def start_fm(message: types.Message, state: FSMContext):
    await state.set_state(FMStates.income)
    await message.answer("Расскажите, из чего будет складываться ваш доход? Какие источники выручки?", reply_markup=nav_keyboard())

@dp.message(FMStates.income)
async def fm_income(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите доходы.")
        return
    await state.update_data(income=message.text)
    await state.set_state(FMStates.costs)
    await message.answer("Какие затраты вам предстоят? (постоянные и переменные)", reply_markup=nav_keyboard())

@dp.message(FMStates.costs)
async def fm_costs(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите затраты.")
        return
    await state.update_data(costs=message.text)
    await state.set_state(FMStates.investment)
    await message.answer("Сколько денег нужно вложить на старте?", reply_markup=nav_keyboard())

@dp.message(FMStates.investment)
async def fm_investment(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Укажите сумму инвестиций.")
        return
    await state.update_data(investment=message.text)
    await state.set_state(FMStates.breakeven)
    await message.answer("Через сколько месяцев планируете выйти на безубыточность? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(FMStates.breakeven)
async def fm_breakeven(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(breakeven="")
    else:
        await state.update_data(breakeven=message.text)
    await state.set_state(FMStates.metrics)
    await message.answer("Какие финансовые показатели важны? (ROI, маржинальность и т.д.) (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(FMStates.metrics)
async def fm_metrics(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(metrics="")
    else:
        await state.update_data(metrics=message.text)
    await state.set_state(FMStates.data)
    await message.answer("Есть готовые финансовые данные? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(FMStates.data)
async def fm_data(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(data="")
    else:
        await state.update_data(data=message.text)
    await state.set_state(FMStates.horizon)
    await message.answer("На какой период прогноз?", reply_markup=horizon_keyboard())

@dp.message(FMStates.horizon)
async def fm_horizon(message: types.Message, state: FSMContext):
    if message.text not in ["1 год", "3 года", "5 лет"]:
        await message.answer("Выберите вариант.", reply_markup=horizon_keyboard())
        return
    await state.update_data(horizon=message.text)
    fields = {
        "income": "Доходы",
        "costs": "Затраты",
        "investment": "Инвестиции",
        "breakeven": "Точка безубыточности",
        "metrics": "Показатели",
        "data": "Данные",
        "horizon": "Горизонт"
    }
    await finalize_order(message, state, "Финансовая модель", fields)

# ===================== СЦЕНАРИЙ БИЗНЕС-ПЛАН =====================
@dp.message(lambda msg: msg.text == "📈 Бизнес-план")
async def start_bp(message: types.Message, state: FSMContext):
    await state.set_state(BPStates.summary)
    await message.answer("Напишите краткое резюме проекта (1–2 предложения).", reply_markup=nav_keyboard())

@dp.message(BPStates.summary)
async def bp_summary(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, напишите резюме.")
        return
    await state.update_data(summary=message.text)
    await state.set_state(BPStates.product)
    await message.answer("Опишите подробнее ваш продукт или услугу. В чём уникальность?", reply_markup=nav_keyboard())

@dp.message(BPStates.product)
async def bp_product(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите продукт.")
        return
    await state.update_data(product=message.text)
    await state.set_state(BPStates.competitors)
    await message.answer("Кто ваши конкуренты? В чём преимущество?", reply_markup=nav_keyboard())

@dp.message(BPStates.competitors)
async def bp_competitors(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите конкурентов.")
        return
    await state.update_data(competitors=message.text)
    await state.set_state(BPStates.marketing)
    await message.answer("Как планируете привлекать клиентов?", reply_markup=nav_keyboard())

@dp.message(BPStates.marketing)
async def bp_marketing(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите маркетинг.")
        return
    await state.update_data(marketing=message.text)
    await state.set_state(BPStates.team)
    await message.answer("Расскажите о команде. (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.team)
async def bp_team(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(team="")
    else:
        await state.update_data(team=message.text)
    await state.set_state(BPStates.sales)
    await message.answer("Какой план продаж на первый год? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.sales)
async def bp_sales(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(sales="")
    else:
        await state.update_data(sales=message.text)
    await state.set_state(BPStates.risks)
    await message.answer("Какие риски видите и как их снизить? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.risks)
async def bp_risks(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(risks="")
    else:
        await state.update_data(risks=message.text)
    await state.set_state(BPStates.capital)
    await message.answer("Какой стартовый капитал? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.capital)
async def bp_capital(message: types.Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(capital="")
    else:
        await state.update_data(capital=message.text)
    await state.set_state(BPStates.finance_file)
    await message.answer("Приложите финансовую модель, если есть. (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.finance_file)
async def bp_finance_file(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(finance_file=file_name)
    elif message.text.lower() == "пропустить":
        await state.update_data(finance_file="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.")
        return
    await state.set_state(BPStates.files)
    await message.answer("Дополнительные материалы? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.files)
async def bp_files(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(files=file_name)
    elif message.text.lower() == "пропустить":
        await state.update_data(files="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.")
        return
    fields = {
        "summary": "Резюме",
        "product": "Продукт",
        "competitors": "Конкуренты",
        "marketing": "Маркетинг",
        "team": "Команда",
        "sales": "План продаж",
        "risks": "Риски",
        "capital": "Капитал",
        "finance_file": "Финмодель",
        "files": "Файлы"
    }
    await finalize_order(message, state, "Бизнес-план", fields)

# ===================== СЦЕНАРИЙ КОНСУЛЬТАЦИЯ =====================
@dp.message(lambda msg: msg.text == "💬 Консультация")
async def start_consult(message: types.Message, state: FSMContext):
    await state.set_state(ConsultStates.description)
    await message.answer("Расскажите в двух словах, над чем вы работаете.", reply_markup=nav_keyboard())

@dp.message(ConsultStates.description)
async def consult_description(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите проект.")
        return
    await state.update_data(description=message.text)
    await state.set_state(ConsultStates.stage)
    await message.answer("На каком этапе ваш проект?", reply_markup=stage_keyboard())

@dp.message(ConsultStates.stage)
async def consult_stage(message: types.Message, state: FSMContext):
    if message.text not in ["💡 Идея", "⚙️ Прототип", "🚀 Готовый продукт"]:
        await message.answer("Выберите из предложенных.", reply_markup=stage_keyboard())
        return
    await state.update_data(stage=message.text)
    await state.set_state(ConsultStates.goal)
    await message.answer("Чего вы хотите достичь с нашей помощью?", reply_markup=nav_keyboard())

@dp.message(ConsultStates.goal)
async def consult_goal(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите цель.")
        return
    await state.update_data(goal=message.text)
    data = await state.get_data()
    stage = data.get("stage", "")
    if "Идея" in stage:
        rec = "Рекомендуем начать с Технического задания."
    elif "Прототип" in stage:
        rec = "Рекомендуем Бизнес-план для инвесторов."
    else:
        rec = "Рекомендуем Финансовую модель и ТЭО."
    summary = f"📋 КОНСУЛЬТАЦИЯ\n\nПроект: {data.get('description')}\nЭтап: {stage}\nЦель: {data.get('goal')}\n\n💡 {rec}\n\nХотите перейти к заказу? Выберите услугу в меню."
    await message.answer(summary, reply_markup=main_menu_keyboard())
    await state.clear()

# ===================== МОИ ЗАЯВКИ =====================
@dp.message(lambda msg: msg.text == "📋 Мои заявки")
async def my_orders(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.user_telegram_id == user.telegram_id).order_by(Order.created_at.desc()))
        orders = result.scalars().all()
    if not orders:
        await message.answer("У вас пока нет заявок.", reply_markup=main_menu_keyboard())
        return
    text = "📋 ВАШИ ЗАЯВКИ:\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for order in orders:
        text += f"#{order.id} — {order.service} — {order.status}\n"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"Заявка #{order.id}", callback_data=f"view_order_{order.id}")])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(lambda c: c.data and c.data.startswith("view_order_"))
async def view_order(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
    if not order:
        await callback.message.answer("Заявка не найдена.")
        await callback.answer()
        return
    data = json.loads(order.data) if order.data else {}
    text = f"📄 ЗАЯВКА #{order.id}\n\n"
    text += f"Услуга: {order.service}\nСтатус: {order.status}\nДата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    if order.price:
        text += f"Стоимость: {order.price} руб.\n"
    text += "\n📝 Детали:\n"
    for key, val in data.items():
        text += f"{key}: {val}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К списку", callback_data="back_to_orders")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_orders")
async def back_to_orders(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await my_orders(callback.message, state)
    await callback.answer()

# ===================== АДМИНИСТРИРОВАНИЕ =====================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа.")
        return
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.status != "DONE").order_by(Order.created_at.desc()))
        orders = result.scalars().all()
    if not orders:
        await message.answer("Нет активных заявок.")
        return
    text = "🛠 АКТИВНЫЕ ЗАЯВКИ:\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for order in orders:
        text += f"#{order.id} — {order.service} — {order.status}\n"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"#{order.id}", callback_data=f"manage_order_{order.id}")])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(lambda c: c.data and c.data.startswith("manage_order_"))
async def manage_order(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа.")
        return
    order_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
    if not order:
        await callback.message.answer("Заявка не найдена.")
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"set_status_{order_id}_IN_PROGRESS")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data=f"set_status_{order_id}_DONE")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"set_status_{order_id}_CANCELLED")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="back_to_admin")]
    ])
    await callback.message.edit_text(f"Управление заявкой #{order_id}\nТекущий статус: {order.status}", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("set_status_"))
async def set_status(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа.")
        return
    parts = callback.data.split("_")
    order_id = int(parts[2])
    new_status = parts[3]
    if await update_order_status(order_id, new_status, notify_user=True):
        await callback.message.edit_text(f"Статус заявки #{order_id} изменён на {new_status}.")
        await notify_managers(f"🔄 Менеджер @{callback.from_user.username} изменил статус заявки #{order_id} на {new_status}")
    else:
        await callback.message.edit_text("Ошибка изменения статуса.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await admin_panel(callback.message, state)
    await callback.answer()

# ===================== ОБРАБОТЧИКИ СВОБОДНЫХ ЗАПРОСОВ =====================
@dp.message()
async def handle_free_text(message: types.Message, state: FSMContext):
    text = message.text.lower()
    if any(w in text for w in ["гпх", "смз", "тд", "отчуждение прав", "рид", "реестр по"]):
        await state.set_state(LegalDocStates.contract_types)
        await message.answer("Вы обратились за юридической доработкой договоров. Уточните:\nКакие договоры нужно доработать? (ГПХ, СМЗ, ТД, все три)", reply_markup=nav_keyboard())
        return
    if any(w in text for w in ["доп соглашение", "доп. соглашение", "дополнительное соглашение"]):
        await state.set_state(ExtraAgreementStates.contract_info)
        await message.answer("Дополнительное соглашение. Укажите номер и дату договора (можно пропустить).", reply_markup=nav_keyboard())
        return
    if any(w in text for w in ["грант", "агростартап", "минсельхоз"]):
        await state.set_state(GrantStates.direction)
        await message.answer("Грант Агростартап. Укажите направление (животноводство, растениеводство и т.д.)", reply_markup=nav_keyboard())
        return
    if any(w in text for w in ["строительство", "монолитное", "сро", "подрядчик", "охрана труда"]):
        await state.set_state(StrategyStates.has_company)
        await message.answer("Стратегия для строительного бизнеса. У вас уже есть ООО или ИП? (да/нет)", reply_markup=nav_keyboard())
        return
    if any(w in text for w in ["бизнес план", "окупаемость", "доходы расходы", "инвестиции", "конно-спортивный"]):
        await state.set_state(BPSportsStates.infrastructure)
        await message.answer("Бизнес-план. У вас есть земля и инфраструктура? (да/нет)", reply_markup=nav_keyboard())
        return
    await message.answer("Выберите услугу в меню или опишите задачу подробнее.", reply_markup=main_menu_keyboard())

# ===================== ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ =====================
@dp.message(ExtraAgreementStates.contract_info)
async def extra_contract(message: types.Message, state: FSMContext):
    await state.update_data(contract_info=message.text if message.text.lower() != "пропустить" else "не указано")
    await state.set_state(ExtraAgreementStates.changes)
    await message.answer("Что именно меняется? (цена, срок, условия)", reply_markup=nav_keyboard())

@dp.message(ExtraAgreementStates.changes)
async def extra_changes(message: types.Message, state: FSMContext):
    await state.update_data(changes=message.text)
    await state.set_state(ExtraAgreementStates.template)
    await message.answer("У вас есть свой шаблон? (да/нет, если нет — предложим наш)", reply_markup=nav_keyboard())

@dp.message(ExtraAgreementStates.template)
async def extra_template(message: types.Message, state: FSMContext):
    await state.update_data(template=message.text)
    data = await state.get_data()
    price = 300
    if "срочно" in str(data).lower() or "сегодня" in str(data).lower():
        price = 450
    await finalize_order(message, state, "Дополнительное соглашение", {
        "Договор": data.get("contract_info", "—"),
        "Изменения": data.get("changes", "—"),
        "Шаблон": data.get("template", "—")
    }, price_override=price)

# ===================== ГРАНТ АГРОСТАРТАП =====================
@dp.message(GrantStates.direction)
async def grant_direction(message: types.Message, state: FSMContext):
    await state.update_data(direction=message.text)
    await state.set_state(GrantStates.has_bp)
    await message.answer("У вас уже есть бизнес-план или нужно разработать с нуля?", reply_markup=nav_keyboard())

@dp.message(GrantStates.has_bp)
async def grant_has_bp(message: types.Message, state: FSMContext):
    await state.update_data(has_bp=message.text)
    await state.set_state(GrantStates.documents)
    await message.answer("Есть ли пакет документов для подачи? (регистрация, выписки)", reply_markup=nav_keyboard())

@dp.message(GrantStates.documents)
async def grant_documents(message: types.Message, state: FSMContext):
    await state.update_data(documents=message.text)
    data = await state.get_data()
    await finalize_order(message, state, "Грант Агростартап", {
        "Направление": data.get("direction", "—"),
        "Бизнес-план": data.get("has_bp", "—"),
        "Документы": data.get("documents", "—")
    }, price_override=6500)

# ===================== СТРАТЕГИЯ СТРОИТЕЛЬСТВА =====================
@dp.message(StrategyStates.has_company)
async def strategy_company(message: types.Message, state: FSMContext):
    await state.update_data(has_company=message.text)
    await state.set_state(StrategyStates.has_subcontractors)
    await message.answer("Работаете с субподрядчиками? (да/нет)", reply_markup=nav_keyboard())

@dp.message(StrategyStates.has_subcontractors)
async def strategy_subcontractors(message: types.Message, state: FSMContext):
    await state.update_data(has_subcontractors=message.text)
    await state.set_state(StrategyStates.urgent_tasks)
    await message.answer("Есть срочные вопросы по СРО, налогам, охране труда?", reply_markup=nav_keyboard())

@dp.message(StrategyStates.urgent_tasks)
async def strategy_urgent(message: types.Message, state: FSMContext):
    await state.update_data(urgent_tasks=message.text)
    await state.set_state(StrategyStates.need_sales)
    await message.answer("Нужна система продаж и мотивации? (да/нет)", reply_markup=nav_keyboard())

@dp.message(StrategyStates.need_sales)
async def strategy_sales(message: types.Message, state: FSMContext):
    await state.update_data(need_sales=message.text)
    data = await state.get_data()
    await finalize_order(message, state, "Стратегия строительства", {
        "Компания": data.get("has_company", "—"),
        "Субподрядчики": data.get("has_subcontractors", "—"),
        "Срочные задачи": data.get("urgent_tasks", "—"),
        "Система продаж": data.get("need_sales", "—")
    }, price_override=6800)

# ===================== БИЗНЕС-ПЛАН (КОННЫЙ СПОРТ) =====================
@dp.message(BPSportsStates.infrastructure)
async def bp_infrastructure(message: types.Message, state: FSMContext):
    await state.update_data(infrastructure=message.text)
    await state.set_state(BPSportsStates.scale)
    await message.answer("Какой масштаб мероприятий? (локальные, региональные, международные)", reply_markup=nav_keyboard())

@dp.message(BPSportsStates.scale)
async def bp_scale(message: types.Message, state: FSMContext):
    await state.update_data(scale=message.text)
    await state.set_state(BPSportsStates.data_available)
    await message.answer("Есть ли данные по доходам (взносы, билеты) или всё нужно прогнозировать?", reply_markup=nav_keyboard())

@dp.message(BPSportsStates.data_available)
async def bp_data(message: types.Message, state: FSMContext):
    await state.update_data(data_available=message.text)
    data = await state.get_data()
    await finalize_order(message, state, "Бизнес-план конный спорт", {
        "Инфраструктура": data.get("infrastructure", "—"),
        "Масштаб": data.get("scale", "—"),
        "Данные": data.get("data_available", "—")
    }, price_override=6500)

# ===================== ЮРИДИЧЕСКАЯ ДОРАБОТКА ДОГОВОРОВ =====================
@dp.message(LegalDocStates.contract_types)
async def legal_contract_types(message: types.Message, state: FSMContext):
    await state.update_data(contract_types=message.text)
    await state.set_state(LegalDocStates.has_projects)
    await message.answer("У вас есть готовые проекты договоров? (да/нет)", reply_markup=nav_keyboard())

@dp.message(LegalDocStates.has_projects)
async def legal_has_projects(message: types.Message, state: FSMContext):
    await state.update_data(has_projects=message.text)
    await state.set_state(LegalDocStates.deadline)
    await message.answer("Какой срок выполнения?", reply_markup=nav_keyboard())

@dp.message(LegalDocStates.deadline)
async def legal_deadline(message: types.Message, state: FSMContext):
    await state.update_data(deadline=message.text)
    await state.set_state(LegalDocStates.registry)
    await message.answer("Требуется адаптация под Реестр ПО? (да/нет)", reply_markup=nav_keyboard())

@dp.message(LegalDocStates.registry)
async def legal_registry(message: types.Message, state: FSMContext):
    await state.update_data(registry=message.text)
    await state.set_state(LegalDocStates.requirements)
    await message.answer("Есть особые требования к актам передачи РИД?", reply_markup=nav_keyboard())

@dp.message(LegalDocStates.requirements)
async def legal_requirements(message: types.Message, state: FSMContext):
    await state.update_data(requirements=message.text)
    data = await state.get_data()
    await finalize_order(message, state, "Юридическая доработка договоров", {
        "Типы договоров": data.get("contract_types", "—"),
        "Готовые проекты": data.get("has_projects", "—"),
        "Срок": data.get("deadline", "—"),
        "Реестр ПО": data.get("registry", "—"),
        "Требования": data.get("requirements", "—")
    }, price_override=6500)

# ===================== ЗАПУСК БОТА (webhook) =====================
async def main():
    await init_db()
    # await dp.start_polling(bot)   # отключено для webhook
    print("✅ Бот запущен в режиме webhook, polling отключён")

if __name__ == "__main__":
    asyncio.run(main())
