from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import update

from config import settings
from database.db import SessionLocal
from database.models import User, UserSequence
from keyboards import MAIN_MENU
from services.i18n import LANGUAGES, LANGUAGE_LABELS, MenuAction, current_language

router = Router()
LANGUAGE_PICKER_TEXT = (
    "Tilni tanlang / Тилни танланг / Выберите язык / Choose your language:"
)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=LANGUAGE_LABELS["uz_latn"], callback_data="language:uz_latn"),
            InlineKeyboardButton(text=LANGUAGE_LABELS["uz_cyrl"], callback_data="language:uz_cyrl"),
        ],
        [
            InlineKeyboardButton(text=LANGUAGE_LABELS["ru"], callback_data="language:ru"),
            InlineKeyboardButton(text=LANGUAGE_LABELS["en"], callback_data="language:en"),
        ],
    ])


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    _remove_state_files(data)
    await state.clear()
    args = (message.text or "").split(maxsplit=1)
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id == message.from_user.id:
            referrer_id = None
    async with SessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        is_first_start = user is None or not user.has_started
        if user is None:
            user = User(id=message.from_user.id, telegram_id=message.from_user.id)
            session.add(user)
            await session.flush()
            identity = UserSequence(telegram_id=message.from_user.id)
            session.add(identity)
            await session.flush()
            user.public_id = identity.id
        if is_first_start:
            valid_referrer = (
                referrer_id
                if referrer_id and await session.get(User, referrer_id)
                else None
            )
            started = await session.execute(
                update(User)
                .where(User.id == message.from_user.id, User.has_started.is_(False))
                .values(has_started=True, referred_by=valid_referrer)
            )
            if started.rowcount == 1 and valid_referrer:
                await session.execute(
                    update(User)
                    .where(User.id == valid_referrer)
                    .values(balance=User.balance + settings.referral_bonus)
                )
        user.username = message.from_user.username
        user.full_name = message.from_user.full_name
        user.telegram_id = message.from_user.id
        user.last_active_at = datetime.utcnow()
        if user.is_banned:
            await message.answer("Hisobingiz bloklangan. Yordam uchun administratorga murojaat qiling.")
            return
        await session.commit()
    await message.answer(LANGUAGE_PICKER_TEXT, reply_markup=language_keyboard())


@router.callback_query(F.data.startswith("language:"))
async def select_language(callback: CallbackQuery, state: FSMContext) -> None:
    language = callback.data.split(":", 1)[1]
    if language not in LANGUAGES:
        await callback.answer("Unknown language.", show_alert=True)
        return
    async with SessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        if user is None:
            user = User(
                id=callback.from_user.id,
                telegram_id=callback.from_user.id,
                full_name=callback.from_user.full_name,
            )
            session.add(user)
            await session.flush()
            identity = UserSequence(telegram_id=callback.from_user.id)
            session.add(identity)
            await session.flush()
            user.public_id = identity.id
        user.language = language
        user.username = callback.from_user.username
        user.full_name = callback.from_user.full_name
        user.last_active_at = datetime.utcnow()
        await session.commit()
    await state.clear()
    current_language.set(language)
    await callback.message.answer(
        f"Assalomu alaykum, {callback.from_user.full_name}! Kerakli bo‘limni tanlang.",
        reply_markup=MAIN_MENU,
    )
    await callback.answer()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Bo‘limni pastdagi menyudan tanlang. Ichki amallar uchun /cancel buyrug‘i holatni bekor qiladi.",
        reply_markup=MAIN_MENU,
    )


@router.message(Command("language"))
async def language_command(message: Message) -> None:
    await message.answer(LANGUAGE_PICKER_TEXT, reply_markup=language_keyboard())


@router.message(MenuAction("📞 Yordam"))
async def support(message: Message) -> None:
    contact = f"@{settings.admin_username}"
    if settings.support_phone:
        contact += f"\nTelefon: {settings.support_phone}"
    await message.answer(f"Yordam va admin bilan aloqa:\n{contact}", reply_markup=MAIN_MENU)


@router.message(MenuAction("🔗 Referal"))
async def referral(message: Message) -> None:
    bot = await message.bot.get_me()
    async with SessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        balance = user.balance if user else 0
    link = f"https://t.me/{bot.username}?start={message.from_user.id}"
    await message.answer(
        f"Do‘stlaringizni taklif qiling:\n{link}\n\n"
        f"Har bir yangi foydalanuvchi uchun {settings.referral_bonus} ball. Joriy balans: {balance}.",
        reply_markup=MAIN_MENU,
    )


@router.message(MenuAction("🏠 Asosiy menyu"))
async def home(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    _remove_state_files(data)
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=MAIN_MENU)


@router.message(Command("cancel"))
@router.message(MenuAction("⬅️ Orqaga"))
async def cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    _remove_state_files(data)
    await state.clear()
    await message.answer("Amal bekor qilindi.", reply_markup=MAIN_MENU)


def _remove_state_files(data: dict) -> None:
    import os

    paths = [data.get("source"), *data.get("pdf_paths", [])]
    for path in paths:
        if path and os.path.exists(path):
            os.remove(path)
