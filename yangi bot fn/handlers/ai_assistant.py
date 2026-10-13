import os
import tempfile

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from keyboards import BACK_MENU
from services.i18n import MenuAction, get_user_language
from services.ai import analyze_image, ask_ai, transcribe_audio
from states import BotStates

router = Router()


@router.message(MenuAction("🤖 AI yordamchi"))
async def open_ai(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.ai_prompt)
    await message.answer(
        "Savolingizni yoki tahrirlash/tarjima matnini yuboring. Rasm yoki ovozli xabarni ham yuborishingiz mumkin.",
        reply_markup=BACK_MENU,
    )


@router.message(BotStates.ai_prompt, F.text)
async def reply_ai(message: Message) -> None:
    try:
        answer = await ask_ai(message.text or "", await get_user_language(message.from_user.id))
        await message.answer(answer[:4000])
    except Exception as exc:
        await message.answer(f"AI so‘rovi bajarilmadi: {exc}")


async def _download(message: Message, file_id: str, suffix: str) -> str:
    telegram_file = await message.bot.get_file(file_id)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        path = temporary.name
    try:
        await message.bot.download_file(telegram_file.file_path, destination=path)
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise
    return path


@router.message(BotStates.ai_prompt, F.voice)
async def voice_to_text(message: Message) -> None:
    path = await _download(message, message.voice.file_id, ".ogg")
    try:
        text = await transcribe_audio(path)
        response = await ask_ai(text, await get_user_language(message.from_user.id))
        await message.answer(f"🎙 Tanilgan matn: {text[:1500]}\n\n🤖 {response[:2500]}")
    except Exception as exc:
        await message.answer(f"Ovozli xabarni qayta ishlashda xatolik: {exc}")
    finally:
        if os.path.exists(path):
            os.remove(path)


@router.message(BotStates.ai_prompt, F.photo)
async def image_to_text(message: Message) -> None:
    path = await _download(message, message.photo[-1].file_id, ".jpg")
    try:
        answer = await analyze_image(
            path,
            message.caption or "",
            await get_user_language(message.from_user.id),
        )
        await message.answer(answer[:4000])
    except Exception as exc:
        await message.answer(f"Rasm tahlilida xatolik: {exc}")
    finally:
        if os.path.exists(path):
            os.remove(path)
