# db.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# 1. Налаштування підключення до SQLite
ENGINE = create_engine("sqlite:///shop.db")
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

    def __repr__(self):
        return f"User(id={self.id}, telegram_id={self.telegram_id})"

# 4. Опис моделі Елемента Кошика (CartItem) - ВКЛЮЧАЄ ЗВ'ЯЗОК
class CartItem(Base):
    __tablename__ = 'cart_items'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)   
    
    # Зв'язок з Item: створюємо зовнішній ключ, що посилається на items.id
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    
    quantity = Column(Integer, default=1)                   

    # relationship дозволяє нам звертатися до деталей товару: cart_item.item.name
    item = relationship("Item") 

    def __repr__(self):
        return f"CartItem(user_id={self.user_id}, item_id={self.item_id}, qty={self.quantity})"

# 5. Створення таблиць у базі даних
def create_db():
    Base.metadata.create_all(ENGINE)
    print("База даних і таблиці створені!")

# 6. Створення сесії для взаємодії
Session = sessionmaker(bind=ENGINE)

if __name__ == "__main__":
    create_db()