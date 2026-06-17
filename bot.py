import asyncio
import re
import os
import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from database import (
    init_db, get_or_create_user, create_order, get_user_orders,
    get_all_orders, get_order_by_id, update_order_status,
    AsyncSessionLocal, Order,
)
from sqlalchemy import select

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(',')))

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

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
    kb = [
        [KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🏠 Главное меню")],
        [KeyboardButton(text="⏭ Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def horizon_keyboard():
    kb = [
        [KeyboardButton(text="1 год"), KeyboardButton(text="3 года")],
        [KeyboardButton(text="5 лет")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def stage_keyboard():
    kb = [
        [KeyboardButton(text="💡 Идея")],
        [KeyboardButton(text="⚙️ Прототип")],
        [KeyboardButton(text="🚀 Готовый продукт")]
    ]
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
    budget_choice = State()
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

class ConsultStates(StatesGroup):
    description = State()
    stage = State()
    goal = State()

class QuickDocStates(StatesGroup):
    pages = State()
    deadline = State()
    requirements = State()
    files = State()

class ExtraAgreementStates(StatesGroup):
    contract_info = State()
    changes = State()
    template = State()
    confirm = State()

class LegalDocStates(StatesGroup):
    contract_types = State()
    has_projects = State()
    deadline = State()
    registry = State()
    requirements = State()
    confirm = State()

class GrantStates(StatesGroup):
    direction = State()
    has_bp = State()
    documents = State()
    confirm = State()

class StrategyStates(StatesGroup):
    has_company = State()
    has_subcontractors = State()
    urgent_tasks = State()
    need_sales = State()
    confirm = State()

class BPSportsStates(StatesGroup):
    infrastructure = State()
    scale = State()
    data_available = State()
    confirm = State()

# ===================== СЛОВАРЬ КЛАССОВ СОСТОЯНИЙ =====================
STATE_CLASSES = {
    "TZStates": TZStates,
    "TEOStates": TEOStates,
    "FMStates": FMStates,
    "BPStates": BPStates,
    "ConsultStates": ConsultStates,
    "QuickDocStates": QuickDocStates,
    "ExtraAgreementStates": ExtraAgreementStates,
    "LegalDocStates": LegalDocStates,
    "GrantStates": GrantStates,
    "StrategyStates": StrategyStates,
    "BPSportsStates": BPSportsStates,
}

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def is_skip(text: str) -> bool:
    return text.lower().strip() in ("пропустить", "⏭ пропустить")


def generate_document(prompt: str, data: dict) -> str:
    """Генерация черновика документа через OpenAI. Если ключ не задан — возвращает None."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        user_content = "\n".join(f"{k}: {v}" for k, v in data.items() if v)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1500,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Не удалось сгенерировать черновик: {e}"


async def download_file(message: types.Message, state: FSMContext, field: str) -> str:
    """Скачивает файл из сообщения, сохраняет в downloads/, возвращает имя файла."""
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        os.makedirs("downloads", exist_ok=True)
        ts = datetime.datetime.now().timestamp()
        file_path = os.path.join("downloads", f"{ts}_{file_name}")
        tg_file = await bot.get_file(file_id)
        await bot.download_file(tg_file.file_path, file_path)
        await state.update_data(**{field: file_name})
        return file_name
    return None


async def finalize_order(message: types.Message, state: FSMContext, service_name: str, fields: dict,
                          price_override: float | None = None):
    """Сохраняет заявку в БД, выводит итог пользователю."""
    data = await state.get_data()
    summary = f"📋 {service_name}\n\n"
    for key, label in fields.items():
        val = data.get(key) or "—"
        summary += f"{label}: {val}\n"
    if price_override is not None:
        summary += f"\n💰 Стоимость: {price_override} руб."

    await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    order_id = await create_order(
        telegram_id=message.from_user.id,
        service=service_name,
        data={k: data.get(k, "") for k in fields},
    )

    await message.answer(
        f"{summary}\n\n✅ Заявка №{order_id} создана! Передаём специалисту.",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()


# ===================== ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ =====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        "Добро пожаловать в AIdea Lab PRO!\n\n"
        "Я помогу вам подготовить документы для бизнеса. Выберите услугу:",
        reply_markup=main_menu_keyboard()
    )

STATUS_LABELS = {
    "NEW": "🆕 Новая",
    "IN_PROGRESS": "⚙️ В работе",
    "DONE": "✅ Готово",
    "CANCELLED": "❌ Отменена",
}

@dp.message(lambda msg: msg.text == "📋 Мои заявки")
async def my_orders(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order)
            .where(Order.user_telegram_id == user.telegram_id)
            .order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()
    if not orders:
        await message.answer("У вас пока нет заявок.", reply_markup=main_menu_keyboard())
        return
    text = "📋 ВАШИ ЗАЯВКИ:\n\n"
    rows = []
    for order in orders:
        status = STATUS_LABELS.get(order.status, order.status)
        date = order.created_at.strftime("%d.%m.%Y")
        text += f"#{order.id} — {order.service} — {status} ({date})\n"
        rows.append([InlineKeyboardButton(
            text=f"📄 Заявка #{order.id} · {order.service[:20]}",
            callback_data=f"view_order:{order.id}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(lambda c: c.data and c.data.startswith("view_order:"))
async def cb_view_order(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    if callback.from_user.id != (await get_order_by_id(order_id)).user_telegram_id and not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    import json
    try:
        data = json.loads(order.data)
        details = "\n".join(f"  {k}: {v}" for k, v in data.items() if v)
    except Exception:
        details = order.data or "—"
    status = STATUS_LABELS.get(order.status, order.status)
    date = order.created_at.strftime("%d.%m.%Y %H:%M")
    text = (
        f"📄 Заявка #{order.id}\n"
        f"Услуга: {order.service}\n"
        f"Статус: {status}\n"
        f"Дата: {date}\n\n"
        f"Данные:\n{details}"
    )
    await callback.message.answer(text)
    await callback.answer()

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
        "TZStates": {
            "essence": "name", "audience": "essence", "features": "audience",
            "competitors": "features", "tech_limits": "competitors",
            "deadline": "tech_limits", "budget": "deadline", "files": "budget"
        },
        "TEOStates": {
            "resources": "goal", "risks": "resources", "norms": "risks",
            "effect": "norms", "data": "effect", "horizon": "data", "files": "horizon"
        },
        "FMStates": {
            "costs": "income", "investment": "costs", "breakeven": "investment",
            "metrics": "breakeven", "data": "metrics", "horizon": "data"
        },
        "BPStates": {
            "product": "summary", "competitors": "product", "marketing": "competitors",
            "team": "marketing", "sales": "team", "risks": "sales",
            "capital": "risks", "finance_file": "capital", "files": "finance_file"
        },
        "ConsultStates": {"stage": "description", "goal": "stage"},
        "QuickDocStates": {"deadline": "pages", "requirements": "deadline", "files": "requirements"},
        "ExtraAgreementStates": {"changes": "contract_info", "template": "changes", "confirm": "template"},
        "LegalDocStates": {
            "has_projects": "contract_types", "deadline": "has_projects",
            "registry": "deadline", "requirements": "registry", "confirm": "requirements"
        },
        "GrantStates": {"has_bp": "direction", "documents": "has_bp", "confirm": "documents"},
        "StrategyStates": {
            "has_subcontractors": "has_company", "urgent_tasks": "has_subcontractors",
            "need_sales": "urgent_tasks", "confirm": "need_sales"
        },
        "BPSportsStates": {"scale": "infrastructure", "data_available": "scale", "confirm": "data_available"},
    }

    prefix = current.split(":")[0]
    step = current.split(":")[1]
    if prefix in back_map and step in back_map[prefix]:
        prev = back_map[prefix][step]
        cls = STATE_CLASSES.get(prefix)
        if cls:
            await state.set_state(getattr(cls, prev))
            await message.answer("Вернулись назад.", reply_markup=nav_keyboard())
    else:
        await message.answer("Это первый шаг.", reply_markup=nav_keyboard())

@dp.message(lambda msg: msg.text == "❓ Помощь")
async def cmd_help(message: types.Message, state: FSMContext):
    await message.answer(
        "ℹ️ AIdea Lab PRO — сервис подготовки бизнес-документов.\n\n"
        "📋 Техническое задание — для IT-проектов\n"
        "📊 ТЭО — технико-экономическое обоснование\n"
        "💰 Финансовая модель — прогноз доходов и расходов\n"
        "📈 Бизнес-план — полный план для инвесторов\n"
        "💬 Консультация — поможем выбрать нужный документ\n\n"
        "По вопросам: @aidealab_support",
        reply_markup=main_menu_keyboard()
    )

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
    if is_skip(message.text):
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
    if is_skip(message.text):
        await state.update_data(competitors="")
    else:
        await state.update_data(competitors=message.text)
    await state.set_state(TZStates.tech_limits)
    await message.answer("Есть ли технические рамки? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.tech_limits)
async def tz_tech_limits(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(tech_limits="")
    else:
        await state.update_data(tech_limits=message.text)
    await state.set_state(TZStates.deadline)
    await message.answer("Когда вы хотите получить готовый результат? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TZStates.deadline)
async def tz_deadline(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(deadline="")
    else:
        await state.update_data(deadline=message.text)
    await state.set_state(TZStates.budget)
    await message.answer(
        "Есть ли у вас бюджет на этот проект? Если да, укажите сумму. Если нет, напишите 'нет' или выберите 'Пропустить'.",
        reply_markup=nav_keyboard()
    )

@dp.message(TZStates.budget)
async def tz_budget(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if is_skip(message.text):
        await state.update_data(budget="")
        await state.set_state(TZStates.files)
        await message.answer("Приложите дополнительные материалы (макеты, референсы) или нажмите 'Пропустить'.", reply_markup=nav_keyboard())
        return
    if text in ["нет", "нисколько", "0", "без бюджета", "не готов", "не знаю", "нет бюджета"]:
        await state.update_data(budget="0 (не указан)")
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="💬 Консультация")], [KeyboardButton(text="Продолжить")]],
            resize_keyboard=True
        )
        await message.answer("Понимаю. Хотите перейти к консультации или продолжить?", reply_markup=kb)
        await state.set_state(TZStates.budget_choice)
        return
    try:
        digits = re.sub(r'[^0-9]', '', text)
        if digits:
            await state.update_data(budget=f"{int(digits)} руб.")
        else:
            await state.update_data(budget=text)
    except Exception:
        await state.update_data(budget=text)
    await state.set_state(TZStates.files)
    await message.answer("Приложите дополнительные материалы (макеты, референсы) или нажмите 'Пропустить'.", reply_markup=nav_keyboard())

@dp.message(TZStates.budget_choice)
async def tz_budget_choice(message: types.Message, state: FSMContext):
    if message.text == "💬 Консультация":
        await state.clear()
        await start_consult(message, state)
    else:
        await state.set_state(TZStates.files)
        await message.answer("Приложите дополнительные материалы (макеты, референсы) или нажмите 'Пропустить'.", reply_markup=nav_keyboard())

@dp.message(TZStates.files)
async def tz_files(message: types.Message, state: FSMContext):
    if message.document:
        fname = await download_file(message, state, "files")
    elif is_skip(message.text):
        await state.update_data(files="")
    else:
        await message.answer("Пожалуйста, загрузите файл или нажмите 'Пропустить'.")
        return

    data = await state.get_data()
    doc = generate_document(
        "Ты — эксперт по разработке ТЗ. На основе данных сгенерируй структурированное техническое задание.",
        data
    )
    if doc and "⚠️" not in doc:
        await message.answer(f"📄 Черновик ТЗ от ИИ:\n\n{doc[:3000]}")

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

# ===================== СЦЕНАРИЙ ТЭО =====================
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
    if is_skip(message.text):
        await state.update_data(risks="")
    else:
        await state.update_data(risks=message.text)
    await state.set_state(TEOStates.norms)
    await message.answer("Нужно ли соблюдать законы или стандарты? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.norms)
async def teo_norms(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(norms="")
    else:
        await state.update_data(norms=message.text)
    await state.set_state(TEOStates.effect)
    await message.answer("Какой финансовый результат вы ожидаете? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.effect)
async def teo_effect(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(effect="")
    else:
        await state.update_data(effect=message.text)
    await state.set_state(TEOStates.data)
    await message.answer("У вас уже есть какие-то расчёты или файлы? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(TEOStates.data)
async def teo_data(message: types.Message, state: FSMContext):
    if is_skip(message.text):
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
        await download_file(message, state, "files")
    elif is_skip(message.text):
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
    if is_skip(message.text):
        await state.update_data(breakeven="")
    else:
        await state.update_data(breakeven=message.text)
    await state.set_state(FMStates.metrics)
    await message.answer("Какие финансовые показатели важны? (ROI, маржинальность и т.д.) (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(FMStates.metrics)
async def fm_metrics(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(metrics="")
    else:
        await state.update_data(metrics=message.text)
    await state.set_state(FMStates.data)
    await message.answer("Есть готовые финансовые данные? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(FMStates.data)
async def fm_data(message: types.Message, state: FSMContext):
    if is_skip(message.text):
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
    if is_skip(message.text):
        await state.update_data(team="")
    else:
        await state.update_data(team=message.text)
    await state.set_state(BPStates.sales)
    await message.answer("Какой план продаж на первый год? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.sales)
async def bp_sales(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(sales="")
    else:
        await state.update_data(sales=message.text)
    await state.set_state(BPStates.risks)
    await message.answer("Какие риски видите и как их снизить? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.risks)
async def bp_risks(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(risks="")
    else:
        await state.update_data(risks=message.text)
    await state.set_state(BPStates.capital)
    await message.answer("Какой стартовый капитал? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.capital)
async def bp_capital(message: types.Message, state: FSMContext):
    if is_skip(message.text):
        await state.update_data(capital="")
    else:
        await state.update_data(capital=message.text)
    await state.set_state(BPStates.finance_file)
    await message.answer("Приложите финансовую модель, если есть. (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.finance_file)
async def bp_finance_file(message: types.Message, state: FSMContext):
    if message.document:
        await download_file(message, state, "finance_file")
    elif is_skip(message.text):
        await state.update_data(finance_file="")
    else:
        await message.answer("Загрузите файл или нажмите 'Пропустить'.")
        return
    await state.set_state(BPStates.files)
    await message.answer("Дополнительные материалы? (можно пропустить)", reply_markup=nav_keyboard())

@dp.message(BPStates.files)
async def bp_files(message: types.Message, state: FSMContext):
    if message.document:
        await download_file(message, state, "files")
    elif is_skip(message.text):
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
    summary = (
        f"📋 КОНСУЛЬТАЦИЯ\n\n"
        f"Проект: {data.get('description')}\n"
        f"Этап: {stage}\n"
        f"Цель: {data.get('goal')}\n\n"
        f"💡 {rec}\n\n"
        "Хотите перейти к заказу? Выберите услугу в меню."
    )
    await message.answer(summary, reply_markup=main_menu_keyboard())
    await state.clear()

# ===================== ПОЛНЫЙ ПАКЕТ / ПРОВЕРКА / ДОРАБОТКА (заглушки) =====================
@dp.message(lambda msg: msg.text == "📦 Полный пакет")
async def full_package(message: types.Message, state: FSMContext):
    await message.answer(
        "📦 Полный пакет — ТЗ + ТЭО + Финансовая модель + Бизнес-план.\n\n"
        "Этот режим в разработке. Пока оформите каждый документ отдельно.",
        reply_markup=main_menu_keyboard()
    )

@dp.message(lambda msg: msg.text == "🔍 Проверка документов")
async def check_docs(message: types.Message, state: FSMContext):
    await message.answer(
        "🔍 Проверка документов — скоро будет доступна.\n\n"
        "Мы проверим готовый документ на соответствие требованиям и дадим рекомендации.",
        reply_markup=main_menu_keyboard()
    )

@dp.message(lambda msg: msg.text == "✏️ Доработка документов")
async def revise_docs(message: types.Message, state: FSMContext):
    await message.answer(
        "✏️ Доработка документов — скоро будет доступна.\n\n"
        "Загрузите готовый документ, и мы его улучшим.",
        reply_markup=main_menu_keyboard()
    )

# ===================== АДМИН-ПАНЕЛЬ =====================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_order_keyboard(order_id: int, current_status: str) -> InlineKeyboardMarkup:
    statuses = [
        ("🆕 Новая", "NEW"),
        ("⚙️ В работе", "IN_PROGRESS"),
        ("✅ Готово", "DONE"),
        ("❌ Отменена", "CANCELLED"),
    ]
    buttons = []
    for label, code in statuses:
        if code != current_status:
            buttons.append(
                InlineKeyboardButton(text=label, callback_data=f"setstatus:{order_id}:{code}")
            )
    buttons.append(
        InlineKeyboardButton(text="📨 Уведомить клиента", callback_data=f"notify:{order_id}")
    )
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    orders = await get_all_orders(limit=20)
    if not orders:
        await message.answer("Заявок пока нет.")
        return
    await message.answer(f"📊 Последние заявки ({len(orders)} шт.):")
    for order in orders:
        status = STATUS_LABELS.get(order.status, order.status)
        date = order.created_at.strftime("%d.%m.%Y %H:%M")
        text = (
            f"№{order.id} | {order.service}\n"
            f"👤 ID: {order.user_telegram_id}\n"
            f"{status}  🕐 {date}"
        )
        await message.answer(text, reply_markup=admin_order_keyboard(order.id, order.status))

@dp.callback_query(lambda c: c.data and c.data.startswith("setstatus:"))
async def cb_set_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    _, order_id_str, new_status = callback.data.split(":")
    order_id = int(order_id_str)
    await update_order_status(order_id, new_status)
    label = STATUS_LABELS.get(new_status, new_status)
    order = await get_order_by_id(order_id)
    await callback.message.edit_reply_markup(
        reply_markup=admin_order_keyboard(order_id, new_status)
    )
    await callback.answer(f"Статус обновлён: {label}", show_alert=False)
    await callback.message.answer(f"✅ Заявка №{order_id} → {label}")

@dp.callback_query(lambda c: c.data and c.data.startswith("notify:"))
async def cb_notify_client(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    status = STATUS_LABELS.get(order.status, order.status)
    try:
        await bot.send_message(
            chat_id=order.user_telegram_id,
            text=(
                f"📬 Обновление по вашей заявке №{order.id}!\n\n"
                f"Услуга: {order.service}\n"
                f"Статус: {status}\n\n"
                f"{'✅ Ваш документ готов! Ожидайте ответа от специалиста.' if order.status == 'DONE' else 'Специалист уже работает над вашим заказом.'}"
            )
        )
        await callback.answer("📨 Клиент уведомлён!", show_alert=False)
        await callback.message.answer(f"✅ Уведомление отправлено клиенту {order.user_telegram_id}")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

# ===================== ОБРАБОТЧИКИ СВОБОДНЫХ ТЕКСТОВЫХ ЗАПРОСОВ =====================
@dp.message(F.text)
async def handle_free_text(message: types.Message, state: FSMContext):
    text = message.text.lower()
    if any(w in text for w in ["гпх", "смз", "тд", "отчуждение прав", "рид", "реестр по"]):
        await state.set_state(LegalDocStates.contract_types)
        await message.answer(
            "Вы обратились за юридической доработкой договоров. Уточните:\n"
            "Какие договоры нужно доработать? (ГПХ, СМЗ, ТД, все три)",
            reply_markup=nav_keyboard()
        )
        return
    if any(w in text for w in ["доп соглашение", "доп. соглашение", "дополнительное соглашение"]):
        await state.set_state(ExtraAgreementStates.contract_info)
        await message.answer(
            "Дополнительное соглашение. Укажите номер и дату договора (можно пропустить).",
            reply_markup=nav_keyboard()
        )
        return
    if any(w in text for w in ["грант", "агростартап", "минсельхоз"]):
        await state.set_state(GrantStates.direction)
        await message.answer(
            "Грант Агростартап. Укажите направление (животноводство, растениеводство и т.д.)",
            reply_markup=nav_keyboard()
        )
        return
    if any(w in text for w in ["строительство", "монолитное", "сро", "подрядчик", "охрана труда"]):
        await state.set_state(StrategyStates.has_company)
        await message.answer(
            "Стратегия для строительного бизнеса. У вас уже есть ООО или ИП? (да/нет)",
            reply_markup=nav_keyboard()
        )
        return
    if any(w in text for w in ["бизнес план", "окупаемость", "доходы расходы", "инвестиции", "конно-спортивный"]):
        await state.set_state(BPSportsStates.infrastructure)
        await message.answer(
            "Бизнес-план. У вас есть земля и инфраструктура? (да/нет)",
            reply_markup=nav_keyboard()
        )
        return
    await message.answer("Выберите услугу в меню или опишите задачу подробнее.", reply_markup=main_menu_keyboard())

# ===================== ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ =====================
@dp.message(ExtraAgreementStates.contract_info)
async def extra_contract(message: types.Message, state: FSMContext):
    await state.update_data(contract_info=message.text if not is_skip(message.text) else "не указано")
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
    price = 450 if any(w in str(data).lower() for w in ["срочно", "сегодня"]) else 300
    await finalize_order(message, state, "Дополнительное соглашение", {
        "contract_info": data.get("contract_info", "—"),
        "changes": data.get("changes", "—"),
        "template": data.get("template", "—"),
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
        "direction": data.get("direction", "—"),
        "has_bp": data.get("has_bp", "—"),
        "documents": data.get("documents", "—"),
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
        "has_company": data.get("has_company", "—"),
        "has_subcontractors": data.get("has_subcontractors", "—"),
        "urgent_tasks": data.get("urgent_tasks", "—"),
        "need_sales": data.get("need_sales", "—"),
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
        "infrastructure": data.get("infrastructure", "—"),
        "scale": data.get("scale", "—"),
        "data_available": data.get("data_available", "—"),
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
        "contract_types": data.get("contract_types", "—"),
        "has_projects": data.get("has_projects", "—"),
        "deadline": data.get("deadline", "—"),
        "registry": data.get("registry", "—"),
        "requirements": data.get("requirements", "—"),
    }, price_override=6500)

# ===================== ЗАПУСК =====================
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
