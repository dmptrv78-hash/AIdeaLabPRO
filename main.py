# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 7.0 – СТАБИЛЬНАЯ (polling с защитой от зависаний)
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
import logging
import signal
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiohttp import ClientError, ClientTimeout
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

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
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "TEST")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1636715304").split(',')))
MANAGER_EMAIL = "dmptrv78@gmail.com"

# Настройки для стабильности
POLLING_TIMEOUT = 60  # секунд
POLLING_INTERVAL = 0.5  # секунд между запросами
MAX_RETRIES = 5
BOT_SESSION_TIMEOUT = 120  # секунд

# ===================== ИНИЦИАЛИЗАЦИЯ С ХРАНЕНИЕМ СОСТОЯНИЯ =====================
storage = MemoryStorage()

# Создаем бота с увеличенными таймаутами
bot = Bot(
    token=BOT_TOKEN,
    timeout=BOT_SESSION_TIMEOUT,
    parse_mode="HTML",
)

dp = Dispatcher(storage=storage)

# ===================== БАЗА ДАННЫХ С ПУЛОМ СОЕДИНЕНИЙ =====================
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, select, func, text, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError, OperationalError

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}?check_same_thread=False"

# Настройки пула соединений
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,   # Пересоздание соединения через час
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ===================== МОДЕЛИ БАЗЫ ДАННЫХ =====================
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
    
    __table_args__ = (
        Index('idx_user_telegram_id', 'telegram_id'),
        Index('idx_user_consent', 'consent_given'),
        Index('idx_user_last_activity', 'last_activity'),
    )

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
    
    __table_args__ = (
        Index('idx_order_user', 'user_telegram_id'),
        Index('idx_order_status', 'status'),
        Index('idx_order_created', 'created_at'),
    )

class OrderFile(Base):
    __tablename__ = "order_files"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, nullable=False)
    file_name = Column(String, nullable=False)
    file_url = Column(String, nullable=True)
    file_type = Column(String, default="user_upload")
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

class UserState(Base):
    __tablename__ = "user_states"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(Integer, unique=True, nullable=False)
    state = Column(String, nullable=True)
    data = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# ===================== ДЕКОРАТОР ДЛЯ ПОВТОРНЫХ ПОПЫТОК =====================
def retry_on_db_error(func):
    """Декоратор для повторных попыток при ошибках БД"""
    async def wrapper(*args, **kwargs):
        retries = 3
        for attempt in range(retries):
            try:
                return await func(*args, **kwargs)
            except (OperationalError, SQLAlchemyError) as e:
                if attempt == retries - 1:
                    logger.error(f"❌ Ошибка БД после {retries} попыток: {e}")
                    raise
                logger.warning(f"⚠️ Ошибка БД, попытка {attempt + 1}/{retries}: {e}")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка в {func.__name__}: {e}")
                raise
    return wrapper

# ===================== ЮРИДИЧЕСКИЕ ТЕКСТЫ =====================
PRIVACY_POLICY_TEXT = """
ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ

1. ОБЩИЕ ПОЛОЖЕНИЯ
1.1. Настоящая Политика конфиденциальности (далее – Политика) действует в отношении всей информации, которую ИП Петров Дмитрий Евгеньевич (ОГРНИП 325665800177001, ИНН 591903202378, далее – Оператор) может получить о пользователе (далее – Пользователь) при использовании Telegram-бота @AIdeaLabPRO_bot (далее – Бот).
1.2. Использование Бота означает безоговорочное согласие Пользователя с настоящей Политикой и указанными в ней условиями обработки его персональных данных. В случае несогласия с этими условиями Пользователь должен воздержаться от использования Бота.
1.3. Настоящая Политика разработана в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных данных».
2. ПЕРСОНАЛЬНЫЕ ДАННЫЕ, КОТОРЫЕ МЫ СОБИРАЕМ
2.1. Оператор собирает и обрабатывает следующие персональные данные Пользователя: имя, указанное в профиле Telegram; Telegram ID; адрес электронной почты (если Пользователь предоставил его); номер телефона (если Пользователь предоставил его); данные, предоставленные в процессе заполнения заявок и опросов.
2.2. Бот также автоматически собирает техническую информацию: дату и время взаимодействия, идентификаторы сообщений, тип устройства и браузера (через Telegram).
3. ЦЕЛИ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ
3.1. Оператор обрабатывает персональные данные Пользователя для: предоставления услуг по разработке технических заданий, бизнес-планов, финансовых моделей и других документов; связи с Пользователем по его заявкам и вопросам; направления уведомлений о статусе заявок; улучшения качества обслуживания и аналитики.
4. ПРАВОВЫЕ ОСНОВАНИЯ ОБРАБОТКИ
4.1. Обработка персональных данных осуществляется на основании согласия Пользователя, выраженного путём нажатия кнопки «Согласен» в Боте.
5. ПРАВА ПОЛЬЗОВАТЕЛЯ
5.1. Пользователь имеет право: отозвать своё согласие на обработку персональных данных в любой момент, направив уведомление Оператору по адресу support@aidealab.pro или через Бота; требовать удаления своих персональных данных, если они обрабатываются с нарушением закона; получать информацию о своих персональных данных, находящихся в распоряжении Оператора.
6. СРОКИ ХРАНЕНИЯ И ПОРЯДОК УНИЧТОЖЕНИЯ
6.1. Персональные данные хранятся не дольше, чем это требуется для целей их обработки, но в любом случае не более 3 лет с момента последнего взаимодействия Пользователя с Ботом.
6.2. Уничтожение данных производится по запросу Пользователя или по истечении срока хранения.
7. МЕРЫ ЗАЩИТЫ
7.1. Оператор принимает необходимые организационные и технические меры для защиты персональных данных от неправомерного доступа, уничтожения, изменения, блокирования, копирования, распространения.
8. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ
8.1. Оператор вправе вносить изменения в настоящую Политику. Новая редакция вступает в силу с момента её публикации в Боте.
8.2. Все вопросы по исполнению Политики направлять по адресу: support@aidealab.pro.
"""

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

# ===================== ФУНКЦИИ РАБОТЫ С БД =====================
@retry_on_db_error
async def init_db():
    """Инициализация базы данных с повторными попытками"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise

@retry_on_db_error
async def get_or_create_user(telegram_id, username=None, full_name=None):
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    full_name=full_name,
                    last_activity=datetime.datetime.utcnow()
                )
                session.add(user)
                await session.commit()
                logger.info(f"✅ Создан новый пользователь: {telegram_id}")
            else:
                # Обновляем активность
                user.last_activity = datetime.datetime.utcnow()
                await session.commit()
            return user
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Ошибка в get_or_create_user: {e}")
            raise

@retry_on_db_error
async def save_user_state(user_id, state, data):
    try:
        if data is None:
            data = {}
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserState).where(UserState.user_telegram_id == user_id)
            )
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
        logger.error(f"❌ Ошибка сохранения состояния: {e}")
        raise

@retry_on_db_error
async def get_user_state(user_id):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserState).where(UserState.user_telegram_id == user_id)
            )
            user_state = result.scalar_one_or_none()
            if user_state:
                try:
                    data = json.loads(user_state.data) if user_state.data else {}
                except:
                    data = {}
                return user_state.state, data
            return None, None
    except Exception as e:
        logger.error(f"❌ Ошибка получения состояния: {e}")
        return None, None

@retry_on_db_error
async def clear_user_state(user_id):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserState).where(UserState.user_telegram_id == user_id)
            )
            user_state = result.scalar_one_or_none()
            if user_state:
                await session.delete(user_state)
                await session.commit()
    except Exception as e:
        logger.error(f"❌ Ошибка удаления состояния: {e}")
        raise

@retry_on_db_error
async def save_order(user_telegram_id, service, data_json, price=0):
    async with AsyncSessionLocal() as session:
        try:
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
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Ошибка сохранения заказа: {e}")
            raise

@retry_on_db_error
async def update_order_status(order_id, status, notify_user=True):
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Order).where(Order.id == order_id)
            )
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
                        logger.error(f"Не удалось уведомить клиента: {e}")
                return True
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Ошибка обновления статуса: {e}")
            raise
    return False

# ===================== YANDEX OBJECT STORAGE =====================
def upload_to_yandex(file_data, file_name):
    try:
        access_key = os.getenv('YANDEX_ACCESS_KEY_ID')
        secret_key = os.getenv('YANDEX_SECRET_ACCESS_KEY')
        if not access_key or not secret_key:
            logger.error("❌ Не заданы ключи Yandex Object Storage")
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
        logger.error("❌ Нет учетных данных для Yandex Cloud")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки в Yandex Cloud: {e}")
        return None

@retry_on_db_error
async def save_file_to_db(order_id, file_name, file_url, file_type="user_upload"):
    async with AsyncSessionLocal() as session:
        try:
            order_file = OrderFile(
                order_id=order_id,
                file_name=file_name,
                file_url=file_url,
                file_type=file_type
            )
            session.add(order_file)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Ошибка сохранения файла: {e}")
            raise

# ===================== ИНТЕГРАЦИИ =====================
try:
    from openai import OpenAI
    deepseek_client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url="https://api.deepseek.com",
        timeout=30.0,
        max_retries=3
    )
except Exception as e:
    deepseek_client = None
    logger.error(f"❌ Ошибка инициализации DeepSeek: {e}")

def generate_document(prompt, user_data):
    if not deepseek_client:
        return "⚠️ DeepSeek API не настроен. Используйте менеджера."
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": str(user_data)}
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            timeout=30.0
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ Ошибка генерации: {e}")
        return f"❌ Ошибка генерации: {str(e)[:100]}"

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    gs_client = gspread.authorize(creds)
    sheet = gs_client.open("Заявки").sheet1
    logger.info("✅ Google Sheets подключен")
except Exception as e:
    sheet = None
    logger.warning(f"⚠️ Google Sheets не настроен: {e}")

def add_lead_to_gs(data):
    if sheet:
        try:
            row = [data.get("name", ""), data.get("phone", ""), data.get("service", ""), json.dumps(data, ensure_ascii=False)]
            sheet.append_row(row)
        except Exception as e:
            logger.error(f"❌ Ошибка добавления в Google Sheets: {e}")

async def notify_admins(text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")

# ===================== EMAIL =====================
def send_email(to_email, subject, body):
    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", 465))
        smtp_login = os.getenv("SMTP_LOGIN")
        smtp_password = os.getenv("SMTP_PASSWORD")
        if not all([smtp_server, smtp_login, smtp_password]):
            logger.warning("SMTP не настроен")
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
        logger.error(f"❌ Ошибка отправки email: {e}")
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

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
async def safe_send_message(user_id: int, text: str, **kwargs) -> bool:
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control, ждем {e.retry_after} сек")
        await asyncio.sleep(e.retry_after)
        return await safe_send_message(user_id, text, **kwargs)
    except (TelegramNetworkError, ClientError) as e:
        logger.error(f"Сетевая ошибка при отправке: {e}")
        await asyncio.sleep(1)
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        return False

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
            value = data.get(key, '—')
            if key == "file_url" and value:
                value = "📎 Файл загружен"
            summary += f"{label}: {value}\n"
        summary += f"\n💰 Стоимость: {price} руб."
        
        # Отправка email
        subject = f"🔔 Новая заявка #{order_id}"
        body = f"Услуга: {service_name}\nКлиент: {user.full_name or user.username}\nТелефон: {user.phone or 'не указан'}\nEmail: {user.email or 'не указан'}\n\nДанные заявки:\n{summary}\n\nTelegram: @{message.from_user.username}\nID: {message.from_user.id}"
        send_email(MANAGER_EMAIL, subject, body)
        
        # Уведомление администраторам
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
            await safe_send_message(admin_id, admin_message)
        
        await safe_send_message(
            message.from_user.id,
            f"{summary}\n\n💳 Оплата временно отключена для тестирования. Заявка принята!"
        )
        
        await state.clear()
        await clear_user_state(message.from_user.id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в finalize_order: {e}", exc_info=True)
        await safe_send_message(
            message.from_user.id,
            "Произошла ошибка при создании заявки. Пожалуйста, попробуйте позже."
        )

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
        await safe_send_message(message.from_user.id, "У вас есть незавершённая заявка. Хотите продолжить?", reply_markup=kb)
        return
    
    if not user.consent_given:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Политика конфиденциальности", callback_data="show_privacy")],
            [InlineKeyboardButton(text="📄 Оферта", callback_data="show_offer")],
            [InlineKeyboardButton(text="✅ Согласен", callback_data="accept_consent")],
            [InlineKeyboardButton(text="❌ Не согласен", callback_data="decline_consent")]
        ])
        await safe_send_message(
            message.from_user.id,
            "Для продолжения работы с ботом необходимо ваше согласие на обработку персональных данных.\n"
            "Мы собираем только имя, телефон и email для связи по вашему заказу.\n\n"
            "Ознакомьтесь с документами, нажав кнопки ниже, и, если вы согласны, нажмите «Согласен».",
            reply_markup=kb
        )
        await state.set_state(CommonStates.ask_consent)
        return
    
    if user.email is None:
        await state.set_state(CommonStates.ask_email)
        await safe_send_message(
            message.from_user.id,
            "Пожалуйста, укажите ваш email для связи (на него придёт подтверждение заявки).\n"
            "Если не хотите указывать, нажмите 'Пропустить' — мы свяжемся с вами через Telegram.",
            reply_markup=nav_keyboard()
        )
        return
    
    await safe_send_message(
        message.from_user.id,
        "Добро пожаловать в AIdea Lab PRO!\n\nВыберите услугу:",
        reply_markup=main_menu_keyboard()
    )

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
        await safe_send_message(message.from_user.id, "Пожалуйста, введите ваш email или нажмите 'Пропустить'.")
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
        await safe_send_message(
            message.from_user.id,
            "✅ Email пропущен. Для связи мы будем использовать ваш Telegram. Теперь выберите услугу:",
            reply_markup=main_menu_keyboard()
        )
        return
    if "@" not in text or "." not in text:
        await safe_send_message(
            message.from_user.id,
            "Введите корректный email (например, name@domain.com) или нажмите 'Пропустить'.",
            reply_markup=nav_keyboard()
        )
        return
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        if user:
            user.email = text
            await session.commit()
    await state.clear()
    await safe_send_message(
        message.from_user.id,
        f"✅ Email {text} сохранён! Теперь выберите услугу:",
        reply_markup=main_menu_keyboard()
    )

@dp.message(lambda msg: msg.text == "🏠 Главное меню")
async def go_home(message: types.Message, state: FSMContext):
    await state.clear()
    await clear_user_state(message.from_user.id)
    await safe_send_message(message.from_user.id, "Главное меню", reply_markup=main_menu_keyboard())

@dp.message(lambda msg: msg.text == "🔙 Назад")
async def go_back(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if not current:
        await safe_send_message(message.from_user.id, "Вы не в процессе заполнения.", reply_markup=main_menu_keyboard())
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
        await safe_send_message(message.from_user.id, "Вернулись назад.", reply_markup=nav_keyboard())
    else:
        await safe_send_message(message.from_user.id, "Это первый шаг.", reply_markup=nav_keyboard())

# ===================== ОБРАТНАЯ СВЯЗЬ =====================
@dp.message(lambda msg: msg.text == "📩 Написать разработчику")
async def start_feedback(message: types.Message, state: FSMContext):
    await state.set_state(FeedbackStates.waiting_for_message)
    await safe_send_message(
        message.from_user.id,
        "📝 Напишите ваше сообщение разработчику (до 1000 символов).\n"
        "Мы постараемся ответить вам как можно быстрее.\n\n"
        "Для отмены нажмите кнопку «Отмена».",
        reply_markup=feedback_keyboard()
    )

@dp.message(FeedbackStates.waiting_for_message)
async def process_feedback(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await safe_send_message(message.from_user.id, "✅ Отправка отменена. Возвращаемся в меню.", reply_markup=main_menu_keyboard())
        return
    if not message.text:
        await safe_send_message(message.from_user.id, "Пожалуйста, напишите текст сообщения или нажмите 'Отмена'.")
        return
    text = message.text.strip()
    if len(text) > 1000:
        await safe_send_message(
            message.from_user.id,
            f"❌ Сообщение слишком длинное ({len(text)} символов). Максимум 1000 символов. Пожалуйста, сократите."
        )
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
        await safe_send_message(admin_id, report)
    await state.clear()
    await safe_send_message(
        message.from_user.id,
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
    await safe_send_message(
        message.from_user.id,
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
        await safe_send_message(message.from_user.id, "Использование: /broadcast текст сообщения")
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
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение {user_id}: {e}")
    await safe_send_message(
        message.from_user.id,
        f"✅ Сообщение отправлено {sent} пользователям из {len(users)}."
    )

# ===================== СЦЕНАРИЙ ТЗ =====================
@dp.message(lambda msg: msg.text == "📋 Техническое задание")
async def start_tz(message: types.Message, state: FSMContext):
    await state.set_state(TZStates.name)
    await safe_send_message(
        message.from_user.id,
        "Начнём с названия. Как назовём ваш проект?",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.name)
async def tz_name(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await safe_send_message(message.from_user.id, "Пожалуйста, введите название.")
        return
    await state.update_data(name=message.text)
    await state.set_state(TZStates.essence)
    await safe_send_message(
        message.from_user.id,
        "Опишите свою идею простыми словами: что вы хотите создать и кому это поможет?",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.essence)
async def tz_essence(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await safe_send_message(message.from_user.id, "Пожалуйста, опишите суть.")
        return
    await state.update_data(essence=message.text)
    await state.set_state(TZStates.audience)
    await safe_send_message(
        message.from_user.id,
        "Кто ваши клиенты или пользователи? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.audience)
async def tz_audience(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(audience="")
    else:
        await state.update_data(audience=message.text)
    await state.set_state(TZStates.features)
    await safe_send_message(
        message.from_user.id,
        "Какие главные возможности должно иметь ваше решение? Напишите список через запятую.",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.features)
async def tz_features(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await safe_send_message(message.from_user.id, "Пожалуйста, перечислите функции.")
        return
    await state.update_data(features=message.text)
    await state.set_state(TZStates.competitors)
    await safe_send_message(
        message.from_user.id,
        "Есть ли у вас конкуренты? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.competitors)
async def tz_competitors(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=message.text)
    await state.set_state(TZStates.tech_limits)
    await safe_send_message(
        message.from_user.id,
        "Есть ли технические рамки? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.tech_limits)
async def tz_tech_limits(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(tech_limits="")
    else:
        await state.update_data(tech_limits=message.text)
    await state.set_state(TZStates.deadline)
    await safe_send_message(
        message.from_user.id,
        "Когда вы хотите получить готовый результат? (можно пропустить)",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.deadline)
async def tz_deadline(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(deadline="")
    else:
        await state.update_data(deadline=message.text)
    await state.set_state(TZStates.budget)
    await safe_send_message(
        message.from_user.id,
        "Есть ли у вас бюджет на этот проект? Если да, укажите сумму. Если нет, напишите 'нет' или выберите 'Пропустить'.",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.budget)
async def tz_budget(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if "пропустить" in text:
        await state.update_data(budget="")
        await state.set_state(TZStates.files)
        await safe_send_message(
            message.from_user.id,
            "Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.",
            reply_markup=nav_keyboard()
        )
        return
    if text in ["нет", "нисколько", "0", "без бюджета", "не готов", "не знаю", "нет бюджета"]:
        await state.update_data(budget="0 (не указан)")
        await state.set_state(TZStates.files)
        await safe_send_message(
            message.from_user.id,
            "Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.",
            reply_markup=nav_keyboard()
        )
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
    await safe_send_message(
        message.from_user.id,
        "Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.",
        reply_markup=nav_keyboard()
    )

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
            await safe_send_message(message.from_user.id, "Не удалось сохранить файл. Вы можете пропустить этот шаг.")
            return
    elif "пропустить" in message.text.lower():
        await state.update_data(file_url=None)
        await state.update_data(file_name=None)
    else:
        await safe_send_message(
            message.from_user.id,
            "Пожалуйста, загрузите файл или нажмите 'Пропустить'.",
            reply_markup=nav_keyboard()
        )
        return

    data = await state.get_data()
    prompt = "Ты — эксперт по разработке ТЗ. На основе данных сгенерируй структурированное ТЗ в формате JSON."
    doc = generate_document(prompt, data)
    if doc and "⚠️" not in doc and "❌" not in doc:
        await safe_send_message(message.from_user.id, f"📄 Сгенерированный черновик ТЗ:\n\n{doc}")
        for admin_id in ADMIN_IDS:
            try:
                await safe_send_message(
                    admin_id,
                    f"📄 Черновик ТЗ от @{message.from_user.username} (ID: {message.from_user.id}):\n\n{doc}"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить черновик админу {admin_id}: {e}")
    else:
        await safe_send_message(message.from_user.id, "⚠️ Не удалось сгенерировать черновик. Пожалуйста, обратитесь к менеджеру.")

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

# ===================== МОНИТОРИНГ И ЗАЩИТА ОТ ЗАВИСАНИЙ =====================
async def health_check():
    """Периодическая проверка работоспособности"""
    while True:
        try:
            # Проверка соединения с Telegram
            me = await bot.get_me()
            logger.info(f"✅ Бот активен: @{me.username}")
            
            # Проверка БД
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            logger.info("✅ База данных доступна")
            
            await asyncio.sleep(60)  # Проверка каждую минуту
        except Exception as e:
            logger.error(f"❌ Ошибка health check: {e}")
            await asyncio.sleep(10)

async def restart_polling_on_error():
    """Перезапуск polling при ошибках"""
    retry_count = 0
    max_retries = 10
    
    while True:
        try:
            logger.info("🚀 Запуск polling с защитой от зависаний...")
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                polling_timeout=POLLING_TIMEOUT,
                relax=POLLING_INTERVAL,
                handle_signals=False
            )
            retry_count = 0  # Сброс счетчика при успешном запуске
        except (TelegramNetworkError, ClientError) as e:
            retry_count += 1
            logger.error(f"❌ Сетевая ошибка в polling (попытка {retry_count}): {e}")
            await asyncio.sleep(min(30, 5 * retry_count))
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ Критическая ошибка в polling (попытка {retry_count}): {e}", exc_info=True)
            await asyncio.sleep(10 * retry_count)
            
            if retry_count >= max_retries:
                logger.critical("❌ Превышено максимальное количество перезапусков")
                # Отправка уведомления админам
                for admin_id in ADMIN_IDS:
                    await safe_send_message(
                        admin_id,
                        f"🚨 Бот перезапускается после {retry_count} ошибок!\nОшибка: {str(e)[:200]}"
                    )
                retry_count = 0

# ===================== ОБРАБОТЧИКИ СИГНАЛОВ =====================
def signal_handler(signum, frame):
    """Обработка сигналов для корректного завершения"""
    logger.info(f"Получен сигнал {signum}, завершаем работу...")
    sys.exit(0)

# ===================== ЗАПУСК БОТА =====================
async def main():
    # Установка обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Инициализация БД
        await init_db()
        logger.info("✅ База данных инициализирована")
        
        # Запуск health check в фоновом режиме
        asyncio.create_task(health_check())
        logger.info("✅ Health check запущен")
        
        # Уведомление админов о запуске
        for admin_id in ADMIN_IDS:
            await safe_send_message(
                admin_id,
                f"🤖 Бот AIdea Lab PRO запущен!\nВремя: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        # Запуск polling с защитой от зависаний
        await restart_polling_on_error()
        
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка при запуске: {e}", exc_info=True)
        # Уведомление админов о критической ошибке
        for admin_id in ADMIN_IDS:
            await safe_send_message(
                admin_id,
                f"🚨 КРИТИЧЕСКАЯ ОШИБКА при запуске бота!\n{e}\n\nБот будет перезапущен через 30 секунд..."
            )
        await asyncio.sleep(30)
        raise

if __name__ == "__main__":
    # Добавляем поддержку перезапуска при ошибках
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен пользователем")
            break
        except Exception as e:
            logger.critical(f"❌ Бот упал с ошибкой: {e}", exc_info=True)
            logger.info("🔄 Перезапуск через 30 секунд...")
            time.sleep(30)
            continue
        break
