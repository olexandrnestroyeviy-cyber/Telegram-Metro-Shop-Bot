# bot.py - ФІНАЛЬНА АСИНХРОННА ВЕРСІЯ (для SQLAlchemy AsyncIO)
import asyncio
import logging
import re 
import random
# ВИДАЛЕНО: datetime та timedelta більше не потрібні, оскільки немає COOLDOWN_HOURS
# from datetime import datetime, timedelta 

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
# ВИДАЛЕНО: Неможливо імпортувати Text. Використовуємо F.text
# from aiogram.filters.text import Text 
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

# ЗМІНА: Імпортуємо асинхронні інструменти
from db import AsyncSessionLocal, Item, User, CartItem, create_db, ASYNC_ENGINE

# --- КОНФІГУРАЦІЯ (ОБОВ'ЯЗКОВО ЗАМІНИТИ!) ---
TOKEN = "8203607429:AAFyudKK3pCEPXu4SmC-Px7I5wmMCTSohw4" 
ADMIN_ID = 7249241490 # Ваш Telegram ID
CURRENCY = " грн" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
# ----------------------------------------------

# --- ДАНІ ДЛЯ НОВОЇ ФУНКЦІЇ ---
JOKES = [
    "Мені не потрібна терапія. Мені потрібна відпустка... Або код, який працює з першого разу.",
    "Що сказав нуль вісімці? – Класний пасок!",
    "Чому програмісти постійно плутають Різдво та Хелловін? Бо $DEC 25$ дорівнює $OCT 31$.",
    "Який найулюбленіший алкогольний напій програміста? Ром (ROM).",
    "На скільки потрібно знати англійську, щоб бути програмістом? На $4-8$ Гб.",
    "Після запуску, бот сказав: 'Я працюю!' – І це була його остання помилка.",
    "Найпопулярніша річ у роботі: перевіряти, чи правильно ти вимкнув мікрофон на мітингу.",
    "Купив собі бездротову мишку... забув, що вона на батарейках. Все одно провідна вийшла.",
    "Приходить програміст додому, дружина йому каже: 'Сходи в магазин, купи ковбаси. Якщо будуть яйця, купи десяток'. Він повертається з десятьма ковбасами. – А чому так багато? – Яйця були.",
]

# --- ДОПОМІЖНА ФУНКЦІЯ ---
def escape_markdown(text: str) -> str:
    """Екранує символи MarkdownV2."""
    escape_chars = r'\_*[]()~`>#+-=|}{.!$'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# --- FSM (FINITE STATE MACHINE) ---

class AddItem(StatesGroup):
    waiting_for_name = State()       
    waiting_for_category = State()   
    waiting_for_price = State()      
    waiting_for_description = State()

class Checkout(StatesGroup):
    waiting_for_confirmation = State() 

# --- СТВОРЕННЯ REPLY-КЛАВІАТУР ---

def get_reply_keyboard(is_admin: bool = False):
    """Створює Reply-клавіатуру для головного меню."""
    kb = [
        [types.KeyboardButton(text="🛒 Каталог Товарів"), types.KeyboardButton(text="🛍️ Мій Кошик")],
        # Кнопка "😂 Рандомний Мем"
        [types.KeyboardButton(text="😂 Рандомний Мем"), types.KeyboardButton(text="⚙️ Зв'язок з Адміном")]
    ]
    if is_admin:
        kb.append([types.KeyboardButton(text="/additem")])
    
    return types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        selective=True
    )

def get_back_to_menu_inline():
    """Створює Inline-кнопку для повернення в Головне меню."""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    return builder.as_markup()

# --- ОБРОБНИКИ КОМАНД ТА REPLY-МЕНЮ ---

@dp.message(Command("start", "menu"))
# ЗМІНА: Використовуємо F.text замість Text
@dp.message(F.text == "↩️ Головне меню")
async def cmd_start_or_menu(message: types.Message, state: FSMContext):
    await state.clear()
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).filter_by(telegram_id=message.from_user.id))
        user = result.scalars().first()
        
        is_admin = message.from_user.id == ADMIN_ID
        
        if not user:
            # Поле last_game_time залишається в моделі DB, але тут не використовується.
            # Якщо ви плануєте видалити його з db.py, тут нічого не зміниться.
            new_user = User(
                telegram_id=message.from_user.id, 
                username=message.from_user.username or 'N/A'
            )
            session.add(new_user)
            await session.commit()
            
    user_name = escape_markdown(message.from_user.first_name)
    
    await message.answer(
        f"Ласкаво просимо, **{user_name}**, до **METRO SHOP**\\! Оберіть дію:", 
        reply_markup=get_reply_keyboard(is_admin), 
        parse_mode="MarkdownV2"
    )

@dp.callback_query(F.data == "main_menu_inline")
async def go_to_main_menu_inline(callback: types.CallbackQuery, state: FSMContext):
    await state.clear() 
    await callback.message.edit_text(
        "Ви повернулися до головного меню\\. Оберіть дію:", 
        parse_mode="MarkdownV2"
    )
    await callback.answer()
    # Використовуємо message замість callback.message, щоб cmd_start_or_menu коректно обробив його
    await cmd_start_or_menu(callback.message, state)

# ----------------------------------------------------------------------
#                         ОБРОБНИКИ КНОПОК МЕНЮ (Reply Keyboard)
# ----------------------------------------------------------------------
@dp.message(F.text == "🛒 Каталог Товарів")
async def handle_catalog_button(message: types.Message):
    await show_categories(message)

@dp.message(F.text == "🛍️ Мій Кошик")
async def handle_cart_button(message: types.Message):
    await show_cart_message(message)

@dp.message(F.text == "⚙️ Зв'язок з Адміном")
async def handle_contact_button(message: types.Message):
    await contact_admin_message(message)

# ----------------------------------------------------------------------
#                           😂 НОВА ФУНКЦІЯ: РАНДОМНИЙ МЕМ! 😂
# ----------------------------------------------------------------------

# ЗМІНА: Використовуємо F.text замість Text
@dp.message(F.text == "😂 Рандомний Мем")
async def send_random_joke(message: types.Message):
    """Надсилає випадковий текст-жарт зі списку JOKES."""
    random_joke = random.choice(JOKES)
    
    await message.answer(
        f"😂 **Ваш рандомний мем \\(програмістський\\):**\n"
        f"_{escape_markdown(random_joke)}_",
        parse_mode="MarkdownV2"
    )

# ----------------------------------------------------------------------
#                           АДМІН-ПАНЕЛЬ та КАТАЛОГ
# ----------------------------------------------------------------------

@dp.message(Command("additem"))
async def cmd_add_item(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        # Додано відповідь для не-адмінів
        await message.answer("❌ У вас немає прав адміністратора для цієї команди.")
        return
    await state.set_state(AddItem.waiting_for_name)
    await message.answer(
        "**⚙️ Додавання нового товару \\(Крок 1/4\\)**\n"
        "Введіть **назву** товару:", 
        parse_mode="MarkdownV2"
    )

@dp.message(AddItem.waiting_for_name)
async def process_item_name(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("❌ Назва не може бути порожньою. Спробуйте ще раз.")
        return
        
    await state.update_data(name=message.text.strip())
    await message.answer(
        "**⚙️ Додавання нового товару \\(Крок 2/4\\)**\n"
        "Введіть **категорію** товару \\(наприклад, 'Зброя', 'Броня', 'Спорядження' \\- емодзі дозволені\\!\\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_category)

@dp.message(AddItem.waiting_for_category)
async def process_item_category(message: types.Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("❌ Категорія не може бути порожньою. Спробуйте ще раз.")
        return
        
    await state.update_data(category=message.text.strip())
    await message.answer(
        "**⚙️ Додавання нового товару \\(Крок 3/4\\)**\n"
        "Введіть **ціну** товару \\(ціле число\\):", 
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_price)

@dp.message(AddItem.waiting_for_price)
async def process_item_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Будь ласка, введіть коректну ціну (ціле число більше нуля).")
        return
    
    await state.update_data(price=price)
    await message.answer(
        "**⚙️ Додавання нового товару \\(Крок 4/4\\)**\n"
        "Введіть **опис** товару \\(або 'Ні', щоб пропустити\\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_description)

@dp.message(AddItem.waiting_for_description)
async def process_item_description(message: types.Message, state: FSMContext):
    """Зберігає опис і додає товар до БД"""
    data = await state.get_data()
    description = message.text.strip()
    
    if description.lower() == 'ні':
        description = None

    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        try:
            new_item = Item(
                name=data['name'],
                category=data['category'],
                price=data['price'],
                description=description,
                is_available=True,
                image_link=None 
            )
            session.add(new_item)
            await session.commit()
            
            await message.answer(
                f"✅ Товар **'{escape_markdown(data['name'])}'** успішно додано до каталогу\\!\n"
                f"Категорія: {escape_markdown(data['category'])}, Ціна: {data['price']}{escape_markdown(CURRENCY)}\\.",
                parse_mode="MarkdownV2",
                reply_markup=get_reply_keyboard(True)
            )
        except IntegrityError:
            await session.rollback()
            await message.answer("❌ Помилка: Товар з такою назвою вже існує\\. Спробуйте іншу назву\\.")
        except Exception as e:
            await session.rollback()
            logging.error(f"Помилка при додаванні товару: {e}")
            await message.answer("❌ Сталася невідома помилка при записі до бази даних\\. Спробуйте ще раз або зверніться до адміністратора\\.")
        finally:
            await state.clear()


async def show_categories(message: types.Message):
    """Показує всі унікальні категорії товарів (на основі Message)"""
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Item.category).distinct())
        categories = result.scalars().all()
    
    builder = InlineKeyboardBuilder()
    
    if not categories:
        # Додано обробку порожнього каталогу
        await message.answer(
            "Каталог поки що порожній\\! Зверніться до адміністратора, щоб додати товари\\.", 
            parse_mode="MarkdownV2",
            reply_markup=get_back_to_menu_inline()
        )
        return

    for cat in categories:
        builder.row(types.InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}"))
    
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    
    await message.answer("Оберіть категорію спорядження:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_items_by_category(callback: types.CallbackQuery):
    """Показує список товарів обраної категорії з кнопками 'Додати до кошика'"""
    
    category = callback.data.split("_")[1]
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        items_result = await session.execute(
            select(Item).filter_by(category=category, is_available=True)
        )
        items = items_result.scalars().all()

    if not items:
        await callback.answer("У цій категорії поки що немає доступних товарів\\.", show_alert=True)
        return

    text = f"**Категорія: {escape_markdown(category)}**\n\n"
    builder = InlineKeyboardBuilder()
    
    for item in items:
        item_name_escaped = escape_markdown(item.name)
        # item_desc_escaped = escape_markdown(item.description or 'Немає опису') # Видалено, щоб уникнути занадто довгого тексту для кнопки
        
        text += f"**{item_name_escaped}**\n"
        text += f"💰 Ціна: {item.price}{escape_markdown(CURRENCY)}\n"
        text += f"\\_Опис:\\_ {escape_markdown(item.description or 'Немає опису')}\n\n"
        
        builder.row(
            types.InlineKeyboardButton(
                text=f"➕ Додати {item_name_escaped}", 
                callback_data=f"add_{item.id}"
            )
        )
    
    builder.row(types.InlineKeyboardButton(text="🔙 До категорій", callback_data="show_catalog_callback"))
    
    await callback.message.edit_text(
        text, 
        reply_markup=builder.as_markup(), 
        parse_mode="MarkdownV2"
    )
    await callback.answer()

@dp.callback_query(F.data == "show_catalog_callback")
async def show_categories_callback(callback: types.CallbackQuery):
    await show_categories(callback.message)
    await callback.answer()

# ----------------------------------------------------------------------
#                             КОШИК та ОФОРМЛЕННЯ
# ----------------------------------------------------------------------

async def show_cart_message(message: types.Message):
    user_tg_id = message.from_user.id
    await _render_cart_content(user_tg_id, message.answer)

@dp.callback_query(F.data == "show_cart_callback")
async def show_cart_callback(callback: types.CallbackQuery):
    user_tg_id = callback.from_user.id
    await _render_cart_content(user_tg_id, callback.message.edit_text, callback.answer)


async def _render_cart_content(user_tg_id: int, send_or_edit_func, callback_answer=None):
    """Допоміжна функція для рендерингу вмісту кошика."""
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        cart_result = await session.execute(
            select(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item))
        )
        cart_items = cart_result.scalars().all()
    
    text = f"**🛍️ Ваш Кошик \\(Metro Shop\\):**\n\n" 
    builder = InlineKeyboardBuilder()
    total_price = 0
    
    if not cart_items:
        text += "Ваш кошик порожній\\. Час щось обрати\\! 🛒"
        builder.row(types.InlineKeyboardButton(text="↩️ До каталогу", callback_data="show_catalog_callback"))
        builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    else:
        for cart_item in cart_items:
            item = cart_item.item
            if item:
                item_subtotal = item.price * cart_item.quantity
                total_price += item_subtotal
                
                # Використовуємо лише один рядок для кожного товару
                text += f"\\*{escape_markdown(item.name)}\\* \\(x{cart_item.quantity}\\) \\- {item_subtotal}{escape_markdown(CURRENCY)}\n"
                
                builder.row(
                    types.InlineKeyboardButton(text="➖", callback_data=f"remove_one_{cart_item.id}"),
                    types.InlineKeyboardButton(text=f"x{cart_item.quantity}", callback_data="ignore"),
                    types.InlineKeyboardButton(text="➕", callback_data=f"add_one_{cart_item.id}"),
                    types.InlineKeyboardButton(text="❌", callback_data=f"delete_item_{cart_item.id}"),
                    width=4
                )
                
                text += "\\— \\— \\— \\— \\— \\— \n"

        text += f"\n**💸 Загальна сума: {total_price}{escape_markdown(CURRENCY)}**"
        
        builder.row(types.InlineKeyboardButton(text="✅ Оформити Замовлення", callback_data="checkout"))
        builder.row(types.InlineKeyboardButton(text="🗑️ Очистити Кошик", callback_data="clear_cart"))
        builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    
    # Перевірка: чи є це message.answer чи message.edit_text
    if send_or_edit_func.__name__ == 'answer':
         await send_or_edit_func(
            text, 
            reply_markup=builder.as_markup(), 
            parse_mode="MarkdownV2" 
        )
    else:
         await send_or_edit_func(
            text, 
            reply_markup=builder.as_markup(), 
            parse_mode="MarkdownV2" 
        )
    
    if callback_answer:
        await callback_answer()

@dp.callback_query(F.data.startswith("add_"))
async def add_item_to_cart(callback: types.CallbackQuery):
    """Обробляє додавання товару до кошика (з каталогу)."""
    try:
        item_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Помилка ідентифікатора товару\\.", show_alert=True)
        return

    user_tg_id = callback.from_user.id
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        item_result = await session.execute(select(Item).filter_by(id=item_id))
        item = item_result.scalars().first()
        
        if not item or not item.is_available:
            await callback.answer("❌ Товар не знайдено або він недоступний\\.", show_alert=True)
            return

        cart_result = await session.execute(select(CartItem).filter(
            CartItem.user_id == user_tg_id, 
            CartItem.item_id == item_id
        ))
        cart_item = cart_result.scalars().first()

        if cart_item:
            cart_item.quantity += 1
            message_text = f"➕ Додано ще одну одиницю {escape_markdown(item.name)}\\! Кількість: {cart_item.quantity}\\."
        else:
            new_cart_item = CartItem(
                user_id=user_tg_id,
                item_id=item_id,
                quantity=1
            )
            session.add(new_cart_item)
            message_text = f"✅ Товар {escape_markdown(item.name)} додано до кошика\\!"

        await session.commit()
    
    await callback.answer(message_text, show_alert=True)


@dp.callback_query(F.data.startswith("add_one_"))
async def add_one_item_in_cart(callback: types.CallbackQuery):
    """Обробляє кнопку ➕ у кошику."""
    cart_item_id = int(callback.data.split("_")[2])
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        cart_result = await session.execute(
            select(CartItem).filter_by(id=cart_item_id).options(selectinload(CartItem.item))
        )
        cart_item = cart_result.scalars().first()
        
        if cart_item:
            cart_item.quantity += 1
            await session.commit()
            item_name = escape_markdown(cart_item.item.name)
            
            await callback.answer(f"➕ Кількість {item_name} збільшено до {cart_item.quantity}\\.", show_alert=True)
            # Перерендер кошика
            await show_cart_callback(callback)
        else:
            await callback.answer("Помилка: Елемент кошика не знайдено\\.", show_alert=True)


@dp.callback_query(F.data.startswith("remove_one_") | F.data.startswith("delete_item_"))
async def remove_item_from_cart(callback: types.CallbackQuery):
    """Обробляє кнопки ➖ та ❌ у кошику."""
    # Правильне розділення: action - remove/delete, item_id
    action, _, cart_item_id_str = callback.data.rpartition('_')
    cart_item_id = int(cart_item_id_str)
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        # Використовуємо .filter_by(id=...) для більшої безпеки, ніж просто фільтр
        cart_result = await session.execute(
            select(CartItem).filter_by(id=cart_item_id).options(selectinload(CartItem.item))
        )
        cart_item = cart_result.scalars().first()
        
        if cart_item:
            item = cart_item.item
            item_name = escape_markdown(item.name) if item else "Товар"
            action_text = ""
            
            if action == "delete_item":
                await session.delete(cart_item)
                action_text = f"❌ {item_name} повністю видалено з кошика\\."
            
            elif action == "remove_one":
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                    action_text = f"➖ Кількість {item_name} зменшено до {cart_item.quantity}\\."
                else:
                    await session.delete(cart_item)
                    action_text = f"❌ {item_name} видалено з кошика\\."

            await session.commit()
            
            await callback.answer(action_text, show_alert=True)
            # Перерендер кошика
            await show_cart_callback(callback) 
        else:
            await callback.answer("Помилка: Елемент кошика не знайдено\\.", show_alert=True)


@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    user_tg_id = callback.from_user.id
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CartItem).filter(CartItem.user_id == user_tg_id))
        await session.commit()
    
    await callback.answer("🗑️ Ваш кошик повністю очищено\\!", show_alert=True)
    # Перерендер кошика
    await show_cart_callback(callback)

# ----------------------------------------------------------------------
#                         ЗВ'ЯЗОК З АДМІНОМ
# ----------------------------------------------------------------------

async def contact_admin_message(message: types.Message):
    admin_link = f"tg://user?id={ADMIN_ID}" 
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💬 Зв'язатися з Адміном", url=admin_link))
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    
    await message.answer(
        "З усіх питань, будь ласка, звертайтеся до нашого адміністратора\\. " 
        "Натисніть на кнопку, щоб розпочати чат:",
        reply_markup=builder.as_markup(),
        parse_mode="MarkdownV2"
    )

# ----------------------------------------------------------------------
#                         ОФОРМЛЕННЯ ЗАМОВЛЕННЯ
# ----------------------------------------------------------------------

@dp.callback_query(F.data == "checkout")
async def start_checkout(callback: types.CallbackQuery, state: FSMContext):
    user_tg_id = callback.from_user.id
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        cart_result = await session.execute(
            select(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item))
        )
        cart_items = cart_result.scalars().all()

    if not cart_items:
        await callback.answer("Кошик порожній\\! Додайте товари перед оформленням\\.", show_alert=True)
        return
    
    total_price = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items if cart_item.item)

    order_details = "\n\n**🛒 Товари:**\n"
    for cart_item in cart_items:
        item = cart_item.item
        if item:
            item_name_escaped = escape_markdown(item.name)
            order_details += f"  - {item_name_escaped} x{cart_item.quantity} \\({item.price * cart_item.quantity}{escape_markdown(CURRENCY)}\\)\n"
    
    final_text = (
        "**✅ ПІДТВЕРДЖЕННЯ ЗАМОВЛЕННЯ**\n"
        "Ваше замовлення буде надіслано адміністратору\\.\n\n"
        f"**💸 ЗАГАЛЬНА СУМА:** {total_price}{escape_markdown(CURRENCY)}"
        f"{order_details}"
        # ВИПРАВЛЕНО: Екранування @ у Telegram
        "\n**\\! ЗВ'ЯЗОК:** Адміністратор зв'яжеться з вами через Telegram \\(за вашим username\\)\\. Будь ласка, перевірте, що він відкритий\\."
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✔️ Підтвердити та Надіслати", callback_data="confirm_order"))
    builder.row(types.InlineKeyboardButton(text="❌ Скасувати та Головне меню", callback_data="main_menu_inline"))
    
    await callback.message.edit_text(
        final_text, 
        reply_markup=builder.as_markup(), 
        parse_mode="MarkdownV2"
    )
    await state.set_state(Checkout.waiting_for_confirmation)
    await callback.answer()

@dp.callback_query(F.data == "confirm_order", Checkout.waiting_for_confirmation)
async def confirm_order(callback: types.CallbackQuery, state: FSMContext):
    user_tg_id = callback.from_user.id
    username = callback.from_user.username or "Не вказано"
    
    # ЗМІНА: Асинхронна робота з БД
    async with AsyncSessionLocal() as session:
        cart_result = await session.execute(
            select(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item))
        )
        cart_items = cart_result.scalars().all()
        
        total_price = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items if cart_item.item)

        order_details = "\n\n**🛒 Товари:**\n"
        for cart_item in cart_items:
            item = cart_item.item
            if item:
                item_name_escaped = escape_markdown(item.name)
                order_details += f"  - {item_name_escaped} x{cart_item.quantity} \\({item.price * cart_item.quantity}{escape_markdown(CURRENCY)}\\)\n"
        
        # ВИПРАВЛЕНО: Екранування @ у f-рядку для Telegram
        admin_message = (
            f"🔔 **НОВЕ ЗАМОВЛЕННЯ\\!**\n"
            f"----------------------------\n"
            f"**🧑 Користувач:** \\@{escape_markdown(username)} \\(ID: {user_tg_id}\\)\n"
            f"**💸 СУМА:** {total_price}{escape_markdown(CURRENCY)}\n"
            f"{order_details}"
        )
        
        # 1. Надсилання повідомлення адміністратору
        await bot.send_message(ADMIN_ID, admin_message, parse_mode="MarkdownV2")

        # 2. Очищення кошика та стану
        await session.execute(delete(CartItem).filter(CartItem.user_id == user_tg_id))
        await session.commit()
    
    await state.clear()
    
    # 3. Повідомлення клієнту
    # ВИПРАВЛЕНО: Екранування @ у f-рядку для Telegram
    await callback.message.edit_text(
        r"🎉 **ЗАМОВЛЕННЯ ПРИЙНЯТО\\!**" + "\n" + 
        "Ваше замовлення успішно надіслано адміністратору\\. "
        f"Він зв'яжеться з вами через Telegram \\(\@?{escape_markdown(username)}\\) найближчим часом\\!\n\n"
        "Дякуємо, що обрали METRO SHOP\\!",
        parse_mode="MarkdownV2",
        reply_markup=get_back_to_menu_inline() 
    )
    await callback.answer("Замовлення підтверджено!")

# ----------------------------------------------------------------------
#                             СЕКЦІЯ ЗАПУСКУ
# ----------------------------------------------------------------------

async def main():
    # Створення таблиць ПЕРЕД запуском бота
    await create_db() 
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        print("🤖 Бот запущено...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот вимкнено")
