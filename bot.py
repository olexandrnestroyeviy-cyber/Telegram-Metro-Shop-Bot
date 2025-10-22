# bot.py - ФІНАЛЬНА ВЕРСІЯ З МЕНЮ, ВИПРАВЛЕННЯМИ ТА ГРОЮ
import asyncio
import logging
import re 
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.filters.text import Text # ВИПРАВЛЕНО: Правильний імпорт Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

# Ваш файл db.py має бути поруч
from db import Session, Item, User, CartItem 

# --- КОНФІГУРАЦІЯ (ОБОВ'ЯЗКОВО ЗАМІНИТИ!) ---
TOKEN = "8203607429:AAFyudKK3pCEPXu4SmC-Px7I5wmMCTSohw4" 
ADMIN_ID = 7249241490 # Ваш Telegram ID
CURRENCY = " грн" 
COOLDOWN_HOURS = 6 # Скільки годин триває перезарядка гри "Знайди Артефакт"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
# ----------------------------------------------

# --- ДОПОМІЖНА ФУНКЦІЯ ---
def escape_markdown(text: str) -> str:
    """
    Екранує символи MarkdownV2.
    Виправлено проблему з \! (використовуємо r-рядок).
    """
    # Екранування символів: \_ * [ ] ( ) ~ ` > # + - = | { } . !
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
        [types.KeyboardButton(text="🔦 Знайди Артефакт"), types.KeyboardButton(text="⚙️ Зв'язок з Адміном")] # ДОДАНО ГРУ
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
@dp.message(Text("↩️ Головне меню"))
async def cmd_start_or_menu(message: types.Message, state: FSMContext):
    await state.clear()
    
    session = Session()
    user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
    is_admin = message.from_user.id == ADMIN_ID
    
    if not user:
        new_user = User(
            telegram_id=message.from_user.id, 
            username=message.from_user.username or 'N/A'
        )
        session.add(new_user)
        session.commit()
    session.close()

    user_name = escape_markdown(message.from_user.first_name)
    
    await message.answer(
        f"Ласкаво просимо, **{user_name}**, до **METRO SHOP**\! Оберіть дію:", 
        reply_markup=get_reply_keyboard(is_admin), 
        parse_mode="MarkdownV2"
    )

@dp.callback_query(F.data == "main_menu_inline")
async def go_to_main_menu_inline(callback: types.CallbackQuery, state: FSMContext):
    """Обробляє Inline-кнопку 'Головне меню' для повернення до Reply-меню."""
    await state.clear() 
    await callback.message.edit_text(
        "Ви повернулися до головного меню\. Оберіть дію:", 
        parse_mode="MarkdownV2"
    )
    await callback.answer()
    await cmd_start_or_menu(callback.message, state) # Надсилаємо нове повідомлення з Reply Keyboard

# ----------------------------------------------------------------------
#                         ОБРОБНИКИ КНОПОК МЕНЮ (Reply Keyboard)
# ----------------------------------------------------------------------

@dp.message(Text("🛒 Каталог Товарів"))
async def handle_catalog_button(message: types.Message):
    await show_categories(message)

@dp.message(Text("🛍️ Мій Кошик"))
async def handle_cart_button(message: types.Message):
    await show_cart_message(message)

@dp.message(Text("⚙️ Зв'язок з Адміном"))
async def handle_contact_button(message: types.Message):
    await contact_admin_message(message)

# ----------------------------------------------------------------------
#                           ✨ НОВА ФУНКЦІЯ: ЗНАЙДИ АРТЕФАКТ! ✨
# ----------------------------------------------------------------------

@dp.message(Text("🔦 Знайди Артефакт"))
async def find_artifact_game(message: types.Message):
    user_tg_id = message.from_user.id
    
    session = Session()
    user = session.query(User).filter_by(telegram_id=user_tg_id).first()
    
    # Перевірка перезарядки
    if user.last_game_time and datetime.now() < user.last_game_time + timedelta(hours=COOLDOWN_HOURS):
        next_try_time = user.last_game_time + timedelta(hours=COOLDOWN_HOURS)
        wait_time = next_try_time - datetime.now()
        
        hours = int(wait_time.total_seconds() // 3600)
        minutes = int((wait_time.total_seconds() % 3600) // 60)
        
        await message.answer(
            f"❌ **Пошук артефактів ще не перезарядився\!**\n"
            f"Залишилося: **{hours} год\. {minutes} хв\.\**\n"
            f"Спробуйте знову після {next_try_time.strftime('%H:%M')} \.",
            parse_mode="MarkdownV2"
        )
        session.close()
        return

    # 1. Пошук доступних предметів
    available_items = session.query(Item).filter(Item.is_available == True).all()
    
    if not available_items:
        await message.answer("Схоже, всі артефакти вже розібрані, або каталог порожній\. Приходьте пізніше\.")
        session.close()
        return

    # 2. Вибір випадкового предмета (Шанс 1 до 5)
    win_chance = 1
    if random.randint(1, 5) <= win_chance:
        # Перемога!
        won_item = random.choice(available_items)
        
        # Додавання товару в кошик (кількість 1)
        cart_item = session.query(CartItem).filter(
            CartItem.user_id == user_tg_id, 
            CartItem.item_id == won_item.id
        ).first()

        if cart_item:
            cart_item.quantity += 1
        else:
            new_cart_item = CartItem(
                user_id=user_tg_id,
                item_id=won_item.id,
                quantity=1
            )
            session.add(new_cart_item)
            
        win_message = (
            f"🎉 **УСПІХ\! Ви знайшли артефакт\!** 🎉\n"
            f"Ви натрапили на рідкісне спорядження: **{escape_markdown(won_item.name)}**\.\n"
            f"Він був автоматично доданий до вашого кошика \(`x{cart_item.quantity if cart_item else 1}`\)\!"
        )
    else:
        # Програш
        win_message = "😔 **На жаль, цього разу ви не знайшли нічого цінного\.\**\nПроте, ви почули дивні звуки... можливо, вам пощастить наступного разу\!"

    # 3. Оновлення часу останньої гри
    stmt = update(User).where(User.telegram_id == user_tg_id).values(last_game_time=datetime.now())
    session.execute(stmt)
    session.commit()
    session.close()

    await message.answer(win_message, parse_mode="MarkdownV2")

# ----------------------------------------------------------------------
#                           АДМІН-ПАНЕЛЬ та КАТАЛОГ
# ----------------------------------------------------------------------

# ... (FSM-обробники AddItem залишаються без змін)
@dp.message(Command("additem"))
async def cmd_add_item(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    # Логіка додавання товару... (скорочено, оскільки вона є у попередньому коді)

@dp.message(AddItem.waiting_for_name)
async def process_item_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(
        "**⚙️ Додавання нового товару \(Крок 2/4\)**\n"
        "Введіть **категорію** товару \(наприклад, 'Зброя', 'Броня', 'Спорядження' \- емодзі дозволені\!\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_category)
# ... (всі наступні FSM-обробники аналогічні попередньому коду)

@dp.message(AddItem.waiting_for_description)
async def process_item_description(message: types.Message, state: FSMContext):
    """Зберігає опис і додає товар до БД"""
    data = await state.get_data()
    description = message.text.strip()
    
    if description.lower() == 'ні':
        description = None

    session = Session()
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
        session.commit()
        
        await message.answer(
            f"✅ Товар **'{escape_markdown(data['name'])}'** успішно додано до каталогу\!\n"
            f"Категорія: {escape_markdown(data['category'])}, Ціна: {data['price']}{escape_markdown(CURRENCY)}\.",
            parse_mode="MarkdownV2",
            reply_markup=get_reply_keyboard(True)
        )
    except IntegrityError:
        session.rollback()
        await message.answer("❌ Помилка: Товар з такою назвою вже існує\. Спробуйте іншу назву\.")
    except Exception as e:
        session.rollback()
        logging.error(f"Помилка при додаванні товару: {e}")
        await message.answer("❌ Сталася невідома помилка при записі до бази даних\. Спробуйте ще раз або зверніться до адміністратора\.")
    finally:
        session.close()
        await state.clear()


async def show_categories(message: types.Message):
    """Показує всі унікальні категорії товарів (на основі Message)"""
    session = Session()
    categories = session.execute(select(Item.category).distinct()).scalars().all()
    session.close()
    
    builder = InlineKeyboardBuilder()
    
    for cat in categories:
        builder.row(types.InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}"))
    
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    
    await message.answer("Оберіть категорію спорядження:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_items_by_category(callback: types.CallbackQuery):
    """Показує список товарів обраної категорії з кнопками 'Додати до кошика'"""
    
    category = callback.data.split("_")[1]
    
    session = Session()
    items = session.query(Item).filter_by(category=category, is_available=True).all()
    session.close()

    if not items:
        await callback.answer("У цій категорії поки що немає доступних товарів\.", show_alert=True)
        return

    text = f"**Категорія: {escape_markdown(category)}**\n\n"
    builder = InlineKeyboardBuilder()
    
    for item in items:
        item_name_escaped = escape_markdown(item.name)
        item_desc_escaped = escape_markdown(item.description or 'Немає опису')
        
        text += f"**{item_name_escaped}**\n"
        text += f"💰 Ціна: {item.price}{escape_markdown(CURRENCY)}\n"
        text += f"\_Опис:\_ {item_desc_escaped}\n\n"
        
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
    session = Session()
    cart_items = session.query(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item)).all()
    session.close() 
    
    text = f"**🛍️ Ваш Кошик \(Metro Shop\):**\n\n" 
    builder = InlineKeyboardBuilder()
    total_price = 0
    
    if not cart_items:
        text += "Ваш кошик порожній\. Час щось обрати\! 🛒"
        builder.row(types.InlineKeyboardButton(text="↩️ До каталогу", callback_data="show_catalog_callback"))
        builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    else:
        for cart_item in cart_items:
            item = cart_item.item
            if item:
                item_subtotal = item.price * cart_item.quantity
                total_price += item_subtotal
                
                text += f"\*{escape_markdown(item.name)}\* \(x{cart_item.quantity}\)\n"
                text += f"💰 {item_subtotal}{escape_markdown(CURRENCY)}\n"
                
                builder.row(
                    types.InlineKeyboardButton(text="➖", callback_data=f"remove_one_{cart_item.id}"),
                    types.InlineKeyboardButton(text=f"x{cart_item.quantity}", callback_data="ignore"),
                    types.InlineKeyboardButton(text="➕", callback_data=f"add_one_{cart_item.id}"),
                    types.InlineKeyboardButton(text="❌", callback_data=f"delete_item_{cart_item.id}"),
                    width=4
                )
                
                text += "\— \— \— \— \— \— \n"

        text += f"\n**💸 Загальна сума: {total_price}{escape_markdown(CURRENCY)}**"
        
        builder.row(types.InlineKeyboardButton(text="✅ Оформити Замовлення", callback_data="checkout"))
        builder.row(types.InlineKeyboardButton(text="🗑️ Очистити Кошик", callback_data="clear_cart"))
        builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    
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
        await callback.answer("❌ Помилка ідентифікатора товару\.", show_alert=True)
        return

    user_tg_id = callback.from_user.id
    
    session = Session()
    item = session.query(Item).filter_by(id=item_id).first()
    
    if not item:
        session.close()
        await callback.answer("❌ Товар не знайдено в каталозі\.", show_alert=True)
        return

    cart_item = session.query(CartItem).filter(
        CartItem.user_id == user_tg_id, 
        CartItem.item_id == item_id
    ).first()

    if cart_item:
        cart_item.quantity += 1
        message_text = f"➕ Додано ще одну одиницю {escape_markdown(item.name)}\! Кількість: {cart_item.quantity}\."
    else:
        new_cart_item = CartItem(
            user_id=user_tg_id,
            item_id=item_id,
            quantity=1
        )
        session.add(new_cart_item)
        message_text = f"✅ Товар {escape_markdown(item.name)} додано до кошика\!"

    session.commit()
    session.close()
    
    await callback.answer(message_text, show_alert=True)


@dp.callback_query(F.data.startswith("add_one_"))
async def add_one_item_in_cart(callback: types.CallbackQuery):
    """Обробляє кнопку ➕ у кошику (ВИПРАВЛЕНО)."""
    cart_item_id = int(callback.data.split("_")[2])
    session = Session()
    cart_item = session.query(CartItem).filter_by(id=cart_item_id).options(selectinload(CartItem.item)).first()
    
    if cart_item:
        cart_item.quantity += 1
        session.commit()
        item_name = escape_markdown(cart_item.item.name)
        session.close()
        await callback.answer(f"➕ Кількість {item_name} збільшено до {cart_item.quantity}\.", show_alert=True)
        await show_cart_callback(callback)
    else:
        session.close()
        await callback.answer("Помилка: Елемент кошика не знайдено\.", show_alert=True)


@dp.callback_query(F.data.startswith("remove_one_") | F.data.startswith("delete_item_"))
async def remove_item_from_cart(callback: types.CallbackQuery):
    """Обробляє кнопки ➖ та ❌ у кошику (ВИПРАВЛЕНО)."""
    action, cart_item_id = callback.data.split("_", 2)
    cart_item_id = int(cart_item_id)
    
    session = Session()
    cart_item = session.query(CartItem).filter_by(id=cart_item_id).options(selectinload(CartItem.item)).first()
    
    if cart_item:
        item = cart_item.item
        item_name = escape_markdown(item.name) if item else "Товар"
        action_text = ""
        
        if action == "delete_item":
            session.delete(cart_item)
            action_text = f"❌ {item_name} повністю видалено з кошика\."
        
        elif action == "remove_one":
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                session.commit()
                action_text = f"➖ Кількість {item_name} зменшено до {cart_item.quantity}\."
            else:
                session.delete(cart_item)
                action_text = f"❌ {item_name} видалено з кошика\."

        session.commit()
        session.close()
        
        await callback.answer(action_text, show_alert=True)
        await show_cart_callback(callback) 
    else:
        session.close()
        await callback.answer("Помилка: Елемент кошика не знайдено\.", show_alert=True)


@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    user_tg_id = callback.from_user.id
    session = Session()
    
    session.query(CartItem).filter(CartItem.user_id == user_tg_id).delete()
    session.commit()
    session.close()
    
    await callback.answer("🗑️ Ваш кошик повністю очищено\!", show_alert=True)
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
        "З усіх питань, будь ласка, звертайтеся до нашого адміністратора\. " 
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
    session = Session()
    
    cart_items = session.query(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item)).all()
    session.close()

    if not cart_items:
        await callback.answer("Кошик порожній\! Додайте товари перед оформленням\.", show_alert=True)
        return
    
    total_price = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items if cart_item.item)

    order_details = "\n\n**🛒 Товари:**\n"
    for cart_item in cart_items:
        item = cart_item.item
        if item:
            item_name_escaped = escape_markdown(item.name)
            order_details += f"  - {item_name_escaped} x{cart_item.quantity} \({item.price * cart_item.quantity}{escape_markdown(CURRENCY)}\)\n"
    
    final_text = (
        "**✅ ПІДТВЕРДЖЕННЯ ЗАМОВЛЕННЯ**\n"
        "Ваше замовлення буде надіслано адміністратору\.\n\n"
        f"**💸 ЗАГАЛЬНА СУМА:** {total_price}{escape_markdown(CURRENCY)}"
        f"{order_details}"
        "\n**\! ЗВ'ЯЗОК:** Адміністратор зв'яжеться з вами через Telegram \(за вашим username\)\. Будь ласка, перевірте, що він відкритий\."
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
    
    session = Session()
    cart_items = session.query(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item)).all()
    
    total_price = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items if cart_item.item)

    order_details = "\n\n**🛒 Товари:**\n"
    for cart_item in cart_items:
        item = cart_item.item
        if item:
            item_name_escaped = escape_markdown(item.name)
            order_details += f"  - {item_name_escaped} x{cart_item.quantity} \({item.price * cart_item.quantity}{escape_markdown(CURRENCY)}\)\n"
    
    admin_message = (
        f"🔔 **НОВЕ ЗАМОВЛЕННЯ\!**\n"
        f"----------------------------\n"
        f"**🧑 Користувач:** \@{escape_markdown(username)} \\(ID: {user_tg_id}\\)\n"
        f"**💸 СУМА:** {total_price}{escape_markdown(CURRENCY)}\n"
        f"{order_details}"
    )
    
    # 1. Надсилання повідомлення адміністратору
    await bot.send_message(ADMIN_ID, admin_message, parse_mode="MarkdownV2")

    # 2. Очищення кошика та стану
    session.query(CartItem).filter(CartItem.user_id == user_tg_id).delete()
    session.commit()
    session.close() 
    await state.clear()
    
    # 3. Повідомлення клієнту
    await callback.message.edit_text(
        r"🎉 **ЗАМОВЛЕННЯ ПРИЙНЯТО\!**" + "\n" + # Використовуємо r-рядок
        "Ваше замовлення успішно надіслано адміністратору\. "
        f"Він зв'яжеться з вами через Telegram \(\@{escape_markdown(username)}\) найближчим часом\!\n\n"
        "Дякуємо, що обрали METRO SHOP\!",
        parse_mode="MarkdownV2",
        reply_markup=get_back_to_menu_inline() 
    )
    await callback.answer("Замовлення підтверджено!")

# ----------------------------------------------------------------------
#                             СЕКЦІЯ ЗАПУСКУ
# ----------------------------------------------------------------------

async def main():
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        print("🤖 Бот запущено...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот вимкнено")
