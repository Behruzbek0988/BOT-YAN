from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy import func, select

from database.db import SessionLocal
from database.models import Habit, HabitLog, Reminder, Todo
from keyboards import BACK_MENU
from services.scheduler import TIMEZONE, schedule_reminder
from services.i18n import MenuAction
from states import BotStates

router = Router()


@router.message(MenuAction("🗓 Rejalar"))
async def planner(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Rejalar: /todo — vazifa qo‘shish, /todos — ro‘yxat, /remind — eslatma, "
        "/habit — odat qo‘shish, /habits — odatlarni belgilash.",
        reply_markup=BACK_MENU,
    )


@router.message(Command("todo"))
async def add_todo_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.todo_text)
    await message.answer("Vazifa matnini yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.todo_text, F.text)
async def add_todo(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or len(text) > 500:
        await message.answer("Vazifa 1–500 belgi bo‘lishi kerak.")
        return
    async with SessionLocal() as session:
        session.add(Todo(user_id=message.from_user.id, text=text))
        await session.commit()
    await state.clear()
    await message.answer("Vazifa qo‘shildi. Ro‘yxat: /todos", reply_markup=BACK_MENU)


@router.message(Command("todos"))
async def list_todos(message: Message) -> None:
    async with SessionLocal() as session:
        todos = (
            await session.scalars(
                select(Todo).where(Todo.user_id == message.from_user.id).order_by(Todo.id.desc()).limit(20)
            )
        ).all()
    if not todos:
        await message.answer("Vazifalar ro‘yxati bo‘sh.", reply_markup=BACK_MENU)
        return
    rows = [
        [InlineKeyboardButton(text=f"{'✅' if todo.is_done else '⬜'} {todo.text[:45]}", callback_data=f"todo:{todo.id}")]
        for todo in todos
    ]
    await message.answer("Bajarilganini belgilash uchun vazifaga bosing:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("todo:"))
async def toggle_todo(callback: CallbackQuery) -> None:
    todo_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        todo = await session.get(Todo, todo_id)
        if todo is None or todo.user_id != callback.from_user.id:
            await callback.answer("Vazifa topilmadi.", show_alert=True)
            return
        todo.is_done = not todo.is_done
        await session.commit()
        text = f"{'✅' if todo.is_done else '⬜'} {todo.text}"
    await callback.message.edit_text(text)
    await callback.answer("Vazifa yangilandi.")


@router.message(Command("remind"))
async def reminder_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.reminder_text)
    await message.answer("Eslatma matnini yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.reminder_text, F.text)
async def reminder_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or len(text) > 500:
        await message.answer("Eslatma 1–500 belgi bo‘lishi kerak.")
        return
    await state.update_data(reminder_text=text)
    await state.set_state(BotStates.reminder_time)
    await message.answer("Sana va vaqtni YYYY-MM-DD HH:MM ko‘rinishida yuboring (Toshkent vaqti).")


@router.message(BotStates.reminder_time, F.text)
async def reminder_time(message: Message, state: FSMContext) -> None:
    try:
        run_at = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Sana formati xato. Masalan: 2026-10-09 09:30")
        return
    if run_at <= datetime.now(TIMEZONE).replace(tzinfo=None):
        await message.answer("Eslatma vaqti kelajakda bo‘lishi kerak.")
        return
    text = (await state.get_data())["reminder_text"]
    async with SessionLocal() as session:
        reminder = Reminder(user_id=message.from_user.id, text=text, run_at=run_at)
        session.add(reminder)
        await session.commit()
        reminder_id = reminder.id
    schedule_reminder(message.bot, reminder_id, run_at)
    await state.clear()
    await message.answer(f"⏰ Eslatma {run_at:%Y-%m-%d %H:%M} ga belgilandi.", reply_markup=BACK_MENU)


@router.message(Command("habit"))
async def habit_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.habit_name)
    await message.answer("Kuzatmoqchi bo‘lgan odat nomini yuboring:", reply_markup=BACK_MENU)


@router.message(BotStates.habit_name, F.text)
async def add_habit(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()[:160]
    if not name:
        await message.answer("Odat nomi bo‘sh bo‘lmasligi kerak.")
        return
    async with SessionLocal() as session:
        exists = await session.scalar(select(Habit.id).where(Habit.user_id == message.from_user.id, Habit.name == name))
        if exists:
            await message.answer("Bu odat allaqachon mavjud.")
            return
        session.add(Habit(user_id=message.from_user.id, name=name))
        await session.commit()
    await state.clear()
    await message.answer("Odat qo‘shildi. Bugungi belgilash uchun /habits buyrug‘idan foydalaning.")


@router.message(Command("habits"))
async def habits(message: Message) -> None:
    async with SessionLocal() as session:
        items = (await session.scalars(select(Habit).where(Habit.user_id == message.from_user.id))).all()
        rows = []
        today = datetime.now(TIMEZONE).date().isoformat()
        for habit in items:
            done = await session.scalar(
                select(func.count(HabitLog.id)).where(HabitLog.habit_id == habit.id, HabitLog.day == today)
            )
            total = await session.scalar(
                select(func.count(HabitLog.id)).where(HabitLog.habit_id == habit.id)
            )
            rows.append([InlineKeyboardButton(
                text=f"{'✅' if done else '⬜'} {habit.name} — {total} kun",
                callback_data=f"habit:{habit.id}",
            )])
    await message.answer(
        "Bugungi odatlarni belgilang:" if rows else "Odatlar ro‘yxati bo‘sh. /habit bilan qo‘shing.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else BACK_MENU,
    )


@router.callback_query(F.data.startswith("habit:"))
async def log_habit(callback: CallbackQuery) -> None:
    habit_id = int(callback.data.split(":")[1])
    today = datetime.now(TIMEZONE).date().isoformat()
    async with SessionLocal() as session:
        habit = await session.get(Habit, habit_id)
        if habit is None or habit.user_id != callback.from_user.id:
            await callback.answer("Odat topilmadi.", show_alert=True)
            return
        exists = await session.scalar(
            select(HabitLog.id).where(HabitLog.habit_id == habit_id, HabitLog.day == today)
        )
        if exists:
            await callback.answer("Bugun allaqachon belgilangan.")
            return
        session.add(HabitLog(habit_id=habit_id, day=today))
        await session.commit()
    await callback.answer("Bugun bajarildi! ✅")
    await callback.message.edit_text(f"✅ {habit.name} — bugun bajarildi")
