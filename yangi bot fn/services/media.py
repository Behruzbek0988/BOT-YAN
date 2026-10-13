import asyncio
import os
import uuid
from pathlib import Path

import yt_dlp

from config import settings


def _download(url: str, audio_only: bool) -> str:
    os.makedirs(settings.download_dir, exist_ok=True)
    file_id = uuid.uuid4().hex
    options = {
        "outtmpl": os.path.join(settings.download_dir, f"{file_id}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": settings.max_download_mb * 1024 * 1024,
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
        "restrictfilenames": True,
    }
    if audio_only:
        options["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([url])
    ext = ".mp3" if audio_only else None
    candidates = list(Path(settings.download_dir).glob(f"{file_id}.*"))
    if ext:
        result = Path(settings.download_dir) / f"{file_id}{ext}"
        if result.exists():
            return str(result)
    if not candidates:
        raise RuntimeError("Yuklangan fayl topilmadi.")
    return str(candidates[0])


async def download_media(url: str, audio_only: bool = False) -> str:
    return await asyncio.to_thread(_download, url, audio_only)
