# ============================================================
# AIdea Lab PRO – Telegram бот для бизнес-документов
# Версия 5.3 – добавлен сценарий «Полный пакет» (34 шага)
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
from pathlib import Path

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

# ===================== ЮРИДИЧЕСКИЕ ТЕКСТЫ =====================
PRIVACY_POLICY_TEXT = """
ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ

1. ОБЩИЕ ПОЛОЖЕНИЯ
1.1. Настоящая Политика конфиденциальности (далее – Политика) действует в отношении всей информации, которую ИП Петров Дмитрий Евгеньевич (ОГРНИП 325665800177001, ИНН 591903202378, далее – Оператор) может получить о пользователе (далее – Пользователь) при использовании Telegram-бота @AIdeaLabPRO_bot (далее – Бот).
1.2. Использование Бота означает безоговорочное согласие Пользователя с настоящей Политикой и указанными в ней условиями обработки его персональных данных. В случае несогласия с этими условиями Пользователь должен воздержаться от использования Бота.
1.3. Настоящая Политика разработана в соответствии с Федеральным законом от 27.07.2006 № 152-ФЗ «О персональных данных».

2. ПЕРСОНАЛЬНЫЕ ДАННЫЕ, КОТОРЫЕ МЫ СОБИРАЕМ
2.1. Оператор собирает и обрабатывает следующие персональные данные Пользователя:
- Имя, указанное в профиле Telegram;
- Telegram ID;
- Адрес электронной почты (если Пользователь предоставил его);
- Номер телефона (если Пользователь предоставил его);
- Данные, предоставленные в процессе заполнения заявок и опросов (название проекта, описание, функциональные требования и т.п.).
2.2. Бот также автоматически собирает техническую информацию: дату и время взаимодействия, идентификаторы сообщений, тип устройства и браузера (через Telegram).

3. ЦЕЛИ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ
3.1. Оператор обрабатывает персональные данные Пользователя для:
- предоставления услуг по разработке технических заданий, бизнес-планов, финансовых моделей и других документов;
- связи с Пользователем по его заявкам и вопросам;
- направления уведомлений о статусе заявок;
- улучшения качества обслуживания и аналитики.

4. ПРАВОВЫЕ ОСНОВАНИЯ ОБРАБОТКИ
4.1. Обработка персональных данных осуществляется на основании согласия Пользователя, выраженного путём нажатия кнопки «Согласен» в Боте.

5. ПРАВА ПОЛЬЗОВАТЕЛЯ
5.1. Пользователь имеет право:
- отозвать своё согласие на обработку персональных данных в любой момент, направив уведомление Оператору по адресу support@aidealab.pro или через Бота;
- требовать удаления своих персональных данных, если они обрабатываются с нарушением закона;
- получать информацию о своих персональных данных, находящихся в распоряжении Оператора.

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
3.1. Заказчик выражает согласие с условиями Оферты путём:
- отправки заявки через Бот и её оплаты;
- или иного действия, свидетельствующего о намерении воспользоваться услугами.
3.2. Акцепт Оферты создаёт юридически обязывающий договор между Исполнителем и Заказчиком (ст. 438 ГК РФ).
3.3. Акцепт признаётся полным, если Заказчик выполнил все условия, необходимые для получения услуги.

4. СТОИМОСТЬ УСЛУГ И ПОРЯДОК ОПЛАТЫ
4.1. Стоимость услуг определяется автоматически Ботом на основе выбранной услуги, объёма, срочности и других параметров, и указывается в финальном сообщении перед оплатой.
4.2. Окончательная цена фиксируется в счёте, выставленном через ЮKassa.
4.3. Оплата производится в российских рублях безналичным способом через ЮKassa (банковские карты, СБП, ЮMoney).
4.4. Оплата считается выполненной при поступлении денежных средств на расчётный счёт Исполнителя.

5. ПРАВА И ОБЯЗАННОСТИ СТОРОН
5.1. Исполнитель обязуется:
- оказать услуги в сроки, указанные в заявке;
- обеспечить качество документов в соответствии с общепринятыми стандартами;
- сохранять конфиденциальность информации, полученной от Заказчика.
5.2. Заказчик обязуется:
- предоставить достоверные данные, необходимые для оказания услуг;
- оплатить услуги в установленном порядке;
- своевременно сообщать об изменениях контактных данных.

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
ИП Петров Дмитрий Евгеньевич
ИНН: 591903202378
ОГРНИП: 325665800177001
Расчётный счёт: 40802810123456789012
Банк: ПАО Сбербанк
БИК: 044525225
Кор. счёт: 30101810400000000225
Юридический адрес: 127000, г. Москва, ул. Примерная, д. 1, кв. 1
E-mail: support@aidealab.pro
"""

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8802501314:AAG0L8mrwSTNUqhrsHWIWGarw8QlZgtJXGQ")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "TEST")
# MANAGER_GROUP_ID – не используется, все уведомления на почту
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1636715304").split(',')))  # ваш ID, если нужно

# Целевой email для всех уведомлений
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

# ===================== БАЗА ДАННЫХ (абсолютный путь) =====================
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, select, text
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
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

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

# ===================== НОВЫЙ КЛАСС ДЛЯ ПОЛНОГО ПАКЕТА =====================
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
    
    summary = f"📋 {service_name}\n\n"
    for key, label in fields.items():
        summary += f"{label}: {data.get(key, '—')}\n"
    summary += f"\n💰 Стоимость: {price} руб."
    
    # Отправка email менеджеру
    subject = f"🔔 Новая заявка #{order_id}"
    body = f"Услуга: {service_name}\nКлиент: {user.full_name or user.username}\nТелефон: {user.phone or 'не указан'}\nEmail: {user.email or 'не указан'}\n\nДанные заявки:\n{summary}\n\nTelegram: @{message.from_user.username}\nID: {message.from_user.id}"
    send_email(MANAGER_EMAIL, subject, body)
    
    await message.answer(summary)
    await message.answer("💳 Оплата временно отключена для тестирования. Заявка принята!")
    await state.clear()

# ===================== ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ =====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
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
    user_id = message.from_user.id

    report = (
        f"📩 НОВОЕ СООБЩЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ\n\n"
        f"👤 Имя: {full_name}\n"
        f"🆔 ID: {user_id}\n"
        f"📝 Текст сообщения:\n{text}"
    )

    send_email(MANAGER_EMAIL, f"Сообщение от пользователя {full_name}", report)
    await notify_admins(f"📩 Новое сообщение от {full_name} (ID: {user_id}). Проверьте почту.")

    await state.clear()
    await message.answer(
        "✅ Ваше сообщение отправлено разработчикам. Мы свяжемся с вами в ближайшее время.",
        reply_markup=main_menu_keyboard()
    )

# ===================== ОСНОВНЫЕ СЦЕНАРИИ УСЛУГ (ТЗ, ТЭО, Финмодель, Бизнес-план, Консультация) =====================
# (Здесь вставляются существующие обработчики. Я их не копирую для краткости, но они должны быть.
#  В полном файле они уже есть. Мы добавляем только новый сценарий "Полный пакет".)

# ===================== СЦЕНАРИЙ «ПОЛНЫЙ ПАКЕТ» =====================
@dp.message(lambda msg: msg.text == "📦 Полный пакет")
async def start_full_package(message: types.Message, state: FSMContext):
    await state.set_state(FullPackageStates.step1)
    await message.answer("Начнём с названия. Как назовём ваш проект?", reply_markup=nav_keyboard())

# Шаг 1: Название
@dp.message(FullPackageStates.step1)
async def fp_step1(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введите название.")
        return
    await state.update_data(name=message.text)
    await state.set_state(FullPackageStates.step2)
    await message.answer("Опишите свою идею простыми словами: что вы хотите создать и кому это поможет?", reply_markup=nav_keyboard())

# Шаг 2: Суть
@dp.message(FullPackageStates.step2)
async def fp_step2(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите суть.")
        return
    await state.update_data(essence=message.text)
    await state.set_state(FullPackageStates.step3)
    await message.answer("Кто ваши клиенты или пользователи? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 3: Аудитория
@dp.message(FullPackageStates.step3)
async def fp_step3(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(audience="")
    else:
        await state.update_data(audience=message.text)
    await state.set_state(FullPackageStates.step4)
    await message.answer("Какие главные возможности должно иметь ваше решение? Напишите список через запятую.", reply_markup=nav_keyboard())

# Шаг 4: Функции
@dp.message(FullPackageStates.step4)
async def fp_step4(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, перечислите функции.")
        return
    await state.update_data(features=message.text)
    await state.set_state(FullPackageStates.step5)
    await message.answer("Есть ли у вас конкуренты? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 5: Конкуренты
@dp.message(FullPackageStates.step5)
async def fp_step5(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=message.text)
    await state.set_state(FullPackageStates.step6)
    await message.answer("Есть ли технические рамки? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 6: Технические ограничения
@dp.message(FullPackageStates.step6)
async def fp_step6(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(tech_limits="")
    else:
        await state.update_data(tech_limits=message.text)
    await state.set_state(FullPackageStates.step7)
    await message.answer("Когда вы хотите получить готовый результат? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 7: Сроки
@dp.message(FullPackageStates.step7)
async def fp_step7(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(deadline="")
    else:
        await state.update_data(deadline=message.text)
    await state.set_state(FullPackageStates.step8)
    await message.answer("Есть ли у вас бюджет на этот проект? Если да, укажите сумму. Если нет, напишите 'нет' или выберите 'Пропустить'.", reply_markup=nav_keyboard())

# Шаг 8: Бюджет
@dp.message(FullPackageStates.step8)
async def fp_step8(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if "пропустить" in text:
        await state.update_data(budget="")
        await state.set_state(FullPackageStates.step9)
        await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())
        return
    if text in ["нет", "нисколько", "0", "без бюджета", "не готов", "не знаю", "нет бюджета"]:
        await state.update_data(budget="0 (не указан)")
        await state.set_state(FullPackageStates.step9)
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
    await state.set_state(FullPackageStates.step9)
    await message.answer("Приложите дополнительные материалы (макеты, референсы). Пока можно только пропустить.", reply_markup=nav_keyboard())

# Шаг 9: Файлы ТЗ
@dp.message(FullPackageStates.step9)
async def fp_step9(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(files_tz=file_name)
    elif "пропустить" in message.text.lower():
        await state.update_data(files_tz="")
    else:
        await message.answer("Пожалуйста, загрузите файл или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return
    await state.set_state(FullPackageStates.step10)
    await message.answer("Какую главную задачу вы решаете с помощью этого проекта? (ТЭО)", reply_markup=nav_keyboard())

# Шаг 10: Главная задача (ТЭО)
@dp.message(FullPackageStates.step10)
async def fp_step10(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите цель.")
        return
    await state.update_data(goal=message.text)
    await state.set_state(FullPackageStates.step11)
    await message.answer("Какие ресурсы вам понадобятся? (люди, техника, программы)", reply_markup=nav_keyboard())

# Шаг 11: Ресурсы (ТЭО)
@dp.message(FullPackageStates.step11)
async def fp_step11(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, перечислите ресурсы.")
        return
    await state.update_data(resources=message.text)
    await state.set_state(FullPackageStates.step12)
    await message.answer("Видите ли вы какие-то риски? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 12: Риски (ТЭО)
@dp.message(FullPackageStates.step12)
async def fp_step12(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(risks="")
    else:
        await state.update_data(risks=message.text)
    await state.set_state(FullPackageStates.step13)
    await message.answer("Нужно ли соблюдать законы или стандарты? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 13: Нормативы (ТЭО)
@dp.message(FullPackageStates.step13)
async def fp_step13(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(norms="")
    else:
        await state.update_data(norms=message.text)
    await state.set_state(FullPackageStates.step14)
    await message.answer("Какой финансовый результат вы ожидаете? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 14: Эффект (ТЭО)
@dp.message(FullPackageStates.step14)
async def fp_step14(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(effect="")
    else:
        await state.update_data(effect=message.text)
    await state.set_state(FullPackageStates.step15)
    await message.answer("У вас уже есть какие-то расчёты или файлы? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 15: Данные (ТЭО)
@dp.message(FullPackageStates.step15)
async def fp_step15(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(teo_data="")
    else:
        await state.update_data(teo_data=message.text)
    await state.set_state(FullPackageStates.step16)
    await message.answer("На какой срок вы строите план?", reply_markup=horizon_keyboard())

# Шаг 16: Горизонт (ТЭО)
@dp.message(FullPackageStates.step16)
async def fp_step16(message: types.Message, state: FSMContext):
    if message.text not in ["1 год", "3 года", "5 лет"]:
        await message.answer("Выберите из предложенных вариантов.", reply_markup=horizon_keyboard())
        return
    await state.update_data(teo_horizon=message.text)
    await state.set_state(FullPackageStates.step17)
    await message.answer("Приложите дополнительные материалы для ТЭО (пока можно только пропустить).", reply_markup=nav_keyboard())

# Шаг 17: Файлы ТЭО
@dp.message(FullPackageStates.step17)
async def fp_step17(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(files_teo=file_name)
    elif "пропустить" in message.text.lower():
        await state.update_data(files_teo="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return
    await state.set_state(FullPackageStates.step18)
    await message.answer("Расскажите, из чего будет складываться ваш доход? Какие источники выручки? (Финмодель)", reply_markup=nav_keyboard())

# Шаг 18: Доходы (Финмодель)
@dp.message(FullPackageStates.step18)
async def fp_step18(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите доходы.")
        return
    await state.update_data(income=message.text)
    await state.set_state(FullPackageStates.step19)
    await message.answer("Какие затраты вам предстоят? (постоянные и переменные)", reply_markup=nav_keyboard())

# Шаг 19: Затраты (Финмодель)
@dp.message(FullPackageStates.step19)
async def fp_step19(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, опишите затраты.")
        return
    await state.update_data(costs=message.text)
    await state.set_state(FullPackageStates.step20)
    await message.answer("Сколько денег нужно вложить на старте?", reply_markup=nav_keyboard())

# Шаг 20: Инвестиции (Финмодель)
@dp.message(FullPackageStates.step20)
async def fp_step20(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Укажите сумму инвестиций.")
        return
    await state.update_data(investment=message.text)
    await state.set_state(FullPackageStates.step21)
    await message.answer("Через сколько месяцев планируете выйти на безубыточность? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 21: Безубыточность (Финмодель)
@dp.message(FullPackageStates.step21)
async def fp_step21(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(breakeven="")
    else:
        await state.update_data(breakeven=message.text)
    await state.set_state(FullPackageStates.step22)
    await message.answer("Какие финансовые показатели важны? (ROI, маржинальность и т.д.) (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 22: Метрики (Финмодель)
@dp.message(FullPackageStates.step22)
async def fp_step22(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(metrics="")
    else:
        await state.update_data(metrics=message.text)
    await state.set_state(FullPackageStates.step23)
    await message.answer("Есть готовые финансовые данные? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 23: Данные (Финмодель)
@dp.message(FullPackageStates.step23)
async def fp_step23(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(fm_data="")
    else:
        await state.update_data(fm_data=message.text)
    await state.set_state(FullPackageStates.step24)
    await message.answer("На какой период прогноз?", reply_markup=horizon_keyboard())

# Шаг 24: Горизонт (Финмодель)
@dp.message(FullPackageStates.step24)
async def fp_step24(message: types.Message, state: FSMContext):
    if message.text not in ["1 год", "3 года", "5 лет"]:
        await message.answer("Выберите вариант.", reply_markup=horizon_keyboard())
        return
    await state.update_data(fm_horizon=message.text)
    await state.set_state(FullPackageStates.step25)
    await message.answer("Напишите краткое резюме проекта (1–2 предложения). (Бизнес-план)", reply_markup=nav_keyboard())

# Шаг 25: Резюме (Бизнес-план)
@dp.message(FullPackageStates.step25)
async def fp_step25(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, напишите резюме.")
        return
    await state.update_data(summary=message.text)
    await state.set_state(FullPackageStates.step26)
    await message.answer("Опишите подробнее ваш продукт или услугу. В чём уникальность?", reply_markup=nav_keyboard())

# Шаг 26: Продукт (Бизнес-план)
@dp.message(FullPackageStates.step26)
async def fp_step26(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите продукт.")
        return
    await state.update_data(product=message.text)
    await state.set_state(FullPackageStates.step27)
    await message.answer("Кто ваши конкуренты? В чём преимущество?", reply_markup=nav_keyboard())

# Шаг 27: Конкуренты (Бизнес-план)
@dp.message(FullPackageStates.step27)
async def fp_step27(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите конкурентов.")
        return
    await state.update_data(bp_competitors=message.text)
    await state.set_state(FullPackageStates.step28)
    await message.answer("Как планируете привлекать клиентов?", reply_markup=nav_keyboard())

# Шаг 28: Маркетинг (Бизнес-план)
@dp.message(FullPackageStates.step28)
async def fp_step28(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Опишите маркетинг.")
        return
    await state.update_data(marketing=message.text)
    await state.set_state(FullPackageStates.step29)
    await message.answer("Расскажите о команде. (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 29: Команда (Бизнес-план)
@dp.message(FullPackageStates.step29)
async def fp_step29(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(team="")
    else:
        await state.update_data(team=message.text)
    await state.set_state(FullPackageStates.step30)
    await message.answer("Какой план продаж на первый год? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 30: План продаж (Бизнес-план)
@dp.message(FullPackageStates.step30)
async def fp_step30(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(sales="")
    else:
        await state.update_data(sales=message.text)
    await state.set_state(FullPackageStates.step31)
    await message.answer("Какие риски видите и как их снизить? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 31: Риски (Бизнес-план)
@dp.message(FullPackageStates.step31)
async def fp_step31(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(bp_risks="")
    else:
        await state.update_data(bp_risks=message.text)
    await state.set_state(FullPackageStates.step32)
    await message.answer("Какой стартовый капитал? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 32: Стартовый капитал (Бизнес-план)
@dp.message(FullPackageStates.step32)
async def fp_step32(message: types.Message, state: FSMContext):
    if "пропустить" in message.text.lower():
        await state.update_data(capital="")
    else:
        await state.update_data(capital=message.text)
    await state.set_state(FullPackageStates.step33)
    await message.answer("Приложите финансовую модель, если есть. (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 33: Финмодель (файл)
@dp.message(FullPackageStates.step33)
async def fp_step33(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(finance_file=file_name)
    elif "пропустить" in message.text.lower():
        await state.update_data(finance_file="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return
    await state.set_state(FullPackageStates.step34)
    await message.answer("Дополнительные материалы? (можно пропустить)", reply_markup=nav_keyboard())

# Шаг 34: Дополнительные файлы (Бизнес-план)
@dp.message(FullPackageStates.step34)
async def fp_step34(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        file_path = os.path.join("downloads", f"{datetime.datetime.now().timestamp()}_{file_name}")
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        await state.update_data(bp_files=file_name)
    elif "пропустить" in message.text.lower():
        await state.update_data(bp_files="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return
    # Финальная сводка
    data = await state.get_data()
    fields = {
        "name": "Название",
        "essence": "Суть проекта",
        "audience": "Целевая аудитория",
        "features": "Функции",
        "competitors": "Конкуренты (ТЗ)",
        "tech_limits": "Технические ограничения",
        "deadline": "Срок",
        "budget": "Бюджет",
        "files_tz": "Файлы ТЗ",
        "goal": "Главная задача (ТЭО)",
        "resources": "Ресурсы",
        "risks": "Риски",
        "norms": "Нормативы",
        "effect": "Эффект",
        "teo_data": "Данные",
        "teo_horizon": "Горизонт (ТЭО)",
        "files_teo": "Файлы ТЭО",
        "income": "Доходы",
        "costs": "Затраты",
        "investment": "Инвестиции",
        "breakeven": "Точка безубыточности",
        "metrics": "Метрики",
        "fm_data": "Финансовые данные",
        "fm_horizon": "Горизонт (Финмодель)",
        "summary": "Резюме",
        "product": "Продукт",
        "bp_competitors": "Конкуренты (БП)",
        "marketing": "Маркетинг",
        "team": "Команда",
        "sales": "План продаж",
        "bp_risks": "Риски (БП)",
        "capital": "Стартовый капитал",
        "finance_file": "Файл финмодели",
        "bp_files": "Доп. файлы"
    }
    await finalize_order(message, state, "Полный пакет", fields, price_override=9000)

# ===================== СЦЕНАРИЙ ТЗ =====================
# (Здесь должны быть все обработчики ТЗ, ТЭО, Финмодель, Бизнес-план, Консультация, Мои заявки, Админка, Свободные запросы, Доп. соглашения и т.д.
# Для краткости я их не повторяю, они уже есть в вашей предыдущей версии.
# Убедитесь, что вы добавили их перед этим блоком или вставили полный файл.)

# ===================== ЗАПУСК БОТА (webhook) =====================
async def main():
    await init_db()
    # await dp.start_polling(bot)   # отключено для webhook
    print("✅ Бот запущен в режиме webhook, polling отключён")

if __name__ == "__main__":
    asyncio.run(main())
