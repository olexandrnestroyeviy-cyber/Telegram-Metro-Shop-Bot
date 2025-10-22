# bot.py - ФІНАЛЬНА ВЕРСІЯ З УСІМА ВИПРАВЛЕННЯМИ
import asyncio
import logging
import re 
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

# Ваш файл db.py має бути поруч
from db import Session, Item, User, CartItem 

# --- КОНФІГУРАЦІЯ (ОБОВ'ЯЗКОВО ЗАМІНИТИ!) ---
# ⚠️ ПЕРЕВІРТЕ ТОКЕН! Якщо є конфлікт, замініть його на новий від @BotFather
TOKEN = "8203607429:AAHKBIUubmldST188Ejtcl5zpth2WVEKmsc" 
ADMIN_ID = 7249241490 # Ваш Telegram ID
CURRENCY = " грн" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
# ----------------------------------------------

# --- ДОПОМІЖНА ФУНКЦІЯ (ПОКРАЩЕНА ДЛЯ MARKDOWNV2) ---
def escape_markdown(text: str) -> str:
    """Екранує символи MarkdownV2, щоб вони не ламали текст з емодзі та спецсимволами."""
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

# --- СТВОРЕННЯ КНОПОК МЕНЮ ---
def get_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🛒 Каталог Товарів", callback_data="show_catalog"))
    builder.row(types.InlineKeyboardButton(text="🛍️ Мій Кошик", callback_data="show_cart"))
    builder.row(types.InlineKeyboardButton(text="⚙️ Зв'язок з Адміном", callback_data="contact_admin"))
    return builder.as_markup()

# --- ОБРОБНИКИ КОМАНД ---
@dp.message(Command("start", "menu"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    session = Session()
    user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
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
        reply_markup=get_main_menu_keyboard(),
        parse_mode="MarkdownV2"
    )

# ----------------------------------------------------------------------
#                         АДМІН-ПАНЕЛЬ (ДОДАВАННЯ ТОВАРУ)
# ----------------------------------------------------------------------

@dp.message(Command("additem"))
async def cmd_add_item(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас немає доступу до цієї команди\.")
        return

    await state.clear()
    await message.answer(
        "**⚙️ Додавання нового товару \(Крок 1/4\)**\n"
        "Введіть **повну назву** товару \(емодзі дозволені\!\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_name)

@dp.message(AddItem.waiting_for_name)
async def process_item_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    
    await message.answer(
        "**⚙️ Додавання нового товару \(Крок 2/4\)**\n"
        "Введіть **категорію** товару \(наприклад, 'Зброя', 'Броня', 'Спорядження' \- емодзі дозволені\!\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_category)

@dp.message(AddItem.waiting_for_category)
async def process_item_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    
    await message.answer(
        f"**⚙️ Додавання нового товару \(Крок 3/4\)**\n"
        f"Введіть **ціну** товару в {escape_markdown(CURRENCY.strip())} \(лише число, наприклад, 2500\):",
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
        await message.answer("❌ Будь ласка, введіть коректне числове значення ціни\.")
        return

    await state.update_data(price=price)
    
    await message.answer(
        "**⚙️ Додавання нового товару \(Крок 4/4\)**\n"
        "Введіть **короткий опис** товару \(емодзі дозволені\! або напишіть 'Ні'\):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AddItem.waiting_for_description)

@dp.message(AddItem.waiting_for_description)
async def process_item_description(message: types.Message, state: FSMContext):
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
            parse_mode="MarkdownV2"
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
        
# ----------------------------------------------------------------------
#                         ЗАГАЛЬНІ ОБРОБНИКИ ТА КОШИК
# ----------------------------------------------------------------------

@dp.callback_query(F.data == "main_menu")
async def go_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    """Повертає до головного меню та очищає стан FSM"""
    await state.clear() 
    await callback.message.edit_text(
        "Ви повернулися до головного меню\. Оберіть дію:", 
        reply_markup=get_main_menu_keyboard(),
        parse_mode="MarkdownV2"
    )
    await callback.answer()

@dp.callback_query(F.data == "show_catalog")
async def show_categories(callback: types.CallbackQuery):
    """Показує всі унікальні категорії товарів"""
    session = Session()
    categories = session.query(Item.category).distinct().all()
    session.close()
    
    builder = InlineKeyboardBuilder()
    
    for (cat,) in categories:
        builder.row(types.InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}"))
    
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu"))
    
    await callback.message.edit_text("Оберіть категорію спорядження:", reply_markup=builder.as_markup())
    await callback.answer()

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
    
    builder.row(types.InlineKeyboardButton(text="🔙 До категорій", callback_data="show_catalog"))
    
    await callback.message.edit_text(
        text, 
        reply_markup=builder.as_markup(), 
        parse_mode="MarkdownV2"
    )
    await callback.answer()

@dp.callback_query(F.data == "contact_admin")
async def contact_admin(callback: types.CallbackQuery):
    """Обробляє натискання на 'Зв'язок з Адміном'"""
    
    admin_link = f"tg://user?id={ADMIN_ID}" 
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💬 Зв'язатися з Адміном", url=admin_link))
    builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu"))
    
    await callback.message.edit_text(
        "З усіх питань, будь ласка, звертайтеся до нашого адміністратора\. " 
        "Натисніть на кнопку, щоб розпочати чат:",
        reply_markup=builder.as_markup(),
        parse_mode="MarkdownV2"
    )
    await callback.answer()

# ----------------------------------------------------------------------
# ⚠️ ДОДАНИЙ ОБРОБНИК ДЛЯ РОБОТИ КОШИКА (add_)
# ----------------------------------------------------------------------

@dp.callback_query(F.data.startswith("add_"))
async def add_item_to_cart(callback: types.CallbackQuery):
    """Обробляє додавання товару до кошика."""
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

    # Перевіряємо, чи є товар вже в кошику
    cart_item = session.query(CartItem).filter(
        CartItem.user_id == user_tg_id, 
        CartItem.item_id == item_id
    ).first()

    if cart_item:
        # Якщо товар є, збільшуємо кількість
        cart_item.quantity += 1
        session.commit()
        message_text = f"➕ Додано ще одну одиницю {escape_markdown(item.name)}\! Кількість: {cart_item.quantity}\."
    else:
        # Якщо товару немає, створюємо новий запис
        new_cart_item = CartItem(
            user_id=user_tg_id,
            item_id=item_id,
            quantity=1
        )
        session.add(new_cart_item)
        session.commit()
        message_text = f"✅ Товар {escape_markdown(item.name)} додано до кошика\!"

    session.close()
    
    await callback.answer(message_text, show_alert=True)

# ----------------------------------------------------------------------
#                 ФУНКЦІЇ КОШИКА (show_cart, remove, clear)
# ----------------------------------------------------------------------

@dp.callback_query(F.data == "show_cart")
async def show_cart(callback: types.CallbackQuery):
    user_tg_id = callback.from_user.id
    session = Session()
    
    cart_items = session.query(CartItem).filter(CartItem.user_id == user_tg_id).options(selectinload(CartItem.item)).all()
    session.close() 
    
    text = f"**🛍️ Ваш Кошик \(Metro Shop\):**\n\n" 
    builder = InlineKeyboardBuilder()
    total_price = 0
    
    if not cart_items:
        text += "Ваш кошик порожній\. Час щось обрати\! 🛒"
        builder.row(types.InlineKeyboardButton(text="↩️ До каталогу", callback_data="show_catalog"))
        builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu"))
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
                    types.InlineKeyboardButton(text="❌", callback_data=f"delete_item_{cart_item.id}"),
                    width=2
                )
                
                text += "\— \— \— \— \— \— \n"

        text += f"\n**💸 Загальна сума: {total_price}{escape_markdown(CURRENCY)}**"
        
        builder.row(types.InlineKeyboardButton(text="✅ Оформити Замовлення", callback_data="checkout"))
        builder.row(types.InlineKeyboardButton(text="🗑️ Очистити Кошик", callback_data="clear_cart"))
        builder.row(types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu"))
    
    await callback.message.edit_text(
        text, 
        reply_markup=builder.as_markup(), 
        parse_mode="MarkdownV2" 
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("remove_one_") | F.data.startswith("delete_item_"))
async def remove_item_from_cart(callback: types.CallbackQuery):
    action, cart_item_id = callback.data.split("_", 2)
    cart_item_id = int(cart_item_id)
    
    session = Session()
    cart_item = session.query(CartItem).filter_by(id=cart_item_id).options(selectinload(CartItem.item)).first()
    
    if cart_item:
        item = cart_item.item
        item_name = escape_markdown(item.name) if item else "Товар"
        
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
        # Викликаємо show_cart, щоб оновити вміст повідомлення
        await show_cart(callback)
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
    await show_cart(callback)


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
    builder.row(types.InlineKeyboardButton(text="❌ Скасувати та Головне меню", callback_data="main_menu"))
    
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
        f"**🧑 Користувач:** \@{escape_markdown(username)} \(ID: {user_tg_id}\)\n" 
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
        "🎉 **ЗАМОВЛЕННЯ ПРИЙНЯТО\!**\n"
        "Ваше замовлення успішно надіслано адміністратору\. "
        f"Він зв'яжеться з вами через Telegram \(\@**{escape_markdown(username)}**\) найближчим часом\!\n\n"
        "Дякуємо, що обрали METRO SHOP\!",
        parse_mode="MarkdownV2",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="↩️ Головне меню", callback_data="main_menu")]
            ]
        )
    )
    await callback.answer("Замовлення підтверджено!")


# ----------------------------------------------------------------------
#                             СЕКЦІЯ ЗАПУСКУ
# ----------------------------------------------------------------------

async def main():
    # Очищаємо всі старі вебхуки, щоб уникнути конфліктів із поллінгом
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        print("🤖 Бот запущено...")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот вимкнено")
