import os
import json
import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Float, select
)

# Strip sslmode — asyncpg on Replit's internal Postgres doesn't use SSL
_raw = os.environ["DATABASE_URL"]
_p = urlparse(_raw)
_qs = parse_qs(_p.query)
_qs.pop("sslmode", None)
DATABASE_URL = urlunparse((
    "postgresql+asyncpg",
    _p.netloc, _p.path, _p.params,
    urlencode({k: v[0] for k, v in _qs.items()}),
    _p.fragment,
))

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# ===================== МОДЕЛИ =====================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, nullable=False)
    service = Column(String, nullable=False)
    status = Column(String, default="NEW")
    data = Column(Text, nullable=True)   # JSON с ответами
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


# ===================== ИНИЦИАЛИЗАЦИЯ =====================

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ===================== ПОЛЬЗОВАТЕЛИ =====================

async def get_user(telegram_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_or_create_user(telegram_id: int, username: str | None, full_name: str | None) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def update_user_phone(telegram_id: int, phone: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.phone = phone
            await session.commit()


# ===================== ЗАКАЗЫ =====================

async def create_order(telegram_id: int, service: str, data: dict) -> int:
    async with AsyncSessionLocal() as session:
        order = Order(
            user_telegram_id=telegram_id,
            service=service,
            status="NEW",
            data=json.dumps(data, ensure_ascii=False),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


async def get_user_orders(telegram_id: int) -> list:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order)
            .where(Order.user_telegram_id == telegram_id)
            .order_by(Order.created_at.desc())
        )
        return result.scalars().all()


async def get_all_orders(limit: int = 30) -> list:
    """Return the most recent orders across all users."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(limit)
        )
        return result.scalars().all()


async def get_order_by_id(order_id: int):
    """Return a single order by ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()


async def update_order_status(order_id: int, status: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if order:
            order.status = status
            order.updated_at = datetime.datetime.utcnow()
            await session.commit()


# ===================== ФАЙЛЫ =====================

async def save_order_file(order_id: int, file_name: str, file_path: str):
    async with AsyncSessionLocal() as session:
        f = OrderFile(order_id=order_id, file_name=file_name, file_path=file_path)
        session.add(f)
        await session.commit()
