import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_list(name: str) -> list[int]:
    return [int(item.strip()) for item in os.getenv(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: list[int] = field(default_factory=list)
    admin_username: str = os.getenv("ADMIN_USERNAME", "Behruzbek_0875").lstrip("@")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    support_phone: str = os.getenv("SUPPORT_PHONE", "+998 94 793 11 14")
    payment_cards: tuple[str, ...] = tuple(
        card.strip() for card in os.getenv("PAYMENT_CARDS", "").split(",") if card.strip()
    )
    referral_bonus: int = int(os.getenv("REFERRAL_BONUS", "10"))
    max_download_mb: int = int(os.getenv("MAX_DOWNLOAD_MB", "45"))
    download_dir: str = os.getenv("DOWNLOAD_DIR", "downloads")


settings = Settings(admin_ids=_env_list("ADMIN_IDS"))
