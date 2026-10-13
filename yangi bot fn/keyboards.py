from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from services.i18n import CATALOG

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=CATALOG["uz_latn"]["🤖 AI yordamchi"]), KeyboardButton(text=CATALOG["uz_latn"]["📥 Yuklab olish"])],
        [KeyboardButton(text=CATALOG["uz_latn"]["🛠 Konvertor"]), KeyboardButton(text=CATALOG["uz_latn"]["🗓 Rejalar"])],
        [KeyboardButton(text=CATALOG["uz_latn"]["🛒 Do‘kon"]), KeyboardButton(text=CATALOG["uz_latn"]["📇 Vizitka / QR / CV"])],
        [KeyboardButton(text=CATALOG["uz_latn"]["🎥 Xizmat buyurtma"])],
        [KeyboardButton(text=CATALOG["uz_latn"]["🎮 O‘yinlar"]), KeyboardButton(text=CATALOG["uz_latn"]["🔗 Referal"])],
        [KeyboardButton(text=CATALOG["uz_latn"]["✍️ Adminga yozish"])],
        [KeyboardButton(text=CATALOG["uz_latn"]["📞 Yordam"]), KeyboardButton(text=CATALOG["uz_latn"]["🏠 Asosiy menyu"])],
    ],
    resize_keyboard=True,
)

BACK_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text=CATALOG["uz_latn"]["⬅️ Orqaga"]),
            KeyboardButton(text=CATALOG["uz_latn"]["🏠 Asosiy menyu"]),
        ]
    ],
    resize_keyboard=True,
)
