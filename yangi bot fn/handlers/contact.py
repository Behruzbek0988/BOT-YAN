import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from config import settings
from database.db import SessionLocal
from database.models import User
from services.i18n import MenuAction
from states import BotStates

router = Router()
logger = logging.getLogger(__name__)


async def _begin_contact(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.contact_message)
    await message.answer("Adminga yuboriladigan matn, rasm, audio yoki videoni yuboring.")


@router.message(Command("contact"))
@router.message(MenuAction("✍️ Adminga yozish"))
async def contact_start(message: Message, state: FSMContext) -> None:
    await _begin_contact(message, state)


@router.message(BotStates.contact_message)
async def contact_send(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None:
            await message.answer("Avval /start buyrug‘ini bosing.")
            await state.clear()
            return
        username = f"@{user.username}" if user.username else "yo‘q"
        details = (
            "📩 Yangi murojaat\n"
            f"Noyob ID: {user.public_id or '—'}\n"
            f"Telegram ID: {user.telegram_id or user.id}\n"
            f"Username: {username}"
        )

    if not settings.admin_ids:
        await state.clear()
        await message.answer("Adminlar sozlanmagan. Keyinroq qayta urinib ko‘ring.")
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✉️ Javob berish",
            callback_data=f"contact:reply:{user_id}",
        )
    ]])
    delivered = False
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(admin_id, details, reply_markup=markup)
            await message.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except TelegramAPIError:
            logger.exception("Contact delivery failed for admin_id=%s", admin_id)
        else:
            delivered = True
    await state.clear()
    if delivered:
        await message.answer("Murojaatingiz adminga yuborildi.")
    else:
        await message.answer("Murojaat adminga yetkazilmadi. Keyinroq qayta urinib ko‘ring.")


@router.callback_query(F.data.startswith("contact:reply:"))
async def reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        target_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("Foydalanuvchi ID noto‘g‘ri.", show_alert=True)
        return
    await state.update_data(reply_target_id=target_id)
    await state.set_state(BotStates.admin_reply)
    await callback.message.answer("Foydalanuvchiga yuboriladigan javobni yozing yoki media yuboring.")
    await callback.answer()


@router.message(BotStates.admin_reply)
async def reply_send(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    data = await state.get_data()
    target_id = data.get("reply_target_id")
    try:
        await message.bot.copy_message(
            chat_id=target_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except TelegramAPIError:
        logger.exception("Admin reply delivery failed for user_id=%s", target_id)
        await message.answer("Javob yetkazilmadi. Foydalanuvchi botni bloklagan yoki mavjud emas.")
        return
    await state.clear()
    await message.answer("Javob foydalanuvchiga yetkazildi.")


@router.message(BotStates.admin_user_message)
@router.message(BotStates.admin_user_ad)
async def direct_message_send(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    data = await state.get_data()
    target_id = data.get("direct_target_id")
    try:
        await message.bot.copy_message(
            chat_id=target_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except TelegramAPIError:
        logger.exception("Admin direct message delivery failed for user_id=%s", target_id)
        await message.answer("Xabar yetkazilmadi. Foydalanuvchi botni bloklagan yoki mavjud emas.")
        return
    await state.clear()
    await message.answer("Shaxsiy xabar foydalanuvchiga yetkazildi.")
