# db.py - АСИНХРОННА ВЕРСІЯ
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import aiosqlite # Потрібен для асинхронної роботи з SQLite

# 1. Налаштування підключення до АСИНХРОННОГО SQLite
# Використовуємо 'sqlite+aiosqlite:///' та create_async_engine
# check_same_thread=False необхідний для SQLite в асинхронному режимі.
ASYNC_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///shop.db", 
    echo=True # Для налагодження (за бажанням)
)
Base = declarative_base()

# 2. Опис моделі Товару (Item)
class Item(Base):
    __tablename__ = 'items'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False) 
    category = Column(String, nullable=False, index=True) 
    price = Column(Integer, nullable=False)   
    description = Column(String)
    image_link = Column(String)              
    is_available = Column(Boolean, default=True) 

    def __repr__(self):
        return f"Item(id={self.id}, name='{self.name}', price={self.price})"

# 3. Опис моделі Користувача (User)
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True) 
    username = Column(String)
    state = Column(String, default='main_menu') 
    
    # НОВЕ ПОЛЕ ДЛЯ ГРИ
    last_game_time = Column(String, nullable=True) # Зберігаємо час як рядок (ISO format) або використовуємо SQLAlchemy.DateTime

    def __repr__(self):
        return f"User(id={self.id}, telegram_id={self.telegram_id})"

# 4. Опис моделі Елемента Кошика (CartItem)
class CartItem(Base):
    __tablename__ = 'cart_items'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)   
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    quantity = Column(Integer, default=1)                   

    item = relationship("Item") 

    def __repr__(self):
        return f"CartItem(user_id={self.user_id}, item_id={self.item_id}, qty={self.quantity})"

# 5. Створення таблиць у базі даних
async def create_db():
    async with ASYNC_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("База даних і таблиці створені!")

# 6. Створення АСИНХРОННОЇ сесії
# Замість sessionmaker, використовуємо async_sessionmaker
AsyncSessionLocal = async_sessionmaker(ASYNC_ENGINE, expire_on_commit=False)

# Допоміжна функція-генератор для отримання сесії
async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

if __name__ == "__main__":
    # Запускаємо асинхронну функцію для створення БД
    import asyncio
    asyncio.run(create_db())
    
# СИНХРОННА СЕСІЯ БІЛЬШЕ НЕ ВИКОРИСТОВУЄТЬСЯ. ЗАМІСТЬ НЕЇ - AsyncSessionLocal
# Session = sessionmaker(bind=ENGINE) 
