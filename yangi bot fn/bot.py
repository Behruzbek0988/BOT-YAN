import asyncio
import logging
from datetime import datetime

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import TelegramObject

from config import settings
from database.db import SessionLocal, engine, init_db
from database.models import User, UserSequence
from handlers import admin, ai_assistant, bookings, contact, converter, downloader, games, planner, shop, start, tools
from services.i18n import current_language, get_user_language, localize_api_request
from services.scheduler import load_reminders, scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class UserLanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        from_user = data.get("event_from_user")
        language = await get_user_language(from_user.id) if from_user else "uz_latn"
        token = current_language.set(language)
        try:
            return await handler(event, data)
        finally:
            current_language.reset(token)


class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        from_user = data.get("event_from_user")
        if from_user:
            async with SessionLocal() as session:
                user = await session.get(User, from_user.id)
                if user is None:
                    user = User(
                        id=from_user.id,
                        telegram_id=from_user.id,
                        username=from_user.username,
                        full_name=from_user.full_name,
                    )
                    session.add(user)
                    await session.flush()
                    identity = UserSequence(telegram_id=from_user.id)
                    session.add(identity)
                    await session.flush()
                    user.public_id = identity.id
                user.telegram_id = from_user.id
                user.username = from_user.username
                user.full_name = from_user.full_name
                if user.is_banned and from_user.id not in settings.admin_ids:
                    answer = getattr(event, "answer", None)
                    if answer:
                        await answer("Hisobingiz bloklangan. Yordam uchun administratorga murojaat qiling.")
                    return None
                user.last_active_at = datetime.utcnow()
                await session.commit()
        return await handler(event, data)


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN .env faylida sozlanishi shart.")
    await init_db()
    bot = Bot(token=settings.bot_token)
    bot.session.middleware.register(localize_api_request)
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(UserLanguageMiddleware())
    dispatcher.update.outer_middleware(BanMiddleware())
    for router in (
        start.router,
        contact.router,
        ai_assistant.router,
        downloader.router,
        converter.router,
        planner.router,
        shop.router,
        bookings.router,
        tools.router,
        games.router,
        admin.router,
    ):
        dispatcher.include_router(router)

    await load_reminders(bot)
    scheduler.start()
    logger.info("Bot polling boshlandi")
    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
