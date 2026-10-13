import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import settings
from database.db import SessionLocal
from database.models import Order, OrderDetails
from handlers.shop import _send_payment_instructions
from keyboards import BACK_MENU
from states import BotStates
from services.i18n import MenuAction

router = Router()
logger = logging.getLogger(__name__)

SERVICES = {
    "camera_1day": ("1 kunlik to‘y (1 ta kamera)", 850_000, False),
    "camera_2day": ("2 kunlik to‘y (1 ta kamera)", 1_650_000, False),
    "short_event": ("Qisqa marosim — soatiga", 200_000, False),
    "business_card": ("Vizitka tayyorlash", 0, True),
    "logo": ("Logo xizmati", 0, True),
    "advertising": ("Reklama xizmati", 0, True),
    "ai_service": ("AI xizmatlari", 0, True),
}


@router.message(MenuAction("🎥 Xizmat buyurtma"))
async def service_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    rows = [
        [InlineKeyboardButton(text=f"{name} — {price:,} so‘m" if price else f"{name} — narx kelishiladi",
                              callback_data=f"service:{key}")]
        for key, (name, price, _negotiable) in SERVICES.items()
    ]
    await message.answer(
        "Xizmat turini tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("service:"))
async def select_service(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = callback.data.split(":", 1)[1]
    service = SERVICES.get(service_id)
    if service is None:
        await callback.answer("Xizmat topilmadi.", show_alert=True)
        return
    name, price, negotiable = service
    await state.update_data(
        service_id=service_id,
        service_name=name,
        unit_price=price,
        negotiable=negotiable,
    )
    if service_id == "short_event":
        await state.set_state(BotStates.service_hours)
        await callback.message.answer("Marosim necha soat davom etadi? Butun son kiriting.", reply_markup=BACK_MENU)
    else:
        await state.set_state(BotStates.service_full_name)
        await callback.message.answer("To‘liq ismingizni yuboring:", reply_markup=BACK_MENU)
    await callback.answer()


@router.message(BotStates.service_hours, F.text)
async def service_hours(message: Message, state: FSMContext) -> None:
    try:
        hours = int((message.text or "").strip())
        if not 1 <= hours <= 24:
            raise ValueError
    except ValueError:
        await message.answer("Soat miqdori 1 dan 24 gacha bo‘lgan butun son bo‘lsin.")
        return
    await state.update_data(hours=hours, unit_price=200_000 * hours)
    await state.set_state(BotStates.service_full_name)
    await message.answer("To‘liq ismingizni yuboring:")


@router.message(BotStates.service_full_name, F.text)
async def service_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 160:
        await message.answer("Ism 2–160 belgi bo‘lishi kerak.")
        return
    await state.update_data(customer_name=name)
    await state.set_state(BotStates.service_phone)
    await message.answer("Telefon raqamingizni yuboring:")


@router.message(BotStates.service_phone, F.text)
async def service_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    digits = "".join(character for character in phone if character.isdigit())
    if not 7 <= len(digits) <= 15:
        await message.answer("Telefon raqami yaroqsiz. Masalan: +998 90 123 45 67")
        return
    await state.update_data(customer_phone=phone[:40])
    await state.set_state(BotStates.service_address)
    await message.answer("To‘liq manzilingizni yuboring:")


@router.message(BotStates.service_address, F.text)
async def service_address(message: Message, state: FSMContext) -> None:
    address = (message.text or "").strip()
    if len(address) < 4 or len(address) > 500:
        await message.answer("Manzil 4–500 belgi bo‘lishi kerak.")
        return
    await state.update_data(customer_address=address)
    await state.set_state(BotStates.service_event)
    await message.answer(
        "To‘y yoki marosim turini yozing (masalan: qiz to‘yi, uylanish to‘yi, tashqaridagi marosim):"
    )


@router.message(BotStates.service_event, F.text)
async def service_event(message: Message, state: FSMContext) -> None:
    event_type = (message.text or "").strip()
    if len(event_type) < 2 or len(event_type) > 160:
        await message.answer("Marosim turi 2–160 belgi bo‘lishi kerak.")
        return
    data = await state.get_data()
    if not settings.admin_ids:
        await state.clear()
        await message.answer(
            "Buyurtmani yuborib bo‘lmadi: administrator Telegram ID sozlanmagan. "
            "Admin ADMIN_IDS qiymatini sozlasin.",
            reply_markup=BACK_MENU,
        )
        return
    name = data["service_name"]
    hours = data.get("hours")
    if hours:
        name = f"{name} ({hours} soat)"
    price = data["unit_price"]
    is_quote = data["negotiable"]
    status = "awaiting_quote" if is_quote else "awaiting_receipt"
    details_text = (
        f"Xizmat: {name}\n"
        f"Xaridor: {data['customer_name']}\n"
        f"Telefon: {data['customer_phone']}\n"
        f"Manzil: {data['customer_address']}\n"
        f"Marosim: {event_type}\n"
        f"Narx: {'admin bilan kelishiladi' if is_quote else f'{price:,} so‘m'}"
    )
    async with SessionLocal() as session:
        order = Order(user_id=message.from_user.id, amount=price, status=status)
        session.add(order)
        await session.flush()
        order_id = order.id
        session.add(OrderDetails(
            order_id=order_id,
            summary=details_text,
            total_amount=price,
            customer_name=data["customer_name"],
            customer_phone=data["customer_phone"],
            customer_address=data["customer_address"],
            event_type=event_type,
            service_name=name,
        ))
        await session.commit()
    await state.clear()
    if is_quote:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💰 Narx belgilash", callback_data=f"quote:{order_id}")
        ], [
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"order:reject:{order_id}")
        ]])
        for admin_id in settings.admin_ids:
            await message.bot.send_message(
                admin_id,
                f"🆕 Narxi kelishiladigan xizmat buyurtmasi #{order_id}\n"
                f"Telegram ID: {message.from_user.id}\n\n{details_text}",
                reply_markup=markup,
            )
        await message.answer(
            f"Buyurtmangiz #{order_id} adminga yuborildi. Narx kelishilgach, to‘lov rekvizitlari yuboriladi.",
            reply_markup=BACK_MENU,
        )
    else:
        await message.answer(
            f"Buyurtma #{order_id} qabul qilindi.\nXizmat: {name}\nSumma: {price:,} so‘m",
            reply_markup=BACK_MENU,
        )
        await _send_payment_instructions(message.bot, message.from_user.id, order_id, price, price)


@router.callback_query(F.data.startswith("quote:"))
async def quote_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    order_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != "awaiting_quote":
            await callback.answer("Narx kelishish uchun faol buyurtma topilmadi.", show_alert=True)
            return
    await state.set_state(BotStates.admin_quote_amount)
    await state.update_data(quote_order_id=order_id)
    await callback.message.answer(f"Buyurtma #{order_id} uchun narxni so‘mda yuboring:")
    await callback.answer()


@router.message(BotStates.admin_quote_amount, F.text)
async def quote_set_amount(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    try:
        amount = int((message.text or "").replace(" ", "").replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Narx musbat butun son bo‘lishi kerak.")
        return
    order_id = (await state.get_data()).get("quote_order_id")
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        details = await session.get(OrderDetails, order_id) if order else None
        if order is None or details is None or order.status != "awaiting_quote":
            await state.clear()
            await message.answer("Buyurtma topilmadi yoki allaqachon ko‘rib chiqilgan.")
            return
        order.amount = amount
        order.status = "awaiting_receipt"
        details.summary += f"\nKelishilgan narx: {amount:,} so‘m"
        details.total_amount = amount
        user_id = order.user_id
        await session.commit()
    await state.clear()
    await message.answer(f"Buyurtma #{order_id} uchun {amount:,} so‘m belgilandi.")
    await _send_payment_instructions(message.bot, user_id, order_id, amount, amount)
