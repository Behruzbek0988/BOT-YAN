import os
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from config import settings
from keyboards import BACK_MENU
from services.media import download_media
from services.i18n import MenuAction
from states import BotStates

router = Router()
ALLOWED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "twitter.com",
    "x.com",
)


@router.message(MenuAction("📥 Yuklab olish"))
async def open_downloader(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.download_url)
    await message.answer(
        "Instagram, TikTok, YouTube, Pinterest yoki X havolasini yuboring.\n"
        "Faqat MP3 audio uchun: mp3 https://... \n"
        "Platforma cheklovlari va mualliflik huquqlariga rioya qiling.",
        reply_markup=BACK_MENU,
    )


@router.message(BotStates.download_url, F.text)
async def download_link(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    audio_only = raw.lower().startswith("mp3 ")
    url = raw[4:].strip() if audio_only else raw
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS)
    if parsed.scheme != "https" or not allowed:
        await message.answer("Havola yaroqsiz yoki qo‘llab-quvvatlanmaydi. HTTPS platforma havolasini yuboring.")
        return
    status = await message.answer("Havola qayta ishlanmoqda, kuting…")
    path = ""
    try:
        path = await download_media(url, audio_only)
        size = os.path.getsize(path)
        if size > settings.max_download_mb * 1024 * 1024:
            raise ValueError(f"Fayl hajmi {settings.max_download_mb} MB limitidan katta.")
        await message.answer_document(FSInputFile(path), caption="Tayyor.")
        await state.clear()
    except Exception as exc:
        await message.answer(f"Yuklab bo‘lmadi: {exc}")
    finally:
        if path and os.path.exists(path):
            os.remove(path)
        await status.delete()
