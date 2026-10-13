from datetime import datetime, timedelta
import logging
import csv
from io import StringIO
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from config import settings
from database.db import SessionLocal
from database.models import Category, Order, Product, User
from keyboards import BACK_MENU
from states import BotStates

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer(
        "Admin paneli. Mahsulot va bonus boshqaruvi: /addproduct, /bonus, /ban ID, /unban ID.",
        reply_markup=_admin_keyboard(),
    )


def _admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Faollik va statistika", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🔍 Foydalanuvchini qidirish", callback_data="admin:search")],
        [InlineKeyboardButton(text="📢 Barchaga e'lon", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📥 Foydalanuvchilar CSV", callback_data="admin:export")],
    ])


@router.callback_query(F.data == "admin:stats")
async def stats_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    await callback.message.answer(await _stats_text())
    await callback.answer()


async def _stats_text() -> str:
    now = datetime.utcnow()
    tashkent_today = datetime.now(ZoneInfo("Asia/Tashkent")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_start_utc = tashkent_today.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    async with SessionLocal() as session:
        users = await session.scalar(select(func.count(User.id))) or 0
        new_day = await session.scalar(
            select(func.count(User.id)).where(User.created_at >= now - timedelta(days=1))
        ) or 0
        new_week = await session.scalar(
            select(func.count(User.id)).where(User.created_at >= now - timedelta(days=7))
        ) or 0
        active_today = await session.scalar(
            select(func.count(User.id)).where(User.last_active_at >= today_start_utc)
        ) or 0
        blocked = await session.scalar(
            select(func.count(User.id)).where(User.is_banned.is_(True))
        ) or 0
        orders = await session.scalar(select(func.count(Order.id))) or 0
        pending = await session.scalar(select(func.count(Order.id)).where(Order.status == "review")) or 0
    return (
        "📊 Bot statistikasi\n"
        f"Jami foydalanuvchilar: {users}\n"
        f"So‘nggi 24 soatda qo‘shilgan: {new_day}\n"
        f"So‘nggi 7 kunda qo‘shilgan: {new_week}\n"
        f"Bugun faol foydalanuvchilar: {active_today}\n"
        f"Bloklangan foydalanuvchilar: {blocked}\n"
        f"Buyurtmalar: {orders}\n"
        f"Tekshirilayotgan cheklar: {pending}"
    )


@router.callback_query(F.data == "admin:search")
async def user_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    await state.set_state(BotStates.admin_search)
    await callback.message.answer("Noyob ID, Telegram ID yoki @username yuboring:")
    await callback.answer()


@router.message(BotStates.admin_search, F.text)
async def user_search(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    query = (message.text or "").strip()
    async with SessionLocal() as session:
        user = None
        username = query.lstrip("@").casefold()
        if username.isdigit():
            numeric_id = int(username)
            user = await session.scalar(select(User).where(User.public_id == numeric_id))
            if user is None:
                user = await session.scalar(select(User).where(User.id == numeric_id))
        elif username:
            user = await session.scalar(
                select(User).where(func.lower(User.username) == username)
            )
        if user is None:
            await message.answer("Foydalanuvchi topilmadi. Qayta kiriting:")
            return
        card = _user_card(user)
        markup = _user_keyboard(user)
    await state.clear()
    await message.answer(card, reply_markup=markup)


def _user_card(user: User) -> str:
    username = f"@{user.username}" if user.username else "yo‘q"
    status = "Bloklangan" if user.is_banned else "Faol"
    return (
        "👤 Foydalanuvchi kartochkasi\n"
        f"Noyob ID: {user.public_id or '—'}\n"
        f"Telegram ID: {user.telegram_id or user.id}\n"
        f"Username: {username}\n"
        f"Ism: {user.full_name or '—'}\n"
        f"Qo‘shilgan: {user.created_at:%Y-%m-%d %H:%M} UTC\n"
        f"Oxirgi faolligi: {user.last_active_at:%Y-%m-%d %H:%M} UTC\n"
        f"Status: {status}"
    )


def _user_keyboard(user: User) -> InlineKeyboardMarkup:
    toggle_text = "✅ Blokdan chiqarish" if user.is_banned else "🚫 Bloklash"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:user:toggle:{user.id}")],
        [InlineKeyboardButton(text="✉️ Shaxsiy xabar yuborish", callback_data=f"admin:user:message:{user.id}")],
        [InlineKeyboardButton(text="📢 Shaxsiy reklama yuborish", callback_data=f"admin:user:ad:{user.id}")],
    ])


@router.callback_query(F.data.startswith("admin:user:"))
async def manage_user(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        _, _, action, raw_user_id = callback.data.split(":", maxsplit=3)
        user_id = int(raw_user_id)
    except (ValueError, AttributeError):
        await callback.answer("So‘rov noto‘g‘ri.", show_alert=True)
        return
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return
        if action == "toggle":
            user.is_banned = not user.is_banned
            await session.commit()
            card, markup = _user_card(user), _user_keyboard(user)
        elif action in {"message", "ad"}:
            card = ""
            markup = None
        else:
            await callback.answer("Noma'lum amal.", show_alert=True)
            return
    if action == "toggle":
        await callback.message.edit_text(card, reply_markup=markup)
        await callback.answer("Foydalanuvchi holati yangilandi.")
        return
    await state.update_data(direct_target_id=user_id)
    await state.set_state(
        BotStates.admin_user_ad if action == "ad" else BotStates.admin_user_message
    )
    prompt = "Shaxsiy reklama matni yoki mediasini yuboring:" if action == "ad" else "Shaxsiy xabar matni yoki mediasini yuboring:"
    await callback.message.answer(prompt)
    await callback.answer()


def _spreadsheet_safe(value: str) -> str:
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@router.callback_query(F.data == "admin:export")
async def export_users(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).order_by(User.public_id))).all()
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([
            "unique_id", "telegram_id", "username", "full_name",
            "joined_at_utc", "last_activity_utc", "is_blocked",
        ])
        for user in users:
            writer.writerow([
                user.public_id,
                user.telegram_id or user.id,
                _spreadsheet_safe(user.username or ""),
                _spreadsheet_safe(user.full_name or ""),
                user.created_at.isoformat() if user.created_at else "",
                user.last_active_at.isoformat() if user.last_active_at else "",
                user.is_banned,
            ])
    document = BufferedInputFile(
        output.getvalue().encode("utf-8-sig"),
        filename="users.csv",
    )
    await callback.message.answer_document(document, caption="Foydalanuvchilar ro‘yxati (CSV).")
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast")
async def broadcast_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    await state.set_state(BotStates.broadcast)
    await callback.message.answer("Tarqatiladigan xabarni yuboring:")
    await callback.answer()


@router.message(Command("stats"))
async def stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await message.answer(await _stats_text())


@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(BotStates.broadcast)
    await message.answer("Tarqatiladigan matnni yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.broadcast)
async def broadcast(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    await state.update_data(broadcast_message_id=message.message_id, broadcast_chat_id=message.chat.id)
    await state.set_state(BotStates.broadcast_button)
    await message.answer("Ixtiyoriy inline tugma yuboring: Tugma matni | https://havola. Tugmasiz — /skip.")


@router.message(BotStates.broadcast_button, F.text)
async def broadcast_button(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    markup = None
    if (message.text or "").strip() != "/skip":
        parts = (message.text or "").split("|", maxsplit=1)
        if len(parts) != 2 or not parts[0].strip() or len(parts[0].strip()) > 64:
            await message.answer("Format: Tugma matni | https://havola yoki /skip.")
            return
        url = parts[1].strip()
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            await message.answer("Tugma havolasi https:// bilan boshlanishi kerak.")
            return
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=parts[0].strip(), url=url)
        ]])
    data = await state.get_data()
    async with SessionLocal() as session:
        user_ids = (await session.scalars(select(User.id).where(User.is_banned.is_(False)))).all()
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await message.bot.copy_message(
                chat_id=user_id,
                from_chat_id=data["broadcast_chat_id"],
                message_id=data["broadcast_message_id"],
                reply_markup=markup,
            )
            sent += 1
        except TelegramAPIError:
            logger.exception("Broadcast delivery failed for user_id=%s", user_id)
            failed += 1
    await state.clear()
    await message.answer(f"Tarqatish yakunlandi. Yuborildi: {sent}, xato: {failed}.")


@router.message(Command("addproduct"))
async def add_product_start(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(BotStates.product_category)
    await message.answer("Mahsulot kategoriyasini yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.product_category, F.text)
async def product_category(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    category = (message.text or "").strip()[:50]
    if not category:
        await message.answer("Kategoriya nomi bo‘sh bo‘lmasligi kerak.")
        return
    await state.update_data(category=category)
    await state.set_state(BotStates.product_name)
    await message.answer("Mahsulot nomini yuboring:")


@router.message(BotStates.product_name, F.text)
async def product_name(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    await state.update_data(name=(message.text or "")[:160])
    await state.set_state(BotStates.product_description)
    await message.answer("Mahsulot tavsifi:")


@router.message(BotStates.product_description, F.text)
async def product_description(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    await state.update_data(description=(message.text or "")[:2000])
    await state.set_state(BotStates.product_price)
    await message.answer("Narxini butun so‘mda kiriting:")


@router.message(BotStates.product_price, F.text)
async def product_price(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        price = int((message.text or "").replace(" ", ""))
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("Narx manfiy bo‘lmagan butun son bo‘lishi kerak.")
        return
    await state.update_data(price=price)
    await state.set_state(BotStates.product_photo)
    await message.answer("Mahsulot rasmini yuboring yoki rasmsiz qo‘shish uchun /skip yozing.")


@router.message(BotStates.product_photo, F.photo)
async def product_photo(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        category = await session.scalar(select(Category).where(Category.name == data["category"]))
        if category is None:
            category = Category(name=data["category"])
            session.add(category)
            await session.flush()
        session.add(Product(
            name=data["name"],
            description=data["description"],
            price=data["price"],
            photo_file_id=message.photo[-1].file_id,
            category_id=category.id,
        ))
        await session.commit()
    await state.clear()
    await message.answer("Mahsulot katalogga qo‘shildi.")


@router.message(BotStates.product_photo, Command("skip"))
async def product_without_photo(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        category = await session.scalar(select(Category).where(Category.name == data["category"]))
        if category is None:
            category = Category(name=data["category"])
            session.add(category)
            await session.flush()
        session.add(Product(
            name=data["name"],
            description=data["description"],
            price=data["price"],
            category_id=category.id,
        ))
        await session.commit()
    await state.clear()
    await message.answer("Mahsulot rasmsiz katalogga qo‘shildi.")


@router.message(Command("ban"))
async def ban_user(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    target = _target_id(message)
    if target is None:
        await message.answer("Foydalanish: /ban USER_ID")
        return
    async with SessionLocal() as session:
        user = await session.get(User, target)
        if not user:
            await message.answer("Foydalanuvchi topilmadi.")
            return
        user.is_banned = True
        await session.commit()
    await message.answer("Foydalanuvchi bloklandi.")


@router.message(Command("unban"))
async def unban_user(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    target = _target_id(message)
    if target is None:
        await message.answer("Foydalanish: /unban USER_ID")
        return
    async with SessionLocal() as session:
        user = await session.get(User, target)
        if not user:
            await message.answer("Foydalanuvchi topilmadi.")
            return
        user.is_banned = False
        await session.commit()
    await message.answer("Foydalanuvchi blokdan chiqarildi.")


def _target_id(message: Message) -> int | None:
    args = (message.text or "").split()
    return int(args[1]) if len(args) == 2 and args[1].isdigit() else None


@router.message(Command("bonus"))
async def bonus_start(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(BotStates.bonus_user)
    await message.answer("Bonus beriladigan Telegram user ID:")


@router.message(BotStates.bonus_user, F.text)
async def bonus_user(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    if not (message.text or "").isdigit():
        await message.answer("User ID faqat raqamlardan iborat bo‘lishi kerak.")
        return
    await state.update_data(target_id=int(message.text))
    await state.set_state(BotStates.bonus_amount)
    await message.answer("Qo‘shiladigan ball miqdori:")


@router.message(BotStates.bonus_amount, F.text)
async def bonus_amount(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        amount = int(message.text or "")
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Miqdor musbat butun son bo‘lishi kerak.")
        return
    target = (await state.get_data())["target_id"]
    async with SessionLocal() as session:
        user = await session.get(User, target)
        if not user:
            await message.answer("Foydalanuvchi topilmadi.")
            return
        user.balance += amount
        await session.commit()
    await state.clear()
    await message.answer(f"{target} foydalanuvchiga {amount} ball berildi.")
