from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from sqlalchemy import select

from database.db import SessionLocal
from database.models import Reminder

TIMEZONE = ZoneInfo("Asia/Tashkent")
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def deliver_reminder(bot: Bot, reminder_id: int) -> None:
    async with SessionLocal() as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder is None or reminder.sent:
            return
        await bot.send_message(reminder.user_id, f"⏰ Eslatma: {reminder.text}")
        reminder.sent = True
        await session.commit()


def schedule_reminder(bot: Bot, reminder_id: int, run_at: datetime) -> None:
    aware = run_at.replace(tzinfo=TIMEZONE)
    scheduler.add_job(
        deliver_reminder,
        "date",
        run_date=aware,
        args=[bot, reminder_id],
        id=f"reminder-{reminder_id}",
        replace_existing=True,
    )


async def load_reminders(bot: Bot) -> None:
    async with SessionLocal() as session:
        reminders = (
            await session.scalars(
                select(Reminder).where(Reminder.sent.is_(False))
            )
        ).all()
    for reminder in reminders:
        schedule_reminder(bot, reminder.id, reminder.run_at)
