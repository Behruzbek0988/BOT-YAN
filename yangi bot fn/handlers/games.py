from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer
from sqlalchemy import desc, select

from database.db import SessionLocal
from database.models import GameScore, QuizAnswer, User, UserSequence
from keyboards import BACK_MENU
from services.i18n import MenuAction

router = Router()


@router.message(MenuAction("🎮 O‘yinlar"))
async def games_home(message: Message) -> None:
    await message.answer(
        "🎲 /dice — zar o‘yini (Telegram dice), /quiz — savol, /leaderboard — reyting.",
        reply_markup=BACK_MENU,
    )


async def _play(message: Message, emoji: str, label: str) -> None:
    await message.answer(f"{label} o‘yini:")
    result = await message.answer_dice(emoji=emoji)
    points = result.dice.value
    async with SessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        if user is None:
            user = User(
                id=message.from_user.id,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name,
            )
            session.add(user)
            await session.flush()
            identity = UserSequence(telegram_id=message.from_user.id)
            session.add(identity)
            await session.flush()
            user.public_id = identity.id
        score = await session.get(GameScore, message.from_user.id)
        if score is None:
            score = GameScore(user_id=message.from_user.id, score=0)
            session.add(score)
        score.score += points
        await session.commit()
    await message.answer(f"Zar natijasi: {points} ball. Ballaringiz reytingga qo‘shildi.")


@router.message(Command("dice"))
async def dice(message: Message) -> None:
    await _play(message, "🎲", "Zar")


@router.message(Command("slots"))
async def slots(message: Message) -> None:
    await _play(message, "🎰", "Slot")


@router.message(Command("bowling"))
async def bowling(message: Message) -> None:
    await _play(message, "🎳", "Bowling")


@router.message(Command("football"))
async def football(message: Message) -> None:
    await _play(message, "⚽", "Futbol")


@router.message(Command("quiz"))
async def quiz(message: Message) -> None:
    await message.answer_poll(
        question="Kompyuter ko‘rishda tasvirni qayta ishlash uchun qaysi kutubxona keng qo‘llanadi?",
        options=["Pillow", "SQLAlchemy", "APScheduler", "aiogram"],
        type="quiz",
        correct_option_id=0,
        is_anonymous=False,
    )


@router.poll_answer()
async def record_quiz_answer(answer: PollAnswer) -> None:
    if not answer.user or not answer.option_ids or answer.option_ids[0] != 0:
        return
    async with SessionLocal() as session:
        existing = await session.get(QuizAnswer, (answer.poll_id, answer.user.id))
        if existing is not None:
            return
        user = await session.get(User, answer.user.id)
        if user is None:
            user = User(
                id=answer.user.id,
                telegram_id=answer.user.id,
                username=answer.user.username,
                full_name=answer.user.full_name,
            )
            session.add(user)
            await session.flush()
            identity = UserSequence(telegram_id=answer.user.id)
            session.add(identity)
            await session.flush()
            user.public_id = identity.id
        session.add(QuizAnswer(poll_id=answer.poll_id, user_id=answer.user.id))
        score = await session.get(GameScore, answer.user.id)
        if score is None:
            score = GameScore(user_id=answer.user.id, score=0)
            session.add(score)
        score.score += 10
        await session.commit()


@router.message(Command("leaderboard"))
async def leaderboard(message: Message) -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(User.full_name, GameScore.score)
                .join(GameScore, GameScore.user_id == User.id)
                .order_by(desc(GameScore.score))
                .limit(10)
            )
        ).all()
    text = "\n".join(f"{i}. {name or 'Foydalanuvchi'} — {score} ball" for i, (name, score) in enumerate(rows, 1))
    await message.answer("🏆 Peshqadamlar:\n" + (text or "Hozircha natijalar yo‘q."), reply_markup=BACK_MENU)
