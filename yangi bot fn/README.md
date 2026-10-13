# Telegram yordamchi bot

Python 3.11+, aiogram 3 va SQLAlchemy async asosidagi o‘zbekcha Telegram bot.

## O‘rnatish va ishga tushirish

1. Virtual muhit yarating va bog‘liqliklarni o‘rnating:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. `.env.example` faylidan `.env` nusxa yarating. `BOT_TOKEN` va `ADMIN_IDS` (vergul bilan ajratilgan Telegram raqamli IDlar) qiymatlarini kiriting. AI, to‘lov va telefon sozlamalari ixtiyoriy; haqiqiy karta raqamlarini `.env` da saqlang va uni ommaga ulashmang.

3. Botni boshlang:

   ```powershell
   py bot.py
   ```

SQLite sukut bo‘yicha `bot.db` yaratadi. PostgreSQL uchun `DATABASE_URL` qiymatini `postgresql+asyncpg://...` ko‘rinishida sozlang. Eslatmalar va yuklamalar uchun bot jarayoni uzluksiz ishlashi kerak.

## Imkoniyatlar

- AI chat, rasm tahlili va audio transkripsiyasi (OpenAI kaliti bilan).
- YouTube, Instagram, TikTok, Pinterest va X uchun `yt-dlp` havola yuklovchisi hamda MP3 chiqarish (FFmpeg talab qilinishi mumkin; platforma cheklovlariga bog‘liq).
- Rasmni PNG/JPG/WEBP formatlariga o‘girish/siqish, QR yaratish/o‘qish, vizitka va PDF CV.
- `/convertfile`: MP3↔OGG voice, video→GIF hamda DOCX↔PDF; `/pdfmerge` va `/pdfsplit`.
- Vazifalar, Toshkent vaqtidagi eslatmalar, odatlar, katalog/savat va admin tasdiqlaydigan chek.
- Kamera/to‘y va marosim xizmatlariga buyurtma, mijoz ma’lumotlarini yig‘ish, narxi kelishiladigan xizmatlar uchun admin narx belgilashi.
- Admin to‘lovni tasdiqlagach, `PAID / TO‘LANDI` holatli unikal chek rasmi va PDF xaridorga avtomatik yuboriladi.
- Zar o‘yini, viktorina, reyting hamda admin statistika, xabar tarqatish, ban/bonus va mahsulot qo‘shish.
- `/contact` yoki `✍️ Adminga yozish` orqali adminlarga matn va media yuborish, admin javoblarini qabul qilish.
- `/admin` panelida 24 soat/7 kun ro‘yxatdan o‘tish statistikasi, bugungi faollik, bloklash, ID/username qidiruvi, shaxsiy xabar/reklama, inline tugmali ommaviy tarqatish va CSV eksport.
- Start paytida yoki `/language` buyrug‘i orqali o‘zbek lotin, o‘zbek kirill, rus va ingliz tillaridan birini tanlash; bot menyusi, tugmalari, bildirishnomalari va cheklari tanlangan tilga moslashadi.
- Foydalanuvchi yozuvlari har bir Telegram yangilanishida yuritiladi; tavsiya bonusi esa faqat birinchi `/start` havolasi uchun bir marta beriladi.

Xizmat narxlari: 1 kunlik to‘y (1 kamera) — 850 000 so‘m; 2 kunlik to‘y (1 kamera) — 1 650 000 so‘m; qisqa marosim — 200 000 so‘m/soat. Vizitka, logo, reklama va AI xizmatlari uchun admin narxni belgilaydi, undan so‘ng xaridorga to‘lov tugmalari yuboriladi.

FFmpeg audio/video uchun, LibreOffice esa DOCX→PDF uchun tizimga alohida o‘rnatilib PATH ga qo‘shilishi kerak. PDF→DOCX matn joylashuvini mukammal saqlamasligi mumkin. Chek tasdiqlash qo‘lda bajariladi; avtomatik bank tekshiruvi yo‘q. To‘lov kartalari `.env` dagi `PAYMENT_CARDS` vergul bilan ajratilgan qiymatdan olinadi. Referral ballari buyurtma summasidan avtomatik chegiriladi (1 ball = 1 so‘m). Admin bildirishnomalari va buyurtma tekshiruvi uchun `ADMIN_IDS` ga adminning sonli Telegram ID sini kiriting. Bot private chatda username orqali birinchi bo‘lib xabar yubora olmaydi; admin botni ishga tushirgan bo‘lishi ham kerak.

Asosiy buyruqlar: `/todo`, `/todos`, `/remind`, `/habit`, `/habits`, `/qr`, `/card`, `/cv`, `/dice`, `/slots`, `/bowling`, `/football`, `/quiz`, `/leaderboard`, `/contact`. Xizmat buyurtmasi esa asosiy menyudagi `🎥 Xizmat buyurtma` tugmasidan boshlanadi. Admin: `/admin`, `/stats`, `/broadcast`, `/addproduct`, `/ban ID`, `/unban ID`, `/bonus`. Admin panelidagi CSV eksportda ichki noyob ID va Telegram ID alohida ustunlarda beriladi; mavjud bot funksiyalaridagi foreign key mosligini saqlash uchun `users.id` Telegram ID bo‘lib qoladi.

Foydalanuvchi botni birinchi marta ochganda til tanlaydi; tilni keyin `/language` bilan almashtirish mumkin. Foydalanuvchi yoki admin kiritgan ism, manzil, mahsulot nomi va erkin matnlar asl ko‘rinishida saqlanadi; botning interfeys matnlari esa tanlangan tilga o‘giriladi.
