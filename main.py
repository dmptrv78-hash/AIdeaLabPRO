# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 6.2 – стабильная (без save_user_state в ТЗ)
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
import botocore
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

# ===================== ЮРИДИЧЕСКИЕ ТЕКСТЫ =====================
PRIVACY_POLICY_TEXT = """
ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ

1. ОБЩИЕ ПОЛОЖЕНИЯ
1.1. Настоящая Политика конфиденциальности (далее – Политика) действует в отношении всей информации, которую ИП Петров Дмитрий Евгеньевич (ОГРНИП 325665800177001, ИНН 591903202378, далее – Оператор) может получить о пользователе (далее – Пользователь) при использовании Telegram-бота @AIdeaLabPRO_bot (далее – Бот).
1.2. Использование Бота означает безоговорочное согласие Пользователя с настоящей Политикой и указанными в ней условиями обработки его персональных данных. В случае несогласия с этими условиями Пользователь должен воздержаться от использования Бота.
1.3. Настоящая Политика разработана в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных данных».
"""
# Полный текст политики и оферты — вы должны вставить свои полные тексты.

OFFER_TEXT = """
ПУБЛИЧНАЯ ОФЕРТА
на оказание услуг по разработке документов

г. Москва                                            18 июня 2026 г.

ИП Петров Дмитрий Евгеньевич (ОГРНИП 325665800177001, ИНН 591903202378), действующий на основании законодательства РФ, публикует настоящую Оферту о заключении договора на оказание услуг по разработке документов (далее – Договор) с любым лицом, принявшим условия настоящей Оферты (далее – Заказчик).

1. ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ
1.1. Исполнитель – ИП Петров Дмитрий Евгеньевич.
1.2. Заказчик – физическое или юридическое лицо, принявшее условия настоящей Оферты.
1.3. Услуги – разработка технического задания (ТЗ), технико-экономического обоснования (ТЭО), финансовой модели, бизнес-плана, полного пакета документов, а также проверка и доработка документов и консультации.
1.4. Бот – Telegram-бот @AIdeaLabPRO_bot, через который осуществляется взаимодействие.
1.5. Акцепт – полное и безоговорочное принятие условий Оферты путём оплаты услуг или направления заявки через Бот.

2. ПРЕДМЕТ ДОГОВОРА
2.1. Исполнитель обязуется оказать Заказчику услуги, перечень и стоимость которых определяются в соответствии с тарифами, опубликованными в Боте, а Заказчик обязуется оплатить их.
2.2. Услуги считаются оказанными надлежащим образом после передачи Заказчику готового документа в электронном виде через Бот или по электронной почте.

3. ПОРЯДОК ЗАКЛЮЧЕНИЯ ДОГОВОРА (АКЦЕПТ)
3.1. Заказчик выражает согласие с условиями Оферты путём: отправки заявки через Бот и её оплаты; или иного действия, свидетельствующего о намерении воспользоваться услугами.
3.2. Акцепт Оферты создаёт юридически обязывающий договор между Исполнителем и Заказчиком (ст. 438 ГК РФ).
3.3. Акцепт признаётся полным, если Заказчик выполнил все условия, необходимые для получения услуги.

4. СТОИМОСТЬ УСЛУГ И ПОРЯДОК ОПЛАТЫ
4.1. Стоимость услуг определяется автоматически Ботом на основе выбранной услуги, объёма, срочности и других параметров, и указывается в финальном сообщении перед оплатой.
4.2. Окончательная цена фиксируется в счёте, выставленном через ЮKassa.
4.3. Оплата производится в российских рублях безналичным способом через ЮKassa (банковские карты, СБП, ЮMoney).
4.4. Оплата считается выполненной при поступлении денежных средств на расчётный счёт Исполнителя.

5. ПРАВА И ОБЯЗАННОСТИ СТОРОН
5.1. Исполнитель обязуется: оказать услуги в сроки, указанные в заявке; обеспечить качество документов в соответствии с общепринятыми стандартами; сохранять конфиденциальность информации, полученной от Заказчика.
5.2. Заказчик обязуется: предоставить достоверные данные, необходимые для оказания услуг; оплатить услуги в установленном порядке; своевременно сообщать об изменениях контактных данных.

6. ПОРЯДОК ВОЗВРАТА ДЕНЕЖНЫХ СРЕДСТВ
6.1. Возврат денежных средств возможен только до момента начала оказания услуг (статус заявки «Оплачено, не начато»). В этом случае возвращается полная сумма оплаты.
6.2. После начала работ (статус «В работе») возврат не производится, но Исполнитель гарантирует доработку документа до полного соответствия заявке в рамках согласованного ТЗ.
6.3. Для оформления возврата Заказчик направляет письменное заявление на адрес support@aidealab.pro.
6.4. Возврат осуществляется в течение 10 рабочих дней с момента получения заявления.

7. ОТВЕТСТВЕННОСТЬ СТОРОН
7.1. Исполнитель несёт ответственность за ненадлежащее оказание услуг в соответствии с законодательством РФ.
7.2. Заказчик несёт ответственность за достоверность предоставленных данных.
7.3. Исполнитель не несёт ответственности за действия Telegram и третьих лиц.

8. ПОРЯДОК РАЗРЕШЕНИЯ СПОРОВ
8.1. Споры решаются путём переговоров. При недостижении согласия – в судебном порядке по месту нахождения Исполнителя.

9. СРОК ДЕЙСТВИЯ ОФЕРТЫ
9.1. Настоящая Оферта вступает в силу с момента её опубликования в Боте и действует до её отзыва Исполнителем.
9.2. Исполнитель вправе изменять условия Оферты в одностороннем порядке с обязательным уведомлением Заказчиков через Бот.

10. РЕКВИЗИТЫ ИСПОЛНИТЕЛЯ
Реквизиты предоставляются по запросу. Для получения реквизитов обратитесь к менеджеру.
"""

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
    try:
        if data is None:
            data = {}
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
    except Exception as e:
        print(f"❌ Ошибка сохранения состояния: {e}")

async def get_user_state(user_id):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
            user_state = result.scalar_one_or_none()
            if user_state:
                return user_state.state, json.loads(user_state.data)
            return None, None
    except Exception as e:
        print(f"❌ Ошибка получения состояния: {e}")
        return None, None

async def clear_user_state(user_id):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserState).where(UserState.user_telegram_id == user_id))
            user_state = result.scalar_one_or_none()
            if user_state:
                await session.delete(user_state)
                await session.commit()
    except Exception as e:
        print(f"❌ Ошибка удаления состояния: {e}")

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
        access_key = os.getenv('YANDEX_ACCESS_KEY_ID')
        secret_key = os.getenv('YANDEX_SECRET_ACCESS_KEY')
        if not access_key or not secret_key:
            print("❌ Не заданы ключи Yandex Object Storage")
            return None
        s3 = boto3.client(
            's3',
            endpoint_url='https://storage.yandexcloud.net',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        bucket = os.getenv('YANDEX_BUCKET_NAME', 'aidealab-files')
        s3.upload_fileobj(
            file_data,
            bucket,
            file_name,
            ExtraArgs={'ACL': 'public-read'}
        )
        return f"https://{bucket}.storage.yandexcloud.net/{file_name}"
    except botocore.exceptions.NoCredentialsError:
        print("❌ Нет учетных данных для Yandex Cloud")
        return None
    except Exception as e:
        print(f"❌ Ошибка загрузки в Yandex Cloud: {e}")
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
        return f"❌ Ошибка генерации: {e}"

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

# ===================== ОПЛАТА =====================
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
    name, essence, audience, features, competitors, tech_limits, deadline, budget, files = [State() for _ in range(9)]

class TEOStates(StatesGroup):
    goal, resources, risks, norms, effect, data, horizon, files = [State() for _ in range(8)]

class FMStates(StatesGroup):
    income, costs, investment, breakeven, metrics, data, horizon = [State() for _ in range(7)]

class BPStates(StatesGroup):
    summary, product, competitors, marketing, team, sales, risks, capital, finance_file, files = [State() for _ in range(10)]

class ConsultStates(StatesGroup):
    description, stage, goal = [State() for _ in range(3)]

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
    try:
        data = await state.get_data()
        user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        price = price_override if price_override is not None else calculate_price(service_name, data)
        order_id = await save_order(user.telegram_id, service_name, json.dumps(data, ensure_ascii=False), price)
        add_lead_to_gs({"name": data.get("name", ""), "phone": data.get("phone", ""), "service": service_name, **data})
        
        if data.get("file_url"):
            await save_file_to_db(order_id, data.get("file_name", "unknown"), data["file_url"])
        
        summary = f"📋 {service_name}\n\n"
        for key, label in fields.items():
            summary += f"{label}: {data.get(key, '—')}\n"
        summary += f"\n💰 Стоимость: {price} руб."
        
        # Отправка email (если настроен)
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
    except Exception as e:
        print(f"❌ Ошибка в finalize_order: {e}")
        await message.answer("Произошла ошибка при создании заявки. Пожалуйста, попробуйте позже.")

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
    if not message.text:
        await message.answer("Пожалуйста, введите ваш email или нажмите 'Пропустить'.")
        return
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
    if not message.text:
        await message.answer("Пожалуйста, напишите текст сообщения или нажмите 'Отмена'.")
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

# ===================== СЦЕНАРИЙ ТЗ (БЕЗ save_user_state) =====================
@dp.message(lambda msg: msg.text == "📋 Техническое задание")
async def start_tz(message: types.Message, state: FSMContext):
    await state.set_state(TZStates.name)
    await message.answer("Начнём с названия. Как назовём ваш проект?", reply_markup=nav_keyboard())

@dp.message(TZStates.name)
async def tz_name(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 1: {message.text}")
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введите название.")
        return
    await state.update_data(name=message.text)
    await state.set_state(TZStates.essence)
    await message.answer("Опишите свою идею простыми словами: что вы хотите создать и кому это поможет?", reply_markup=nav_keyboard())

@dp.message(TZStates.essence)
async def tz_essence(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 2: {message.text[:50]}...")
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите суть.")
        return
    await state.update_data(essence=message.text)
    await state.set_state(TZStates.audience)
    await message.answer("Кто ваши клиенты или пользователи? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.audience)
async def tz_audience(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 3: {message.text[:50]}...")
    if "пропустить" in message.text.lower():
        await state.update_data(audience="")
    else:
        await state.update_data(audience=message.text)
    await state.set_state(TZStates.features)
    await message.answer("Какие главные возможности должно иметь ваше решение? Напишите список через запятую.", reply_markup=nav_keyboard())

@dp.message(TZStates.features)
async def tz_features(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 4: {message.text[:50]}...")
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, перечислите функции.")
        return
    await state.update_data(features=message.text)
    await state.set_state(TZStates.competitors)
    await message.answer("Есть ли у вас конкуренты? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.competitors)
async def tz_competitors(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 5: {message.text[:50]}...")
    if "пропустить" in message.text.lower():
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=message.text)
    await state.set_state(TZStates.tech_limits)
    await message.answer("Есть ли технические рамки? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.tech_limits)
async def tz_tech_limits(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 6: {message.text[:50]}...")
    if "пропустить" in message.text.lower():
        await state.update_data(tech_limits="")
    else:
        await state.update_data(tech_limits=message.text)
    await state.set_state(TZStates.deadline)
    await message.answer("Когда вы хотите получить готовый результат? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.deadline)
async def tz_deadline(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 7: {message.text[:50]}...")
    if "пропустить" in message.text.lower():
        await state.update_data(deadline="")
    else:
        await state.update_data(deadline=message.text)
    await state.set_state(TZStates.budget)
    await message.answer("Есть ли у вас бюджет на этот проект? Если да, укажите сумму. Если нет, напишите 'нет' или выберите 'Пропустить'.", reply_markup=nav_keyboard())

@dp.message(TZStates.budget)
async def tz_budget(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 8: {message.text[:50]}...")
    text = message.text.lower().strip()
    if "пропустить" in text:
        await state.update_data(budget="")
        await state.set_state(TZStates.files)
        await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())
        return
    if text in ["нет", "нисколько", "0", "без бюджета", "не готов", "не знаю", "нет бюджета"]:
        await state.update_data(budget="0 (не указан)")
        await state.set_state(TZStates.files)
        await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())
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

@dp.message(TZStates.files)
async def tz_files(message: types.Message, state: FSMContext):
    print(f"🔄 Шаг 9 (финал): получен файл или пропуск")
    if message.document:
        file_id = message.document.file_id
        file_name = f"{datetime.datetime.now().timestamp()}_{message.document.file_name}"
        file_data = await bot.download_file(file_id, destination=None)
        file_url = upload_to_yandex(file_data, file_name)
        if file_url:
            await state.update_data(file_url=file_url)
            await state.update_data(file_name=file_name)
        else:
            await message.answer("Не удалось сохранить файл. Вы можете пропустить этот шаг.")
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

# ===================== ЗАПУСК БОТА =====================
async def main():
    await init_db()
    print("✅ Бот запущен в режиме polling")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
