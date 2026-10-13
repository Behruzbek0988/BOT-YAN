import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, FSInputFile
from sqlalchemy import select, update

from config import settings
from database.db import SessionLocal
from database.models import CartItem, Category, Order, OrderDetails, Product, User
from keyboards import BACK_MENU
from services.files import create_payment_invoice
from services.i18n import MenuAction
from states import BotStates

router = Router()
logger = logging.getLogger(__name__)
TASHKENT = ZoneInfo("Asia/Tashkent")


@router.message(MenuAction("🛒 Do‘kon"))
async def shop_home(message: Message) -> None:
    async with SessionLocal() as session:
        categories = (
            await session.scalars(
                select(Category)
                .join(Product, Product.category_id == Category.id)
                .where(Product.active.is_(True))
                .distinct()
                .order_by(Category.name)
            )
        ).all()
    if not categories:
        await message.answer("Katalog hozircha bo‘sh. Yangi mahsulotlar keyinroq qo‘shiladi.", reply_markup=BACK_MENU)
        return
    rows = [[InlineKeyboardButton(text=category.name, callback_data=f"category:{category.id}")] for category in categories]
    rows.append([InlineKeyboardButton(text="🛍 Savatni ko‘rish", callback_data="cart:view")])
    await message.answer("Kategoriyani tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("category:"))
async def category_products(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        products = (
            await session.scalars(
                select(Product)
                .where(Product.category_id == category_id, Product.active.is_(True))
                .order_by(Product.name)
            )
        ).all()
    if not products:
        await callback.answer("Bu kategoriyada mahsulot yo‘q.", show_alert=True)
        return
    rows = [
        [InlineKeyboardButton(text=f"{product.name} — {product.price:,} so‘m", callback_data=f"product:{product.id}")]
        for product in products
    ]
    rows.extend([
        [InlineKeyboardButton(text="⬅️ Kategoriyalar", callback_data="shop:categories")],
        [InlineKeyboardButton(text="🛍 Savat", callback_data="cart:view")],
    ])
    await callback.message.answer("Mahsulotni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data == "shop:categories")
async def back_categories(callback: CallbackQuery) -> None:
    await shop_home(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("product:"))
async def product_detail(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        if product is None or not product.active:
            await callback.answer("Mahsulot topilmadi.", show_alert=True)
            return
        text = f"{product.name}\n{product.description}\nNarxi: {product.price:,} so‘m"
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Savatga qo‘shish", callback_data=f"cart:add:{product.id}")],
            [InlineKeyboardButton(text="🛍 Savat", callback_data="cart:view")],
        ])
        photo = product.photo_file_id
    if photo:
        await callback.message.answer_photo(photo, caption=text, reply_markup=markup)
    else:
        await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("cart:add:"))
async def cart_add(callback: CallbackQuery) -> None:
    product_id = int(callback.data.rsplit(":", 1)[1])
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        if product is None or not product.active:
            await callback.answer("Mahsulot topilmadi.", show_alert=True)
            return
        item = await session.scalar(
            select(CartItem).where(CartItem.user_id == callback.from_user.id, CartItem.product_id == product_id)
        )
        if item:
            item.quantity += 1
        else:
            session.add(CartItem(user_id=callback.from_user.id, product_id=product_id, quantity=1))
        await session.commit()
    await callback.answer("Savatga qo‘shildi.")


@router.callback_query(F.data == "cart:view")
async def cart_view(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        items = (
            await session.execute(
                select(CartItem, Product).join(Product).where(CartItem.user_id == callback.from_user.id)
            )
        ).all()
        if not items:
            await callback.message.answer("Savatingiz bo‘sh.", reply_markup=BACK_MENU)
            await callback.answer()
            return
        total = sum(item.quantity * product.price for item, product in items)
        lines = [f"• {product.name} × {item.quantity} — {item.quantity * product.price:,} so‘m" for item, product in items]
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="cart:checkout")]
    ])
    async with SessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        balance = user.balance if user else 0
    await callback.message.answer(
        "Savat:\n" + "\n".join(lines) + f"\n\nJami: {total:,} so‘m\nIchki balans: {balance} ball.",
        reply_markup=markup,
    )
    await callback.answer()


@router.callback_query(F.data == "cart:checkout")
async def checkout(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        items = (
            await session.execute(
                select(CartItem, Product).join(Product).where(CartItem.user_id == callback.from_user.id)
            )
        ).all()
        if not items:
            await callback.answer("Savat bo‘sh.", show_alert=True)
            return
        total = sum(item.quantity * product.price for item, product in items)
        user = await session.get(User, callback.from_user.id)
        credit = min(user.balance, total) if user else 0
        if user:
            user.balance -= credit
        due = total - credit
        order = Order(
            user_id=callback.from_user.id,
            amount=due,
            status="awaiting_receipt",
        )
        session.add(order)
        await session.flush()
        order_id = order.id
        summary = "\n".join(
            f"{product.name} × {item.quantity} — {item.quantity * product.price:,} so‘m"
            for item, product in items
        )
        if credit:
            summary += f"\nIchki balansdan to‘lov: −{credit:,} so‘m"
        session.add(OrderDetails(
            order_id=order_id,
            summary=summary,
            total_amount=total,
            balance_used=credit,
        ))
        for item, _product in items:
            await session.delete(item)
        await session.commit()
    await _send_payment_instructions(callback.bot, callback.from_user.id, order_id, due, total, credit)
    await callback.answer()


@router.message(BotStates.receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext) -> None:
    order_id = (await state.get_data()).get("receipt_order_id")
    async with SessionLocal() as session:
        order = await session.get(Order, order_id) if order_id else None
        if order is None or order.user_id != message.from_user.id or order.status != "awaiting_receipt":
            await state.clear()
            await message.answer("Chek uchun faol buyurtma topilmadi.")
            return
        order.receipt_file_id = message.photo[-1].file_id
        order.status = "review"
        order_id = order.id
        await session.commit()
    await state.clear()
    if not settings.admin_ids:
        async with SessionLocal() as session:
            order = await session.get(Order, order_id)
            if order:
                order.status = "awaiting_receipt"
                await session.commit()
        await message.answer("ADMIN_IDS sozlanmagan. Chek saqlandi, ammo admin xabarini yuborib bo‘lmadi.")
        return
    try:
        await _notify_admins(message.bot, order_id, message.photo[-1].file_id)
    except TelegramAPIError:
        logger.exception("Receipt notification failed for order_id=%s", order_id)
        async with SessionLocal() as session:
            order = await session.get(Order, order_id)
            if order and order.status == "review":
                order.status = "awaiting_receipt"
                await session.commit()
        await message.answer("Chek adminga yuborilmadi. Keyinroq to‘lovni qayta yuboring.")
        return
    await message.answer("Chek administratorga tekshirish uchun yuborildi.")


async def _send_payment_instructions(
    bot: Bot,
    chat_id: int,
    order_id: int,
    due: int,
    total: int,
    credit: int = 0,
) -> None:
    cards = "\n".join(f"• {card}" for card in settings.payment_cards) or "To‘lov rekvizitlari sozlanmagan."
    payment_button = "✅ To‘lov qildim" if due else "✅ Balans bilan to‘landi"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=payment_button, callback_data=f"paydone:{order_id}")],
        *(
            [[InlineKeyboardButton(text="📤 Chek rasmini yuborish", callback_data=f"receipt:{order_id}")]]
            if due
            else []
        ),
    ])
    payment_details = (
        f"\n\nTo‘lov kartalari:\n{cards}\n\nTo‘lovdan so‘ng tugmani bosing yoki chek rasmini yuboring."
        if due
        else "\n\nIchki balans buyurtmani to‘liq qopladi. Tasdiq uchun tugmani bosing."
    )
    await bot.send_message(
        chat_id,
        f"Buyurtma #{order_id} yaratildi.\nJami: {total:,} so‘m"
        + (f"\nIchki balansdan: −{credit:,} so‘m" if credit else "")
        + f"\nTo‘lanishi: {due:,} so‘m"
        + payment_details,
        reply_markup=keyboard,
    )


async def _notify_admins(bot: Bot, order_id: int, receipt_file_id: str | None = None) -> bool:
    if not settings.admin_ids:
        return False
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        details = await session.get(OrderDetails, order_id)
        user = await session.get(User, order.user_id) if order else None
        if not order or not user:
            raise RuntimeError(f"Buyurtma #{order_id} yoki foydalanuvchi topilmadi.")
        receipt_file_id = receipt_file_id or order.receipt_file_id
        lines = [
            f"💳 To‘lov tekshiruvi — buyurtma #{order.id}",
            f"Xaridor: {details.customer_name if details and details.customer_name else user.full_name}",
            f"Telegram ID: {user.id}",
        ]
        if user.username:
            lines.append(f"Username: @{user.username}")
        if details and details.customer_phone:
            lines.append(f"Telefon: {details.customer_phone}")
        if details and details.customer_address:
            lines.append(f"Manzil: {details.customer_address}")
        if details and details.event_type:
            lines.append(f"Marosim: {details.event_type}")
        if details and details.service_name:
            lines.append(f"Xizmat: {details.service_name}")
        if details and details.summary:
            lines.extend(["", details.summary])
        lines.extend(["", f"To‘lanadigan summa: {order.amount:,} so‘m"])
        caption = "\n".join(lines)
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"order:approve:{order_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"order:reject:{order_id}"),
    ]])
    for admin_id in settings.admin_ids:
        await bot.send_message(admin_id, caption[:4000], reply_markup=markup)
        if receipt_file_id:
            await bot.send_photo(admin_id, receipt_file_id, caption=f"Buyurtma #{order_id} uchun to‘lov cheki.")
    return True


@router.callback_query(F.data.startswith("paydone:"))
async def payment_done(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[1])
    if not settings.admin_ids:
        await callback.answer("Admin ID sozlanmagan; to‘lovni tekshirishning imkoni yo‘q.", show_alert=True)
        return
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if order is None or order.user_id != callback.from_user.id or order.status != "awaiting_receipt":
            await callback.answer("Faol buyurtma topilmadi yoki allaqachon yuborilgan.", show_alert=True)
            return
        order.status = "review"
        await session.commit()
    try:
        await _notify_admins(callback.bot, order_id)
    except TelegramAPIError:
        logger.exception("Admin payment notification failed for order_id=%s", order_id)
        async with SessionLocal() as session:
            order = await session.get(Order, order_id)
            if order and order.status == "review":
                order.status = "awaiting_receipt"
                await session.commit()
        await callback.answer("Admin xabarnomasi yuborilmadi; qayta urinib ko‘ring.", show_alert=True)
        return
    await callback.message.answer("To‘lov xabari adminga yuborildi. Tasdiq javobini kuting.")
    await callback.answer("To‘lov tekshiruvga yuborildi.")


@router.callback_query(F.data.startswith("receipt:"))
async def receipt_begin(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if order is None or order.user_id != callback.from_user.id or order.status != "awaiting_receipt":
            await callback.answer("Faol buyurtma topilmadi.", show_alert=True)
            return
    await state.set_state(BotStates.receipt)
    await state.update_data(receipt_order_id=order_id)
    await callback.message.answer("To‘lov chekini rasm qilib yuboring.", reply_markup=BACK_MENU)
    await callback.answer()


@router.callback_query(F.data.startswith("order:"))
async def order_review(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    _, action, raw_id = callback.data.split(":")
    order_id = int(raw_id)
    if action not in {"approve", "reject"}:
        await callback.answer("Noma’lum amal.", show_alert=True)
        return
    if action == "reject":
        async with SessionLocal() as session:
            order = await session.get(Order, order_id)
            if order is None or order.status not in {"review", "awaiting_quote"}:
                await callback.answer("Buyurtma allaqachon ko‘rib chiqilgan.", show_alert=True)
                return
            previous_status = order.status
            order.status = "rejected"
            details = await session.get(OrderDetails, order_id)
            user = await session.get(User, order.user_id)
            if details and details.balance_used and user:
                user.balance += details.balance_used
                details.balance_used = 0
            user_id = order.user_id
            await session.commit()
        await callback.bot.send_message(
            user_id,
            (
                f"Buyurtma #{order_id} bo‘yicha to‘lov tasdiqlanmadi."
                if previous_status == "review"
                else f"Xizmat buyurtmangiz #{order_id} admin tomonidan rad etildi."
            )
            + f" Yordam uchun @{settings.admin_username} ga yozing.",
        )
        if callback.message.photo:
            await callback.message.edit_caption(caption=f"Buyurtma #{order_id}: rad etildi")
        else:
            await callback.message.edit_text(f"Buyurtma #{order_id}: rad etildi")
        await callback.answer("Buyurtma rad etildi.")
        return

    paid_at = datetime.now(TASHKENT).replace(tzinfo=None)
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != "review":
            await callback.answer("Buyurtma allaqachon ko‘rib chiqilgan.", show_alert=True)
            return
        details = await session.get(OrderDetails, order_id)
        user = await session.get(User, order.user_id)
        if user is None:
            await callback.answer("Xaridor ma’lumoti topilmadi.", show_alert=True)
            return
        invoice_number = details.invoice_number if details else None
        if not invoice_number:
            invoice_number = f"RCPT-{paid_at:%Y%m%d}-{order_id:06d}"
        summary = details.summary if details else "Mahsulot/xizmat tafsilotlari saqlanmagan"
        try:
            image_path, pdf_path = await asyncio.to_thread(
                create_payment_invoice,
                invoice_number,
                paid_at,
                details.customer_name if details and details.customer_name else user.full_name,
                user.id,
                summary,
                details.total_amount if details and details.total_amount else order.amount,
                settings.support_phone or "+998 94 793 11 14",
                settings.admin_username,
                user.language,
            )
        except Exception:
            logger.exception("Invoice generation failed for order_id=%s", order_id)
            await callback.answer("Chek yaratilmadi; buyurtma tasdiqlanmagan. Keyinroq qayta urinib ko‘ring.", show_alert=True)
            return
        changed = await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == "review")
            .values(status="approved")
        )
        if changed.rowcount != 1:
            await session.rollback()
            for path in (image_path, pdf_path):
                if os.path.exists(path):
                    os.remove(path)
            await callback.answer("Buyurtma allaqachon ko‘rib chiqilgan.", show_alert=True)
            return
        if details:
            details.invoice_number = invoice_number
            details.paid_at = paid_at
            details.balance_used = 0
        user_id = order.user_id
        await session.commit()
    try:
        await callback.bot.send_message(
            user_id,
            "Sizning to‘lovingiz tasdiqlandi va buyurtmangiz qabul qilindi! ✅",
        )
        await callback.bot.send_photo(
            user_id,
            FSInputFile(image_path),
            caption=f"To‘lov cheki #{invoice_number} — PAID / TO‘LANDI",
        )
        await callback.bot.send_document(
            user_id,
            FSInputFile(pdf_path),
            caption=f"Yuklab olish uchun PDF chek #{invoice_number}",
        )
    except TelegramAPIError:
        logger.exception("Paid invoice delivery failed for order_id=%s", order_id)
        await callback.message.answer(
            f"Buyurtma #{order_id} tasdiqlandi, lekin mijozga chek yuborilmadi. "
            "Bot foydalanuvchiga xabar yubora olishini tekshiring."
        )
        await callback.answer("Tasdiqlandi, ammo chekni yuborishda xatolik.", show_alert=True)
    else:
        await callback.answer("To‘lov tasdiqlandi; chek rasm va PDF ko‘rinishida yuborildi.")
    finally:
        for path in (image_path, pdf_path):
            if os.path.exists(path):
                os.remove(path)
    if callback.message.photo:
        await callback.message.edit_caption(caption=f"Buyurtma #{order_id}: tasdiqlandi — {invoice_number}")
    else:
        await callback.message.edit_text(f"Buyurtma #{order_id}: tasdiqlandi — {invoice_number}")


@router.message(Command("receipt"))
async def receipt_start(message: Message, state: FSMContext) -> None:
    async with SessionLocal() as session:
        order = await session.scalar(
            select(Order).where(Order.user_id == message.from_user.id, Order.status == "awaiting_receipt")
        )
    if not order:
        await message.answer("Chek yuborish uchun avval savatdan buyurtma yarating.")
        return
    await state.set_state(BotStates.receipt)
    await state.update_data(receipt_order_id=order.id)
    await message.answer("To‘lov chekini rasm qilib yuboring.", reply_markup=BACK_MENU)
