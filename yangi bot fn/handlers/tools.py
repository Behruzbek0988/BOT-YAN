import os
import tempfile

import cv2
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from keyboards import BACK_MENU
from services.files import create_card, create_cv_pdf, create_qr
from services.i18n import MenuAction
from states import BotStates

router = Router()


@router.message(MenuAction("📇 Vizitka / QR / CV"))
async def tools_home(message: Message) -> None:
    await message.answer(
        "Buyruqlar: /qr — QR yaratish yoki o‘qish, /card — vizitka yaratish, /cv — PDF rezyume yaratish.",
        reply_markup=BACK_MENU,
    )


@router.message(Command("qr"))
async def qr_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.qr_text)
    await message.answer("QR yaratish uchun matn/havola yoki QR rasmini yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.qr_text, F.text)
async def qr_generate(message: Message, state: FSMContext) -> None:
    path = create_qr((message.text or "")[:2000])
    try:
        await message.answer_photo(FSInputFile(path), caption="QR-kod tayyor.")
        await state.clear()
    finally:
        os.remove(path)


@router.message(BotStates.qr_text, F.photo)
async def qr_decode(message: Message, state: FSMContext) -> None:
    telegram_file = await message.bot.get_file(message.photo[-1].file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temporary:
        path = temporary.name
    try:
        await message.bot.download_file(telegram_file.file_path, destination=path)
        image = cv2.imread(path)
        text, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
        await message.answer(f"QR ichidagi matn:\n{text}" if text else "Rasmda QR-kod topilmadi.")
        await state.clear()
    finally:
        os.remove(path)


@router.message(Command("card"))
async def card_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.card_name)
    await message.answer("Vizitkada ko‘rsatiladigan ismni yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.card_name, F.text)
async def card_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "")[:100])
    await state.set_state(BotStates.card_job)
    await message.answer("Kasbingizni yuboring:")


@router.message(BotStates.card_job, F.text)
async def card_job(message: Message, state: FSMContext) -> None:
    await state.update_data(job=(message.text or "")[:100])
    await state.set_state(BotStates.card_phone)
    await message.answer("Telefon raqamingizni yuboring:")


@router.message(BotStates.card_phone, F.text)
async def card_phone(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    path = create_card(data["name"], data["job"], (message.text or "")[:50])
    try:
        await message.answer_document(FSInputFile(path), caption="Vizitkangiz tayyor.")
        await state.clear()
    finally:
        os.remove(path)


@router.message(Command("cv"))
async def cv_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.cv_name)
    await message.answer("Rezyume uchun to‘liq ismingiz:", reply_markup=BACK_MENU)


@router.message(BotStates.cv_name, F.text)
async def cv_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "")[:100])
    await state.set_state(BotStates.cv_contact)
    await message.answer("Aloqa ma’lumotlari (telefon, email, manzil):")


@router.message(BotStates.cv_contact, F.text)
async def cv_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(contact=(message.text or "")[:500])
    await state.set_state(BotStates.cv_summary)
    await message.answer("Qisqacha maqsad va ko‘nikmalaringiz:")


@router.message(BotStates.cv_summary, F.text)
async def cv_summary(message: Message, state: FSMContext) -> None:
    await state.update_data(summary=(message.text or "")[:1500])
    await state.set_state(BotStates.cv_experience)
    await message.answer("Ish tajribasi va ta’lim:")


@router.message(BotStates.cv_experience, F.text)
async def cv_experience(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    path = create_cv_pdf(
        data["name"], data["contact"], data["summary"], (message.text or "")[:2000]
    )
    try:
        await message.answer_document(FSInputFile(path), caption="PDF rezyume tayyor.")
        await state.clear()
    finally:
        os.remove(path)
