# bot.py - ФІНАЛЬНА ВЕРСІЯ V3 (З МЕНЮ І ВИПРАВЛЕННЯМИ)
import asyncio
import logging
import re 
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

# Ваш файл db.py має бути поруч
from db import Session, Item, User, CartItem 

# --- КОНФІГУРАЦІЯ (ОБОВ'ЯЗКОВО ЗАМІНИТИ!) ---
TOKEN = "8259784737:AAGki5LfnaxHfMppMiN8M4Niw8HPeOOSAS4" 
ADMIN_ID = 7249241490 # Ваш Telegram ID
CURRENCY = " грн" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
# ----------------------------------------------

# --- ДОПОМІЖНА ФУНКЦІЯ ---
def escape_markdown(text: str) -> str:
    """Екранує символи MarkdownV2, щоб вони не ламали текст з емодзі та спецсимволами."""
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
        [types.KeyboardButton(text="⚙️ Зв'язок з Адміном")]
    ]
    if is_admin:
        # Додаємо команду адміна, видиму тільки йому
        kb.append([types.KeyboardButton(text="/additem")])
    
    return types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        selective=True # Показує клавіатуру лише користувачеві, якому вона була надіслана
    )

def get_back_to_menu_inline():
    """Створює Inline-кнопку для повернення в Головне меню (для використання в Inline-меню)."""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu_inline"))
    return builder.as_markup()

# --- ОБРОБНИКИ КОМАНД ТА REPLY-МЕНЮ ---

@dp.message(Command("start", "menu"))
@dp.message(Text("↩️ Головне меню"))
async def cmd_start_or_menu(message: types.Message, state: FSMContext):
    """Обробляє /start, /menu та натискання кнопки '↩️ Головне меню'."""
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
        reply_markup=get_reply_keyboard(is_admin), # Використовуємо Reply Keyboard
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
    # Відповідь на колбек, щоб зник годинник
    await callback.answer()
    # Надсилаємо нове повідомлення, щоб показати Reply Keyboard
    await cmd_start_or_menu(callback.message, state)


# ----------------------------------------------------------------------
#                         ОБРОБНИКИ КНОПОК МЕНЮ (Reply Keyboard)
# ----------------------------------------------------------------------

@dp.message(Text("🛒 Каталог Товарів"))
async def handle_catalog_button(message: types.Message):
    """Показує категорії при натисканні на кнопку Каталог."""
    await show_categories(message)

@dp.message(Text("🛍️ Мій Кошик"))
async def handle_cart_button(message: types.Message):
    """Показує кошик при натисканні на кнопку Кошик."""
    await show_cart_message(message)

@dp.message(Text("⚙️ Зв'язок з Адміном"))
async def handle_contact_button(message: types.Message):
    """Показує контакт з адміном при натисканні на кнопку."""
    await contact_admin_message(message)

# ----------------------------------------------------------------------
#                   ЛОГІКА КАТАЛОГУ, КОШИКА ТА АДМІНА (Викликається з Message та Callback)
# ----------------------------------------------------------------------

@dp.message(Command("additem"))
async def cmd_add_item(message: types.Message, state: FSMContext):
    """Починає процес додавання нового товару (тільки для адміна)"""
    if message.from_user.id != ADMIN_ID:
        # Для не-адмінів, якщо вони випадково введуть /additem, відповіді не буде.
        # Можна додати: await message.answer("У вас немає доступу до цієї команди.")
        return

    # Логіка додавання товару... (Залишається без змін)
    await state.clear()
    await message.answer(
        "**⚙️ Додавання нового товару \(Крок 1/4\)**\n"
        "Введіть **повну назву** товару \(емодзі дозволені\!\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_name)

# ... (AddItem.waiting_for_name, waiting_for_category, waiting_for_price, waiting_for_description залишаються без змін)
# Ми припускаємо, що ці FSM-обробники вже є у вашому файлі.
# Вони працюють з message, тому не потребують змін.

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
        
        # Виводимо підтвердження та повертаємо Reply-меню
        await message.answer(
            f"✅ Товар **'{escape_markdown(data['name'])}'** успішно додано до каталогу\!\n"
            f"Категорія: {escape_markdown(data['category'])}, Ціна: {data['price']}{escape_markdown(CURRENCY)}\.",
            parse_mode="MarkdownV2",
            reply_markup=get_reply_keyboard(True) # Адмін отримує клавіатуру з /additem
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

# --- КАТАЛОГ (Category handlers) ---

async def show_categories(message: types.Message):
    """Показує всі унікальні категорії товарів (на основі Message)"""
    session = Session()
    # Використовуємо select для більш сучасного підходу
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
    """Обробляє повернення з каталогу на категорії (Inline)."""
    # Ми викликаємо show_categories, але передаємо message від колбеку для edit_text
    await show_categories(callback.message)
    await callback.answer()


# --- КОШИК (Cart handlers) ---

async def show_cart_message(message: types.Message):
    """Показує вміст кошика користувача (на основі Message)"""
    user_tg_id = message.from_user.id
    await _render_cart_content(user_tg_id, message.answer)

@dp.callback_query(F.data == "show_cart_callback")
async def show_cart_callback(callback: types.CallbackQuery):
    """Показує вміст кошика користувача (на основі Callback)"""
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
                
                # ВИПРАВЛЕНО: Кнопки додавання/видалення кількості
                builder.row(
                    types.InlineKeyboardButton(text="➖", callback_data=f"remove_one_{cart_item.id}"),
                    types.InlineKeyboardButton(text=f"x{cart_item.quantity}", callback_data="ignore"), # Інформаційна кнопка
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
        await show_cart_callback(callback) # Оновлюємо кошик
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
        # Викликаємо show_cart_callback, щоб оновити вміст повідомлення
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


# --- ЗВ'ЯЗОК З АДМІНОМ ---
async def contact_admin_message(message: types.Message):
    """Показує контакт з адміном (на основі Message)"""
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

# --- ОФОРМЛЕННЯ ЗАМОВЛЕННЯ (Checkout handlers) ---

@dp.callback_query(F.data == "checkout")
async def start_checkout(callback: types.CallbackQuery, state: FSMContext):
    """Починає процес оформлення замовлення (ВИПРАВЛЕНО)."""
    user_tg_id = callback.from_user.id
    session = Session()
    
    cart_items = session.query(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item)).all()
    session.close()

    if not cart_items:
        await callback.answer("Кошик порожній\! Додайте товари перед оформленням\.", show_alert=True)
        return
    
    total_price = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items if cart_item.item)

    # ... (формування тексту замовлення без змін)
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
    # ... (кінець формування тексту)

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
    """Фіналізує замовлення, надсилає його адміністратору і очищає кошик (ВИПРАВЛЕНО)."""
    user_tg_id = callback.from_user.id
    username = callback.from_user.username or "Не вказано"
    
    session = Session()
    cart_items = session.query(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item)).all()
    
    total_price = sum(cart_item.item.price * cart_item.quantity for cart_item in cart_items if cart_item.item)

    # ... (формування повідомлення для адміна без змін)
    order_details = "\n\n**🛒 Товари:**\n"
    for cart_item in cart_items:
        item = cart_item.item
        if item:
            item_name_escaped = escape_markdown(item.name)
            order_details += f"  - {item_name_escaped} x{cart_item.quantity} \({item.price * cart_item.quantity}{escape_markdown(CURRENCY)}\)\n"
    
    admin_message = (
        f"🔔 **НОВЕ ЗАМОВЛЕННЯ\!**\n"
        f"----------------------------\n"
        f"**🧑 Користувач:** \@{escape_markdown(username)} \(ID: {user_tg_id}\)\n" 
        f"**💸 СУМА:** {total_price}{escape_markdown(CURRENCY)}\n"
        f"{order_details}"
    )
    # ... (кінець формування повідомлення)
    
    # 1. Надсилання повідомлення адміністратору
    await bot.send_message(ADMIN_ID, admin_message, parse_mode="MarkdownV2")

    # 2. Очищення кошика та стану
    session.query(CartItem).filter(CartItem.user_id == user_tg_id).delete()
    session.commit()
    session.close() 
    await state.clear()
    
    # 3. Повідомлення клієнту
    await callback.message.edit_text(
        "🎉 **ЗАМОВЛЕННЯ ПРИЙНЯТО\!**\n"
        "Ваше замовлення успішно надіслано адміністратору\. "
        f"Він зв'яжеться з вами через Telegram \(\@**{escape_markdown(username)}**\) найближчим часом\!\n\n"
        "Дякуємо, що обрали METRO SHOP\!",
        parse_mode="MarkdownV2",
        reply_markup=get_back_to_menu_inline() # Повертаємо Inline-кнопку для переходу до Reply-меню
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

