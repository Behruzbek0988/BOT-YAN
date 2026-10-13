import asyncio
import os
import tempfile

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Audio, Document, FSInputFile, Message, PhotoSize, Video, Voice

from keyboards import BACK_MENU
from services.files import convert_image, convert_media, merge_pdfs, split_pdf
from services.i18n import MenuAction
from states import BotStates

router = Router()
SUPPORTED_FORMATS = {"PNG", "JPG", "JPEG", "WEBP"}


@router.message(MenuAction("🛠 Konvertor"))
async def open_converter(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.image_format)
    await message.answer(
        "Rasmni yuboring; caption sifatida PNG, JPG yoki WEBP yozing. "
        "Qo‘shimcha: /convertfile (audio/video/DOCX/PDF), /pdfmerge, /pdfsplit.",
        reply_markup=BACK_MENU,
    )


@router.message(BotStates.image_format, F.photo)
async def convert_photo(message: Message, state: FSMContext) -> None:
    requested = (message.caption or "").strip().upper()
    photo = message.photo[-1]
    telegram_file = await message.bot.get_file(photo.file_id)
    suffix = os.path.splitext(telegram_file.file_path or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        source = temporary.name
    try:
        await message.bot.download_file(telegram_file.file_path, destination=source)
    except Exception:
        os.remove(source)
        raise
    if requested not in SUPPORTED_FORMATS:
        await state.update_data(source=source)
        await message.answer("Qaysi format kerak? PNG, JPG yoki WEBP deb yuboring.")
        return
    await _send_converted(message, state, source, requested)


@router.message(BotStates.image_format, F.text)
async def select_format(message: Message, state: FSMContext) -> None:
    requested = (message.text or "").strip().upper()
    data = await state.get_data()
    source = data.get("source")
    if requested not in SUPPORTED_FORMATS or not source:
        await message.answer("Avval rasm yuboring, so‘ng PNG, JPG yoki WEBP formatini tanlang.")
        return
    await _send_converted(message, state, source, requested)


async def _send_converted(message: Message, state: FSMContext, source: str, image_format: str) -> None:
    output = ""
    try:
        output = await asyncio.to_thread(convert_image, source, image_format)
        await message.answer_document(FSInputFile(output), caption=f"Rasm {image_format} formatiga o‘girildi.")
        await state.clear()
    except Exception as exc:
        await message.answer(f"Rasmni o‘girishda xatolik: {exc}")
        await state.clear()
    finally:
        for path in (source, output):
            if path and os.path.exists(path):
                os.remove(path)


@router.message(Command("convertfile"))
async def convert_file_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.file_action)
    await message.answer(
        "Faylni caption bilan yuboring: mp3, ogg (Telegram voice), gif, compress, "
        "png, jpg, webp, pdf2docx yoki docx2pdf. Caption bo‘lmasa, keyin tanlaysiz.",
        reply_markup=BACK_MENU,
    )


@router.message(BotStates.file_action, F.text)
async def set_file_action(message: Message, state: FSMContext) -> None:
    mode = (message.text or "").strip().lower()
    if mode not in {"mp3", "ogg", "voice", "gif", "compress", "png", "jpg", "webp", "pdf2docx", "docx2pdf"}:
        await message.answer("Formatni yuboring: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx yoki docx2pdf.")
        return
    await state.update_data(mode="ogg" if mode == "voice" else mode)
    await message.answer(f"{mode} tanlandi. Endi konvertatsiya qilinadigan faylni yuboring.")


@router.message(
    BotStates.file_action,
    F.document | F.video | F.audio | F.voice | F.photo,
)
async def receive_convert_file(message: Message, state: FSMContext) -> None:
    telegram_file, suffix, size = _telegram_attachment(message)
    if size and size > 20 * 1024 * 1024:
        await message.answer("Fayl hajmi Telegram Bot API uchun 20 MB dan kichik bo‘lishi kerak.")
        return
    path = await _download_to_temp(message, telegram_file, suffix)
    mode = ((message.caption or "").strip().lower() or (await state.get_data()).get("mode"))
    if mode == "voice":
        mode = "ogg"
    if not mode:
        await state.update_data(source=path)
        await state.set_state(BotStates.file_format)
        await message.answer("Formatni tanlang: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx yoki docx2pdf.")
        return
    await _convert_and_send(message, state, path, mode)


@router.message(BotStates.file_format, F.text)
async def choose_file_format(message: Message, state: FSMContext) -> None:
    mode = (message.text or "").strip().lower()
    data = await state.get_data()
    source = data.get("source")
    if not source:
        await state.clear()
        await message.answer("Konvertatsiya uchun fayl topilmadi. /convertfile bilan qayta boshlang.")
        return
    await _convert_and_send(message, state, source, mode)


async def _convert_and_send(message: Message, state: FSMContext, source: str, mode: str) -> None:
    if mode == "voice":
        mode = "ogg"
    output = ""
    try:
        output = await convert_media(source, mode)
        result = FSInputFile(output)
        if mode in {"ogg", "voice"}:
            await message.answer_voice(result, caption="Audio voice formatiga o‘girildi.")
        else:
            await message.answer_document(result, caption=f"Konvertatsiya tayyor: {mode}.")
        await state.clear()
    except Exception as exc:
        await message.answer(f"Faylni konvertatsiya qilib bo‘lmadi: {exc}")
    finally:
        for path in (source, output):
            if path and os.path.exists(path):
                os.remove(path)
        await state.clear()


def _telegram_attachment(
    message: Message,
) -> tuple[Document | Video | Audio | Voice | PhotoSize, str, int | None]:
    if message.document:
        return message.document, os.path.splitext(message.document.file_name or "file.bin")[1], message.document.file_size
    if message.video:
        return message.video, ".mp4", message.video.file_size
    if message.audio:
        return message.audio, os.path.splitext(message.audio.file_name or "audio.mp3")[1], message.audio.file_size
    if message.voice:
        return message.voice, ".ogg", message.voice.file_size
    photo = message.photo[-1]
    return photo, ".jpg", photo.file_size


async def _download_to_temp(
    message: Message,
    telegram_file: Document | Video | Audio | Voice | PhotoSize,
    suffix: str,
) -> str:
    telegram_file_info = await message.bot.get_file(telegram_file.file_id)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        path = temporary.name
    try:
        await message.bot.download_file(telegram_file_info.file_path, destination=path)
    except Exception:
        os.remove(path)
        raise
    return path


@router.message(Command("pdfmerge"))
async def pdf_merge_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.pdf_merge)
    await state.update_data(pdf_paths=[])
    await message.answer("2–10 ta PDF yuboring, so‘ng /finish yozing.", reply_markup=BACK_MENU)


@router.message(BotStates.pdf_merge, F.document)
async def pdf_merge_add(message: Message, state: FSMContext) -> None:
    if not (message.document.file_name or "").lower().endswith(".pdf"):
        await message.answer("Faqat PDF fayllar qabul qilinadi.")
        return
    if message.document.file_size and message.document.file_size > 20 * 1024 * 1024:
        await message.answer("Har bir PDF 20 MB dan kichik bo‘lishi kerak.")
        return
    path = await _download_to_temp(message, message.document, ".pdf")
    data = await state.get_data()
    paths = data.get("pdf_paths", [])
    if len(paths) >= 10:
        os.remove(path)
        await message.answer("Birlashtirish uchun ko‘pi bilan 10 ta PDF yuboriladi.")
        return
    paths.append(path)
    await state.update_data(pdf_paths=paths)
    await message.answer(f"PDF qo‘shildi ({len(paths)} ta). Tugatish uchun /finish.")


@router.message(BotStates.pdf_merge, Command("finish"))
async def pdf_merge_finish(message: Message, state: FSMContext) -> None:
    paths = (await state.get_data()).get("pdf_paths", [])
    if len(paths) < 2:
        await message.answer("Birlashtirish uchun kamida 2 ta PDF yuboring.")
        return
    output = ""
    try:
        output = await asyncio.to_thread(merge_pdfs, paths)
        await message.answer_document(FSInputFile(output), caption="PDF fayllar birlashtirildi.")
        await state.clear()
    except Exception as exc:
        await message.answer(f"PDF birlashtirishda xatolik: {exc}")
    finally:
        for path in paths + ([output] if output else []):
            if os.path.exists(path):
                os.remove(path)
        await state.clear()


@router.message(Command("pdfsplit"))
async def pdf_split_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.pdf_split)
    await message.answer("Sahifalarga ajratiladigan PDF faylni yuboring (100 sahifagacha).", reply_markup=BACK_MENU)


@router.message(BotStates.pdf_split, F.document)
async def pdf_split_receive(message: Message, state: FSMContext) -> None:
    if not (message.document.file_name or "").lower().endswith(".pdf"):
        await message.answer("Faqat PDF fayl yuboring.")
        return
    if message.document.file_size and message.document.file_size > 20 * 1024 * 1024:
        await message.answer("PDF 20 MB dan kichik bo‘lishi kerak.")
        return
    source = await _download_to_temp(message, message.document, ".pdf")
    output = ""
    try:
        output = await asyncio.to_thread(split_pdf, source)
        await message.answer_document(FSInputFile(output), caption="PDF sahifalari alohida fayllarga ajratildi.")
        await state.clear()
    except Exception as exc:
        await message.answer(f"PDF ajratishda xatolik: {exc}")
    finally:
        for path in (source, output):
            if path and os.path.exists(path):
                os.remove(path)
