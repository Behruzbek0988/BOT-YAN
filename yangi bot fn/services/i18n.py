import contextvars
import logging
import re
from typing import Any

from aiogram.filters import Filter
from aiogram.types import Message, ReplyKeyboardMarkup
from sqlalchemy import select

from database.db import SessionLocal
from database.models import User

logger = logging.getLogger(__name__)

LANGUAGES = ("uz_latn", "uz_cyrl", "ru", "en")
LANGUAGE_LABELS = {
    "uz_latn": "🇺🇿 O‘zbekcha (Lotin)",
    "uz_cyrl": "🇺🇿 Ўзбекча (Кирилл)",
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}

_RAW_CATALOG = r"""
🏠 Asosiy menyu|🏠 Асосий меню|🏠 Главное меню|🏠 Main menu
✍️ Adminga yozish|✍️ Админга ёзиш|✍️ Написать администратору|✍️ Contact admin
⬅️ Orqaga|⬅️ Орқага|⬅️ Назад|⬅️ Back
🤖 AI yordamchi|🤖 AI ёрдамчи|🤖 AI-помощник|🤖 AI assistant
📥 Yuklab olish|📥 Юклаб олиш|📥 Скачать медиа|📥 Download media
🛠 Konvertor|🛠 Конвертер|🛠 Конвертер|🛠 Converter
🗓 Rejalar|🗓 Режалар|🗓 Планирование|🗓 Planner
🛒 Do‘kon|🛒 Дўкон|🛒 Магазин|🛒 Shop
📇 Vizitka / QR / CV|📇 Визитка / QR / CV|📇 Визитка / QR / CV|📇 Business card / QR / CV
🎥 Xizmat buyurtma|🎥 Хизмат буюртма|🎥 Заказать услугу|🎥 Book a service
🎮 O‘yinlar|🎮 Ўйинлар|🎮 Игры|🎮 Games
🔗 Referal|🔗 Реферал|🔗 Реферал|🔗 Referral
📞 Yordam|📞 Ёрдам|📞 Помощь|📞 Help
✅ Tasdiqlash|✅ Тасдиқлаш|✅ Подтвердить|✅ Approve
❌ Rad etish|❌ Рад этиш|❌ Отклонить|❌ Reject
📤 Chek yuborish|📤 Чек юбориш|📤 Отправить чек|📤 Send receipt
✅ To‘lov qildim|✅ Тўлов қилдим|✅ Я оплатил(а)|✅ I have paid
✅ Balans bilan to‘landi|✅ Баланс билан тўланди|✅ Оплачено с баланса|✅ Paid with balance
📤 Chek rasmini yuborish|📤 Чек расмини юбориш|📤 Отправить фото чека|📤 Upload receipt photo
🛍 Savatni ko‘rish|🛍 Саватни кўриш|🛍 Посмотреть корзину|🛍 View cart
🛍 Savat|🛍 Сават|🛍 Корзина|🛍 Cart
➕ Savatga qo‘shish|➕ Саватга қўшиш|➕ В корзину|➕ Add to cart
✅ Buyurtma berish|✅ Буюртма бериш|✅ Оформить заказ|✅ Place order
⬅️ Kategoriyalar|⬅️ Категориялар|⬅️ Категории|⬅️ Categories
💰 Narx belgilash|💰 Нарх белгилаш|💰 Указать цену|💰 Set price
Xizmat topilmadi.|Хизмат топилмади.|Услуга не найдена.|Service not found.
Xizmat turini tanlang:|Хизмат турини танланг:|Выберите услугу:|Choose a service:
To‘liq ismingizni yuboring:|Тўлиқ исмингизни юборинг:|Введите полное имя:|Enter your full name:
Telefon raqamingizni yuboring:|Телефон рақамингизни юборинг:|Введите номер телефона:|Enter your phone number:
To‘liq manzilingizni yuboring:|Тўлиқ манзилингизни юборинг:|Введите полный адрес:|Enter your full address:
To‘y yoki marosim turini yozing (masalan: qiz to‘yi, uylanish to‘yi, tashqaridagi marosim):|Тўй ёки маросим турини ёзинг (масалан: қиз тўйи, уйланиш тўйи, ташқаридаги маросим):|Укажите тип мероприятия (например, свадьба или выездная церемония):|Enter the event type (for example, wedding or outdoor ceremony):
Marosim necha soat davom etadi? Butun son kiriting.|Маросим неча соат давом этади? Бутун сон киритинг.|Сколько часов продлится мероприятие? Введите целое число.|How many hours will the event last? Enter a whole number.
Ism 2–160 belgi bo‘lishi kerak.|Исм 2–160 белги бўлиши керак.|Имя должно содержать от 2 до 160 символов.|Name must be 2–160 characters.
Telefon raqami yaroqsiz. Masalan: +998 90 123 45 67|Телефон рақами нотўғри. Масалан: +998 90 123 45 67|Неверный номер телефона. Например: +998 90 123 45 67|Invalid phone number. Example: +998 90 123 45 67
Manzil 4–500 belgi bo‘lishi kerak.|Манзил 4–500 белги бўлиши керак.|Адрес должен содержать от 4 до 500 символов.|Address must be 4–500 characters.
Marosim turi 2–160 belgi bo‘lishi kerak.|Маросим тури 2–160 белги бўлиши керак.|Тип мероприятия должен содержать от 2 до 160 символов.|Event type must be 2–160 characters.
Buyurtmani yuborib bo‘lmadi: administrator Telegram ID sozlanmagan. Admin ADMIN_IDS qiymatini sozlasin.|Буюртма юборилмади: администраторнинг Telegram ID рақами созланмаган. Админ ADMIN_IDS ни созласин.|Не удалось отправить заказ: не настроен Telegram ID администратора. Настройте ADMIN_IDS.|Could not submit the order: admin Telegram ID is not configured. Set ADMIN_IDS.
Narx kelishish uchun faol buyurtma topilmadi.|Нарх келишиш учун фаол буюртма топилмади.|Не найден активный заказ для согласования цены.|No active order found for price negotiation.
Narx musbat butun son bo‘lishi kerak.|Нарх мусбат бутун сон бўлиши керак.|Цена должна быть положительным целым числом.|Price must be a positive integer.
Buyurtma topilmadi yoki allaqachon ko‘rib chiqilgan.|Буюртма топилмади ёки аллақачон кўриб чиқилган.|Заказ не найден или уже обработан.|Order not found or already reviewed.
Kategoriyani tanlang:|Категорияни танланг:|Выберите категорию:|Choose a category:
Mahsulotni tanlang:|Маҳсулотни танланг:|Выберите товар:|Choose a product:
Katalog hozircha bo‘sh. Yangi mahsulotlar keyinroq qo‘shiladi.|Каталог ҳозирча бўш. Янги маҳсулотлар кейинроқ қўшилади.|Каталог пока пуст. Новые товары появятся позже.|The catalog is empty for now. New products will be added later.
Bu kategoriyada mahsulot yo‘q.|Бу категорияда маҳсулот йўқ.|В этой категории нет товаров.|There are no products in this category.
Mahsulot topilmadi.|Маҳсулот топилмади.|Товар не найден.|Product not found.
Savatga qo‘shildi.|Саватга қўшилди.|Добавлено в корзину.|Added to cart.
Savatingiz bo‘sh.|Саватингиз бўш.|Ваша корзина пуста.|Your cart is empty.
Savat bo‘sh.|Сават бўш.|Корзина пуста.|Cart is empty.
Chek uchun faol buyurtma topilmadi.|Чек учун фаол буюртма топилмади.|Не найден активный заказ для чека.|No active order found for this receipt.
Chek administratorga tekshirish uchun yuborildi.|Чек администраторга текшириш учун юборилди.|Чек отправлен администратору на проверку.|Receipt sent to the administrator for review.
To‘lov xabari adminga yuborildi. Tasdiq javobini kuting.|Тўлов хабарномаси админга юборилди. Тасдиқни кутинг.|Уведомление об оплате отправлено администратору. Дождитесь подтверждения.|Payment notification sent to the admin. Please wait for confirmation.
To‘lov tekshiruvga yuborildi.|Тўлов текширувга юборилди.|Оплата отправлена на проверку.|Payment submitted for review.
To‘lov chekini rasm qilib yuboring.|Тўлов чекини расм қилиб юборинг.|Отправьте фото платёжного чека.|Send a photo of the payment receipt.
Chek yuborish uchun avval savatdan buyurtma yarating.|Чек юбориш учун аввал саватдан буюртма яратинг.|Сначала оформите заказ в корзине, чтобы отправить чек.|Place an order from the cart before sending a receipt.
ADMIN_IDS sozlanmagan. Chek saqlandi, ammo admin xabarini yuborib bo‘lmadi.|ADMIN_IDS созланмаган. Чек сақланди, аммо админга хабар юборилмади.|ADMIN_IDS не настроен. Чек сохранён, но уведомление админу не отправлено.|ADMIN_IDS is not configured. Receipt saved, but the admin could not be notified.
Admin ID sozlanmagan; to‘lovni tekshirishning imkoni yo‘q.|Админ ID созланмаган; тўловни текшириб бўлмайди.|ID администратора не настроен; проверить оплату невозможно.|Admin ID is not configured; payment cannot be reviewed.
Faol buyurtma topilmadi.|Фаол буюртма топилмади.|Активный заказ не найден.|Active order not found.
Faol buyurtma topilmadi yoki allaqachon yuborilgan.|Фаол буюртма топилмади ёки аллақачон юборилган.|Активный заказ не найден или уже отправлен.|Active order not found or already submitted.
Admin xabarnomasi yuborilmadi; qayta urinib ko‘ring.|Админга хабар юборилмади; қайта уриниб кўринг.|Не удалось уведомить администратора; попробуйте ещё раз.|Could not notify the admin; please try again.
Chek adminga yuborilmadi. Keyinroq to‘lovni qayta yuboring.|Чек админга юборилмади. Кейинроқ тўловни қайта юборинг.|Не удалось отправить чек админу. Отправьте оплату позже.|Receipt was not sent to the admin. Please resubmit later.
Buyurtma allaqachon ko‘rib chiqilgan.|Буюртма аллақачон кўриб чиқилган.|Заказ уже обработан.|Order has already been reviewed.
Xaridor ma’lumoti topilmadi.|Харидор маълумоти топилмади.|Данные покупателя не найдены.|Customer information not found.
Ruxsat yo‘q.|Рухсат йўқ.|Нет доступа.|Access denied.
Noma’lum amal.|Номаълум амал.|Неизвестное действие.|Unknown action.
Buyurtma rad etildi.|Буюртма рад этилди.|Заказ отклонён.|Order rejected.
Sizning to‘lovingiz tasdiqlandi va buyurtmangiz qabul qilindi! ✅|Тўловингиз тасдиқланди ва буюртмангиз қабул қилинди! ✅|Ваша оплата подтверждена, заказ принят! ✅|Your payment is confirmed and your order has been accepted! ✅
To‘lov tasdiqlandi; chek rasm va PDF ko‘rinishida yuborildi.|Тўлов тасдиқланди; чек расм ва PDF шаклида юборилди.|Оплата подтверждена; чек отправлен в виде изображения и PDF.|Payment approved; your receipt was sent as an image and PDF.
Chek yaratilmadi; buyurtma tasdiqlanmagan. Keyinroq qayta urinib ko‘ring.|Чек яратилмади; буюртма тасдиқланмади. Кейинроқ қайта уриниб кўринг.|Не удалось создать чек; заказ не подтверждён. Попробуйте позже.|Receipt could not be generated; the order was not approved. Please try again later.
Tasdiqlandi, ammo chekni yuborishda xatolik.|Тасдиқланди, аммо чекни юборишда хатолик.|Подтверждено, но не удалось отправить чек.|Approved, but receipt delivery failed.
To‘lov cheki|Тўлов чеки|ПЛАТЁЖНЫЙ ЧЕК|PAYMENT RECEIPT
Yuklab olish uchun PDF chek|Юклаб олиш учун PDF чек|PDF-чек для скачивания|Downloadable PDF receipt
Buyruqlar: /qr — QR yaratish yoki o‘qish, /card — vizitka yaratish, /cv — PDF rezyume yaratish.|Буйруқлар: /qr — QR яратиш ёки ўқиш, /card — визитка яратиш, /cv — PDF резюме яратиш.|Команды: /qr — создать или прочитать QR, /card — создать визитку, /cv — создать PDF-резюме.|Commands: /qr — create or read a QR code, /card — create a business card, /cv — create a PDF resume.
QR yaratish uchun matn/havola yoki QR rasmini yuboring:|QR яратиш учун матн/ҳавола ёки QR расмини юборинг:|Отправьте текст/ссылку для QR-кода или изображение QR-кода:|Send text/link for a QR code or an image of a QR code:
QR-kod tayyor.|QR-код тайёр.|QR-код готов.|QR code is ready.
QR ichidagi matn:|QR ичидаги матн:|Текст в QR-коде:|Text in the QR code:
Rasmda QR-kod topilmadi.|Расмда QR-код топилмади.|QR-код на изображении не найден.|No QR code found in the image.
Vizitkada ko‘rsatiladigan ismni yuboring:|Визиткада кўрсатиладиган исмни юборинг:|Введите имя для визитки:|Enter the name for the business card:
Kasbingizni yuboring:|Касбингизни юборинг:|Введите вашу профессию:|Enter your profession:
Vizitkangiz tayyor.|Визиткангиз тайёр.|Ваша визитка готова.|Your business card is ready.
Rezyume uchun to‘liq ismingiz:|Резюме учун тўлиқ исмингиз:|Полное имя для резюме:|Your full name for the resume:
Aloqa ma’lumotlari (telefon, email, manzil):|Алоқа маълумотлари (телефон, email, манзил):|Контактные данные (телефон, email, адрес):|Contact details (phone, email, address):
Qisqacha maqsad va ko‘nikmalaringiz:|Қисқача мақсад ва кўникмаларингиз:|Кратко опишите цель и навыки:|Briefly describe your objective and skills:
Ish tajribasi va ta’lim:|Иш тажрибаси ва таълим:|Опыт работы и образование:|Work experience and education:
PDF rezyume tayyor.|PDF резюме тайёр.|PDF-резюме готово.|PDF resume is ready.
Faqat PDF fayllar qabul qilinadi.|Фақат PDF файллар қабул қилинади.|Принимаются только PDF-файлы.|Only PDF files are accepted.
Har bir PDF 20 MB dan kichik bo‘lishi kerak.|Ҳар бир PDF 20 MB дан кичик бўлиши керак.|Размер каждого PDF должен быть меньше 20 МБ.|Each PDF must be smaller than 20 MB.
Birlashtirish uchun ko‘pi bilan 10 ta PDF yuboriladi.|Бирлаштириш учун кўпи билан 10 та PDF юборилади.|Для объединения можно отправить не более 10 PDF-файлов.|Send up to 10 PDF files to merge.
Birlashtirish uchun kamida 2 ta PDF yuboring.|Бирлаштириш учун камида 2 та PDF юборинг.|Для объединения отправьте не менее двух PDF-файлов.|Send at least 2 PDF files to merge.
PDF fayllar birlashtirildi.|PDF файллар бирлаштирилди.|PDF-файлы объединены.|PDF files merged.
PDF fayl yuboring.|PDF файл юборинг.|Отправьте PDF-файл.|Send a PDF file.
PDF 20 MB dan kichik bo‘lishi kerak.|PDF 20 MB дан кичик бўлиши керак.|Размер PDF должен быть меньше 20 МБ.|PDF must be smaller than 20 MB.
PDF sahifalari alohida fayllarga ajratildi.|PDF саҳифалари алоҳида файлларга ажратилди.|Страницы PDF разделены на отдельные файлы.|PDF pages have been split into separate files.
Sizdan:|Сиздан:|От вас:|From you:
Hammasi:|Ҳаммаси:|Итого:|Total:
Ichki balans:|Ички баланс:|Внутренний баланс:|Account balance:
Savat:|Сават:|Корзина:|Cart:
Yangi buyurtma #|Янги буюртма №|Новый заказ №|New order #
Buyurtma #|Буюртма №|Заказ №|Order #
Tasdiqlandi:|Тасдиқланди:|Подтверждено:|Approved:
rad etildi|рад этилди|отклонён|rejected
tasdiqlandi|тасдиқланди|подтверждён|approved
Xizmat:|Хизмат:|Услуга:|Service:
Xaridor:|Харидор:|Покупатель:|Customer:
Manzil:|Манзил:|Адрес:|Address:
Marosim:|Маросим:|Мероприятие:|Event:
Jami:|Жами:|Итого:|Total:
To‘lov holati:|Тўлов ҳолати:|Статус оплаты:|Payment status:
Kelishilgan narx:|Келишилган нарх:|Согласованная цена:|Agreed price:
Admin:|Админ:|Админ:|Admin:
Chek raqami:|Чек рақами:|Номер чека:|Receipt number:
Sana:|Сана:|Дата:|Date:
Telegram ID|Telegram ID|Telegram ID|Telegram ID
Yuklab olish uchun PDF chek #|Юклаб олиш учун PDF чек №|PDF-чек для скачивания №|Downloadable PDF receipt #
AI so‘rovi bajarilmadi: |AI сўрови бажарилмади: |Не удалось выполнить запрос ИИ: |AI request failed: 
Ovozli xabarni qayta ishlashda xatolik: |Овозли хабарни қайта ишлашда хатолик: |Ошибка обработки голосового сообщения: |Voice message processing error: 
Rasm tahlilida xatolik: |Расм таҳлилида хатолик: |Ошибка анализа изображения: |Image analysis error: 
Rasmni yuboring; caption sifatida PNG, JPG yoki WEBP yozing. Qo‘shimcha: /convertfile (audio/video/DOCX/PDF), /pdfmerge, /pdfsplit.|Расмни юборинг; caption сифатида PNG, JPG ёки WEBP ёзинг. Қўшимча: /convertfile (audio/video/DOCX/PDF), /pdfmerge, /pdfsplit.|Отправьте изображение и укажите PNG, JPG или WEBP в подписи. Дополнительно: /convertfile, /pdfmerge, /pdfsplit.|Send an image with PNG, JPG, or WEBP in the caption. Also: /convertfile, /pdfmerge, /pdfsplit.
Qaysi format kerak? PNG, JPG yoki WEBP deb yuboring.|Қайси формат керак? PNG, JPG ёки WEBP деб юборинг.|Какой формат нужен? Отправьте PNG, JPG или WEBP.|Which format do you need? Send PNG, JPG, or WEBP.
Avval rasm yuboring, so‘ng PNG, JPG yoki WEBP formatini tanlang.|Аввал расм юборинг, сўнг PNG, JPG ёки WEBP форматини танланг.|Сначала отправьте изображение, затем выберите PNG, JPG или WEBP.|Send an image first, then choose PNG, JPG, or WEBP.
Rasmni o‘girishda xatolik: |Расмни ўгиришда хатолик: |Ошибка преобразования изображения: |Image conversion error: 
 tanlandi. Endi konvertatsiya qilinadigan faylni yuboring.| танланди. Энди конвертация қилинадиган файлни юборинг.| выбран. Теперь отправьте файл для конвертации.| selected. Now send the file to convert.
Formatni yuboring: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx yoki docx2pdf.|Форматни юборинг: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx ёки docx2pdf.|Отправьте формат: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx или docx2pdf.|Send a format: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx, or docx2pdf.
Formatni tanlang: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx yoki docx2pdf.|Форматни танланг: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx ёки docx2pdf.|Выберите формат: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx или docx2pdf.|Choose a format: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx, or docx2pdf.
Fayl hajmi Telegram Bot API uchun 20 MB dan kichik bo‘lishi kerak.|Файл ҳажми Telegram Bot API учун 20 MB дан кичик бўлиши керак.|Размер файла должен быть меньше 20 МБ для Telegram Bot API.|File must be smaller than 20 MB for the Telegram Bot API.
Konvertatsiya uchun fayl topilmadi. /convertfile bilan qayta boshlang.|Конвертация учун файл топилмади. /convertfile билан қайта бошланг.|Файл для конвертации не найден. Начните заново командой /convertfile.|No file to convert. Start again with /convertfile.
Audio voice formatiga o‘girildi.|Аудио voice форматига ўгирилди.|Аудио преобразовано в формат voice.|Audio converted to Telegram voice format.
Faylni konvertatsiya qilib bo‘lmadi: |Файлни конвертация қилиб бўлмади: |Не удалось конвертировать файл: |File conversion failed: 
PDF birlashtirishda xatolik: |PDF бирлаштиришда хатолик: |Ошибка объединения PDF: |PDF merge error: 
PDF ajratishda xatolik: |PDF ажратишда хатолик: |Ошибка разделения PDF: |PDF split error: 
Konvertatsiya tayyor: |Конвертация тайёр: |Конвертация завершена: |Conversion complete: 
Rasm {image_format} formatiga o‘girildi.|Расм {image_format} форматига ўгирилди.|Изображение преобразовано в формат {image_format}.|Image converted to {image_format}.
Faylni caption bilan yuboring: mp3, ogg (Telegram voice), gif, compress, png, jpg, webp, pdf2docx yoki docx2pdf. Caption bo‘lmasa, keyin tanlaysiz.|Файлни caption билан юборинг: mp3, ogg (Telegram voice), gif, compress, png, jpg, webp, pdf2docx ёки docx2pdf. Caption бўлмаса, кейин танлайсиз.|Отправьте файл с подписью: mp3, ogg (Telegram voice), gif, compress, png, jpg, webp, pdf2docx или docx2pdf.|Send a file with caption: mp3, ogg, gif, compress, png, jpg, webp, pdf2docx, or docx2pdf.
Instagram, TikTok, YouTube, Pinterest yoki X havolasini yuboring.\nFaqat MP3 audio uchun: mp3 https://... \nPlatforma cheklovlari va mualliflik huquqlariga rioya qiling.|Instagram, TikTok, YouTube, Pinterest ёки X ҳаволасини юборинг.\nФақат MP3 аудио учун: mp3 https://...\nПлатформа қоидалари ва муаллифлик ҳуқуқларига риоя қилинг.|Отправьте ссылку Instagram, TikTok, YouTube, Pinterest или X.\nТолько аудио MP3: mp3 https://...\nСоблюдайте ограничения платформ и авторские права.|Send an Instagram, TikTok, YouTube, Pinterest, or X link.\nFor MP3 audio only: mp3 https://...\nFollow platform restrictions and copyright rules.
Havola qayta ishlanmoqda, kuting…|Ҳавола қайта ишланмоқда, кутинг…|Ссылка обрабатывается, подождите…|Processing the link, please wait…
Havola yaroqsiz yoki qo‘llab-quvvatlanmaydi. HTTPS platforma havolasini yuboring.|Ҳавола нотўғри ёки қўллаб-қувватланмайди. HTTPS платформа ҳаволасини юборинг.|Ссылка недействительна или не поддерживается. Отправьте ссылку платформы с HTTPS.|Invalid or unsupported link. Send an HTTPS link from a supported platform.
Yuklab bo‘lmadi: |Юклаб бўлмади: |Не удалось скачать: |Download failed: 
Foydalanuvchilar: |Фойдаланувчилар: |Пользователи: |Users: 
Faol (1 kun): |Фаол (1 кун): |Активны (1 день): |Active (1 day): 
Faol (7 kun): |Фаол (7 кун): |Активны (7 дней): |Active (7 days): 
Buyurtmalar: |Буюртмалар: |Заказы: |Orders: 
Tekshirilayotgan cheklar: |Текширилаётган чеклар: |Чеки на проверке: |Receipts under review: 
, xato: |, хато: |, ошибок: |, failed: 
Mahsulot nomini yuboring:|Маҳсулот номини юборинг:|Отправьте название товара:|Send the product name:
 foydalanuvchiga | фойдаланувчига | пользователю | points to user 
Foydalanish: /ban USER_ID|Фойдаланиш: /ban USER_ID|Использование: /ban USER_ID|Usage: /ban USER_ID
Foydalanish: /unban USER_ID|Фойдаланиш: /unban USER_ID|Использование: /unban USER_ID|Usage: /unban USER_ID
User ID faqat raqamlardan iborat bo‘lishi kerak.|User ID фақат рақамлардан иборат бўлиши керак.|ID пользователя должен содержать только цифры.|User ID must contain digits only.
AI yordamchiga xush kelibsiz. Savol, matn yoki rasm/ovozli xabar yuboring.|AI ёрдамчисига хуш келибсиз. Савол, матн ёки расм/овозли хабар юборинг.|Добро пожаловать в AI-помощник. Отправьте вопрос, текст, изображение или голосовое сообщение.|Welcome to the AI assistant. Send a question, text, image, or voice message.
Savolingizni yoki tahrirlash/tarjima matnini yuboring. Rasm yoki ovozli xabarni ham yuborishingiz mumkin.|Саволингизни ёки таҳрир/таржима матнини юборинг. Расм ёки овозли хабар ҳам юборишингиз мумкин.|Отправьте вопрос, текст для редактирования или перевода. Можно также отправить изображение или голосовое сообщение.|Send a question or text to edit/translate. You can also send an image or voice message.
Vazifalar:|Вазифалар:|Задачи:|Tasks:
Eslatma:|Эслатма:|Напоминание:|Reminder:
Vazifa matnini yuboring:|Вазифа матнини юборинг:|Отправьте текст задачи:|Send the task text:
Vazifa qo‘shildi. Ro‘yxat: /todos|Вазифа қўшилди. Рўйхат: /todos|Задача добавлена. Список: /todos|Task added. List: /todos
Vazifalar ro‘yxati bo‘sh.|Вазифалар рўйхати бўш.|Список задач пуст.|Your task list is empty.
Bajarilganini belgilash uchun vazifaga bosing:|Бажарилганини белгилаш учун вазифага босинг:|Нажмите на задачу, чтобы отметить её выполненной:|Tap a task to mark it complete:
Vazifa yangilandi.|Вазифа янгиланди.|Задача обновлена.|Task updated.
Vazifa 1–500 belgi bo‘lishi kerak.|Вазифа 1–500 белги бўлиши керак.|Задача должна содержать от 1 до 500 символов.|Task must be 1–500 characters.
Vazifa topilmadi.|Вазифа топилмади.|Задача не найдена.|Task not found.
Eslatma matnini yuboring:|Эслатма матнини юборинг:|Отправьте текст напоминания:|Send reminder text:
Eslatma 1–500 belgi bo‘lishi kerak.|Эслатма 1–500 белги бўлиши керак.|Напоминание должно содержать от 1 до 500 символов.|Reminder must be 1–500 characters.
Sana va vaqtni YYYY-MM-DD HH:MM ko‘rinishida yuboring (Toshkent vaqti).|Сана ва вақтни YYYY-MM-DD HH:MM кўринишида юборинг (Тошкент вақти).|Введите дату и время в формате YYYY-MM-DD HH:MM (время Ташкента).|Send the date and time as YYYY-MM-DD HH:MM (Tashkent time).
Sana formati xato. Masalan: 2026-10-09 09:30|Сана формати хато. Масалан: 2026-10-09 09:30|Неверный формат даты. Например: 2026-10-09 09:30|Invalid date format. Example: 2026-10-09 09:30
Eslatma vaqti kelajakda bo‘lishi kerak.|Эслатма вақти келажакда бўлиши керак.|Время напоминания должно быть в будущем.|Reminder time must be in the future.
Eslatma |Эслатма |Напоминание |Reminder 
 ga belgilandi.| га белгиланди.| запланировано.| scheduled.
Kuzatmoqchi bo‘lgan odat nomini yuboring:|Кузатмоқчи бўлган одат номини юборинг:|Введите название привычки для отслеживания:|Send the name of the habit to track:
Odat qo‘shildi. Bugungi belgilash uchun /habits buyrug‘idan foydalaning.|Одат қўшилди. Бугун белгилаш учун /habits буйруғидан фойдаланинг.|Привычка добавлена. Отметьте её за сегодня командой /habits.|Habit added. Use /habits to mark it for today.
Bu odat allaqachon mavjud.|Бу одат аллақачон мавжуд.|Такая привычка уже есть.|This habit already exists.
Bugungi odatlarni belgilang:|Бугунги одатларни белгиланг:|Отметьте привычки за сегодня:|Mark today’s habits:
Odatlar ro‘yxati bo‘sh. /habit bilan qo‘shing.|Одатлар рўйхати бўш. /habit билан қўшинг.|Список привычек пуст. Добавьте привычку командой /habit.|No habits yet. Add one with /habit.
Odat topilmadi.|Одат топилмади.|Привычка не найдена.|Habit not found.
Bugun allaqachon belgilangan.|Бугун аллақачон белгиланган.|Уже отмечено за сегодня.|Already marked for today.
Bugun bajarildi! ✅|Бугун бажарилди! ✅|Выполнено сегодня! ✅|Completed today! ✅
 — bugun bajarildi| — бугун бажарилди| — выполнено сегодня| — completed today
Rejalar: /todo — vazifa qo‘shish, /todos — ro‘yxat, /remind — eslatma, /habit — odat qo‘shish, /habits — odatlarni belgilash.|Режалар: /todo — вазифа қўшиш, /todos — рўйхат, /remind — эслатма, /habit — одат қўшиш, /habits — одатларни белгилаш.|Планирование: /todo — добавить задачу, /todos — список, /remind — напоминание, /habit — добавить привычку, /habits — отметить привычки.|Planning: /todo — add a task, /todos — list tasks, /remind — reminder, /habit — add a habit, /habits — mark habits.
Amal bekor qilindi.|Амал бекор қилинди.|Операция отменена.|Operation cancelled.
 ball. Joriy balans:| балл. Жорий баланс:| баллов. Текущий баланс:| points. Current balance:
🎲 /dice — zar o‘yini (Telegram dice), /quiz — savol, /leaderboard — reyting.|🎲 /dice — кубик ўйини (Telegram dice), /quiz — савол, /leaderboard — рейтинг.|🎲 /dice — кубик, /quiz — викторина, /leaderboard — рейтинг.|🎲 /dice — dice game, /quiz — quiz, /leaderboard — leaderboard.
Zar natijasi: |Кубик натижаси: |Результат броска: |Dice result: 
Kompyuter ko‘rishda tasvirni qayta ishlash uchun qaysi kutubxona keng qo‘llanadi?|Компьютер кўришида тасвирни қайта ишлаш учун қайси кутубхона кенг қўлланади?|Какая библиотека широко используется для обработки изображений в компьютерном зрении?|Which library is widely used for image processing in computer vision?
🏆 Peshqadamlar:|🏆 Пешқадамлар:|🏆 Лидеры:|🏆 Leaderboard:
Hozircha natijalar yo‘q.|Ҳозирча натижалар йўқ.|Пока нет результатов.|No scores yet.
Buyurtmalar soni:|Буюртмалар сони:|Количество заказов:|Order count:
To‘lov xizmati vaqtincha ishlamayapti.|Тўлов хизмати вақтинча ишламаяпти.|Платёжный сервис временно недоступен.|Payment service is temporarily unavailable.
📇 Asosiy menyu|📇 Асосий меню|📇 Главное меню|📇 Main menu
Kategoriya|Категория|Категория|Category
Miqdor|Миқдор|Количество|Quantity
Tayyor.|Тайёр.|Готово.|Ready.
Fayl tayyor.|Файл тайёр.|Файл готов.|File ready.
Qabul qilindi.|Қабул қилинди.|Принято.|Received.
To‘lov kartalari:|Тўлов карталари:|Карты для оплаты:|Payment cards:
To‘lanishi:|Тўланиши:|К оплате:|Amount due:
Ichki balansdan:|Ички балансдан:|С баланса:|Balance applied:
To‘lovdan so‘ng tugmani bosing yoki chek rasmini yuboring.|Тўловдан сўнг тугмани босинг ёки чек расмини юборинг.|После оплаты нажмите кнопку или отправьте фото чека.|After paying, tap the button or send a receipt photo.
Ichki balans buyurtmani to‘liq qopladi. Tasdiq uchun tugmani bosing.|Ички баланс буюртмани тўлиқ қоплади. Тасдиқлаш учун тугмани босинг.|Баланс полностью покрывает заказ. Нажмите кнопку для подтверждения.|Your balance covers the full order. Tap the button to confirm.
buyurtma yaratildi.|буюртма яратилди.|заказ создан.|order created.
Sana va vaqt|Сана ва вақт|Дата и время|Date and time
Narx:|Нарх:|Цена:|Price:
PAID / TO‘LANDI|PAID / ТЎЛАНДИ|ОПЛАЧЕНО|PAID
Soat miqdori 1 dan 24 gacha bo‘lgan butun son bo‘lsin.|Соат миқдори 1 дан 24 гача бўлган бутун сон бўлсин.|Количество часов должно быть целым числом от 1 до 24.|Hours must be a whole number from 1 to 24.
Buyurtmangiz #|Буюртмангиз №|Ваш заказ №|Your order #
 adminga yuborildi. Narx kelishilgach, to‘lov rekvizitlari yuboriladi.| админга юборилди. Нарх келишилгач, тўлов реквизитлари юборилади.| отправлен администратору. После согласования цены будут отправлены реквизиты для оплаты.| sent to the admin. Payment details will be sent after the price is agreed.
🆕 Narxi kelishiladigan xizmat buyurtmasi #|🆕 Нархи келишиладиган хизмат буюртмаси №|🆕 Заказ услуги с согласованием цены №|🆕 Service order requiring price agreement #
 uchun narxni so‘mda yuboring:| учун нархни сўмда юборинг:| введите цену в сумах:| enter the price in UZS:
 учун | учун | для заказа №| for order #
 so‘m belgilandi.| сўм белгиланди.| сум установлена.| UZS set.
 uchun to‘lov cheki.| учун тўлов чеки.| — чек оплаты.| — payment receipt.
 tasdiqlandi, lekin mijozga chek yuborilmadi. Bot foydalanuvchiga xabar yubora olishini tekshiring.| тасдиқланди, лекин мижозга чек юборила олмади. Бот фойдаланувчига хабар юборишини текширинг.| подтверждён, но чек не отправлен клиенту. Проверьте, может ли бот отправлять сообщения пользователю.| approved, but the receipt was not delivered. Check that the bot can message the user.
: tasdiqlandi — |: тасдиқланди — |: подтверждён — |: approved — 
: rad etildi|: рад этилди|: отклонён|: rejected
Rasm |Расм |Изображение |Image 
 formatiga o‘girildi.| форматига ўгирилди.| преобразовано в формат.| converted to 
 ta). Tugatish uchun /finish.| та). Якунлаш учун /finish.| шт.). Для завершения введите /finish.| file(s)). Send /finish when done.
PDF qo‘shildi (|PDF қўшилди (|PDF добавлен (|PDF added (
2–10 ta PDF yuboring, so‘ng /finish yozing.|2–10 та PDF юборинг, сўнг /finish ёзинг.|Отправьте от 2 до 10 PDF-файлов, затем введите /finish.|Send 2–10 PDF files, then type /finish.
Sahifalarga ajratiladigan PDF faylni yuboring (100 sahifagacha).|Саҳифаларга ажратиладиган PDF файлини юборинг (100 саҳифагача).|Отправьте PDF для разделения (до 100 страниц).|Send a PDF to split (up to 100 pages).
Unknown language.|Номаълум тил.|Неизвестный язык.|Unknown language.
Assalomu alaykum, |Ассалому алайкум, |Здравствуйте, |Hello, 
! Kerakli bo‘limni tanlang.|! Керакли бўлимни танланг.|! Выберите нужный раздел.|! Choose a section.
Hisobingiz bloklangan. Yordam uchun administratorga murojaat qiling.|Ҳисобингиз блокланган. Ёрдам учун администраторга мурожаат қилинг.|Ваш аккаунт заблокирован. Обратитесь к администратору.|Your account is blocked. Contact the administrator.
Bo‘limni pastdagi menyudan tanlang. Ichki amallar uchun /cancel buyrug‘i holatni bekor qiladi.|Бўлимни пастдаги менюдан танланг. Ички амаллар учун /cancel буйруғи ҳолатни бекор қилади.|Выберите раздел в меню ниже. Команда /cancel отменяет текущее действие.|Choose a section from the menu below. Use /cancel to stop the current action.
Yordam va admin bilan aloqa:|Ёрдам ва админ билан алоқа:|Помощь и связь с администратором:|Help and admin contact:
Telefon:|Телефон:|Телефон:|Phone:
Do‘stlaringizni taklif qiling:|Дўстларингизни таклиф қилинг:|Приглашайте друзей:|Invite your friends:
Har bir yangi foydalanuvchi uchun |Ҳар бир янги фойдаланувчи учун |За каждого нового пользователя начисляется |Earn for each new user invited: 
 ball. Joriy balans: | балл. Жорий баланс: | баллов. Текущий баланс: | points. Current balance: 
Asosiy menyu:|Асосий меню:|Главное меню:|Main menu:
Tarqatiladigan matnni yuboring:|Тарқатиладиган матнни юборинг:|Отправьте текст для рассылки:|Send the message to broadcast:
Ixtiyoriy inline tugma yuboring: Tugma matni \| https://havola. Tugmasiz — /skip.|Ихтиёрий inline тугма юборинг: Тугма матни \| https://ҳавола. Тугмасиз — /skip.|Отправьте необязательную inline-кнопку: текст кнопки \| https://ссылка. Без кнопки — /skip.|Send an optional inline button: button text \| https://link. No button — /skip.
Mahsulot kategoriyasini yuboring:|Маҳсулот категориясини юборинг:|Отправьте категорию товара:|Send the product category:
Mahsulot tavsifi:|Маҳсулот тавсифи:|Описание товара:|Product description:
Narxini butun so‘mda kiriting:|Нархини бутун сўмда киритинг:|Введите цену целым числом в сумах:|Enter the price as a whole number in UZS:
Mahsulot rasmini yuboring yoki rasmsiz qo‘shish uchun /skip yozing.|Маҳсулот расмини юборинг ёки расмсиз қўшиш учун /skip ёзинг.|Отправьте фото товара или введите /skip, чтобы добавить без фото.|Send a product photo or type /skip to add it without one.
Mahsulot katalogga qo‘shildi.|Маҳсулот каталогга қўшилди.|Товар добавлен в каталог.|Product added to the catalog.
Mahsulot rasmsiz katalogga qo‘shildi.|Маҳсулот расмсиз каталогга қўшилди.|Товар добавлен в каталог без фото.|Product added to the catalog without a photo.
Foydalanuvchi bloklandi.|Фойдаланувчи блокланди.|Пользователь заблокирован.|User blocked.
Foydalanuvchi blokdan chiqarildi.|Фойдаланувчи блокдан чиқарилди.|Пользователь разблокирован.|User unblocked.
Bonus beriladigan Telegram user ID:|Бонус бериладиган Telegram user ID:|Telegram ID пользователя для начисления бонуса:|Telegram user ID to receive the bonus:
Qo‘shiladigan ball miqdori:|Қўшиладиган балл миқдори:|Количество начисляемых баллов:|Number of points to add:
Foydalanuvchilar:|Фойдаланувчилар:|Пользователи:|Users:
Faol (1 kun):|Фаол (1 кун):|Активны (1 день):|Active (1 day):
Faol (7 kun):|Фаол (7 кун):|Активны (7 дней):|Active (7 days):
Buyurtmalar:|Буюртмалар:|Заказы:|Orders:
Tekshirilayotgan cheklar:|Текширилаётган чеклар:|Чеки на проверке:|Receipts pending review:
Tarqatish yakunlandi. Yuborildi:|Тарқатиш якунланди. Юборилди:|Рассылка завершена. Отправлено:|Broadcast complete. Sent:
 ball berildi.| балл берилди.| баллов начислено.| points awarded.
Kategoriya nomi bo‘sh bo‘lmasligi kerak.|Категория номи бўш бўлмаслиги керак.|Название категории не может быть пустым.|Category name cannot be empty.
Kategoriya nomi|Категория номи|Название категории|Category name
Mahsulot nomi|Маҳсулот номи|Название товара|Product name
Format: Tugma matni \| https://havola yoki /skip.|Формат: тугма матни \| https://ҳавола ёки /skip.|Формат: текст кнопки \| https://ссылка или /skip.|Format: button text \| https://link or /skip.
Tugma havolasi https:// bilan boshlanishi kerak.|Тугма ҳаволаси https:// билан бошланиши керак.|Ссылка кнопки должна начинаться с https://.|Button URL must start with https://.
Narx manfiy bo‘lmagan butun son bo‘lishi kerak.|Нарх манфий бўлмаган бутун сон бўлиши керак.|Цена должна быть целым неотрицательным числом.|Price must be a non-negative whole number.
Foydalanuvchi topilmadi.|Фойдаланувчи топилмади.|Пользователь не найден.|User not found.
Miqdor musbat butun son bo‘lishi kerak.|Миқдор мусбат бутун сон бўлиши керак.|Количество должно быть положительным целым числом.|Quantity must be a positive whole number.
Format|Формат|Формат|Format
Tarqatish yakunlandi. Yuborildi: |Тарқатиш якунланди. Юборилди: |Рассылка завершена. Отправлено: |Broadcast complete. Sent: 
ga belgilandi.|га белгиланди.|назначено на|scheduled for
— bugun bajarildi|— бугун бажарилди|— выполнено сегодня|— completed today
To‘lov rekvizitlari sozlanmagan.|Тўлов реквизитлари созланмаган.|Реквизиты для оплаты не настроены.|Payment details are not configured.
Mahsulot/xizmat tafsilotlari saqlanmagan|Маҳсулот/хизмат тафсилотлари сақланмаган|Данные товара/услуги не сохранены|Product/service details were not saved
Ichki balansdan to‘lov: −|Ички балансдан тўлов: −|Оплачено с внутреннего баланса: −|Paid from account balance: −
💳 To‘lov tekshiruvi — buyurtma #|💳 Тўлов текшируви — буюртма №|💳 Проверка оплаты — заказ №|💳 Payment review — order #
Telegram ID:|Telegram ID:|Telegram ID:|Telegram ID:
Username: @|Фойдаланувчи номи: @|Имя пользователя: @|Username: @
To‘lanadigan summa:|Тўланадиган сумма:|Сумма к оплате:|Amount due:
yoki foydalanuvchi topilmadi.|ёки фойдаланувчи топилмади.|или пользователь не найден.|or the user was not found.
Xizmat buyurtmangiz #|Хизмат буюртмангиз №|Ваш заказ услуги №|Your service order #
admin tomonidan rad etildi.|админ томонидан рад этилди.|отклонён администратором.|was rejected by the admin.
 bo‘yicha to‘lov tasdiqlanmadi.| бўйича тўлов тасдиқланмади.|: оплата не подтверждена.|: payment was not approved.
Yordam uchun @|Ёрдам учун @|Для помощи: @|For help: @
ga yozing.|га ёзинг.|.|.
Zar natijasi:|Зар натижаси:|Результат броска:|Dice result:
 ball. Ballaringiz reytingga qo‘shildi.| балл. Балларингиз рейтингга қўшилди.| очков. Результат добавлен в рейтинг.| points. Added to your leaderboard score.
Foydalanuvchi|Фойдаланувчи|Пользователь|User
Fayl hajmi |Файл ҳажми |Размер файла |File size 
MB limitidan katta.|MB лимитидан катта.|превышает лимит MB.|exceeds the MB limit.
Yuklab bo‘lmadi:|Юклаб бўлмади:|Не удалось скачать:|Download failed:
Faylni konvertatsiya qilib bo‘lmadi:|Файлни конвертация қилиб бўлмади:|Не удалось преобразовать файл:|Could not convert the file:
Konvertatsiya tayyor:|Конвертация тайёр:|Конвертация завершена:|Conversion complete:
1 kunlik to‘y (1 ta kamera)|1 кунлик тўй (1 та камера)|Свадьба на 1 день (1 камера)|1-day wedding (1 camera)
2 kunlik to‘y (1 ta kamera)|2 кунлик тўй (1 та камера)|Свадьба на 2 дня (1 камера)|2-day wedding (1 camera)
Qisqa marosim — soatiga|Қисқа маросим — соатига|Короткое мероприятие — почасово|Short event — hourly
Vizitka tayyorlash|Визитка тайёрлаш|Создание визитки|Business card design
Logo xizmati|Лого хизмати|Услуги по созданию логотипа|Logo design
Reklama xizmati|Реклама хизмати|Рекламные услуги|Advertising services
AI xizmatlari|AI хизматлари|Услуги ИИ|AI services
— narx kelishiladi|— нарх келишилади|— цена договорная|— price by agreement
admin bilan kelishiladi|админ билан келишилади|согласуется с администратором|agreed with the admin
Chek raqami|Чек рақами|Номер чека|Receipt number
Sana|Сана|Дата|Date
Xaridor|Харидор|Покупатель|Customer
Xarid / xizmat|Харид / хизмат|Покупка / услуга|Purchase / service
Jami|Жами|Итого|Total
To‘lov holati|Тўлов ҳолати|Статус оплаты|Payment status
Telefon|Телефон|Телефон|Phone
TO‘LOV CHEKI|ТЎЛОВ ЧЕКИ|ПЛАТЁЖНЫЙ ЧЕК|PAYMENT RECEIPT
 so‘m| сўм| сум| UZS
 soat)| соат)| час)| hours)
 kun| кун| дн.| days
 (Toshkent)|(Тошкент)|(Ташкент)|(Tashkent)
Rasm tahlilida xatolik:|Расм таҳлилида хатолик:|Ошибка анализа изображения:|Image analysis error:
AI so‘rovi bajarilmadi:|AI сўрови бажарилмади:|Не удалось выполнить запрос ИИ:|AI request failed:
Ovozli xabarni qayta ishlashda xatolik:|Овозли хабарни қайта ишлашда хатолик:|Ошибка обработки голосового сообщения:|Voice message processing error:
🎙 Tanilgan matn: |🎙 Танилган матн: |🎙 Распознанный текст: |🎙 Recognized text: 
PDF birlashtirishda xatolik:|PDF бирлаштиришда хатолик:|Ошибка объединения PDF:|PDF merge error:
PDF ajratishda xatolik:|PDF ажратишда хатолик:|Ошибка разделения PDF:|PDF split error:
Rasmni o‘girishda xatolik:|Расмни ўгиришда хатолик:|Ошибка преобразования изображения:|Image conversion error:
tanlandi. Endi konvertatsiya qilinadigan faylni yuboring.|танланди. Энди конвертация қилинадиган файлни юборинг.|выбран. Теперь отправьте файл для конвертации.|selected. Now send the file to convert.
 bilan admin bog‘lanishini kuting.| билан админ боғланишини кутинг.|, дождитесь связи с администратором.|; wait for the admin to contact you.
Admin buyruqlari: /stats, /broadcast, /addproduct, /ban ID, /unban ID, /bonus.|Админ буйруқлари: /stats, /broadcast, /addproduct, /ban ID, /unban ID, /bonus.|Команды администратора: /stats, /broadcast, /addproduct, /ban ID, /unban ID, /bonus.|Admin commands: /stats, /broadcast, /addproduct, /ban ID, /unban ID, /bonus.
Zar|Зар|Кости|Dice
Slot|Слот|Слоты|Slots
Bowling|Боулинг|Боулинг|Bowling
Futbol|Футбол|Футбол|Football
 o‘yini:| ўйини:| — игра| game:
"""


def _build_catalog() -> dict[str, dict[str, str]]:
    catalog = {language: {} for language in LANGUAGES}
    for raw_line in _RAW_CATALOG.strip().splitlines():
        columns = re.split(r"(?<!\\)\|", raw_line)
        if len(columns) != 4:
            raise ValueError(f"Invalid translation entry: {raw_line!r}")
        columns = [
            column.replace(r"\|", "|").replace(r"\n", "\n")
            for column in columns
        ]
        if columns[0] in catalog["uz_latn"]:
            raise ValueError(f"Duplicate translation source: {columns[0]!r}")
        for language, translation in zip(LANGUAGES, columns):
            catalog[language][columns[0]] = translation
    return catalog


CATALOG = _build_catalog()
_SORTED_SOURCES = sorted(CATALOG["uz_latn"], key=len, reverse=True)
_TRANSLATION_TO_SOURCE = {
    language: {translation: source for source, translation in CATALOG[language].items()}
    for language in LANGUAGES
}
current_language: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bot_language", default="uz_latn"
)


async def get_user_language(user_id: int) -> str:
    async with SessionLocal() as session:
        language = await session.scalar(select(User.language).where(User.id == user_id))
    return language if language in LANGUAGES else "uz_latn"


def translate_text(text: str, language: str) -> str:
    if language not in LANGUAGES or language == "uz_latn" or not text:
        return text
    exact = CATALOG[language].get(text)
    if exact is not None:
        return exact
    reverse = _TRANSLATION_TO_SOURCE[language].get(text)
    if reverse is not None:
        return CATALOG[language][reverse]
    result_lines: list[str] = []
    for line in text.split("\n"):
        translated = CATALOG[language].get(line)
        if translated is None:
            translated = line
            for source in _SORTED_SOURCES:
                if source in translated:
                    translated = translated.replace(source, CATALOG[language][source])
        result_lines.append(translated)
    return "\n".join(result_lines)


def menu_text(action: str, language: str) -> str:
    return CATALOG[language].get(action, action)


class MenuAction(Filter):
    def __init__(self, action: str) -> None:
        self.action = action
        self.accepted_texts = {
            menu_text(action, language) for language in LANGUAGES
        }

    async def __call__(self, message: Message) -> bool:
        return bool(message.text and message.text in self.accepted_texts)


async def localize_api_request(handler: Any, bot: Any, method: Any) -> Any:
    chat_id = getattr(method, "chat_id", None)
    if isinstance(chat_id, int) and chat_id > 0:
        language = await get_user_language(chat_id)
    else:
        language = current_language.get()
    for field in ("text", "caption", "question"):
        value = getattr(method, field, None)
        if isinstance(value, str):
            setattr(method, field, translate_text(value, language))
    options = getattr(method, "options", None)
    if options:
        method.options = [translate_text(option, language) for option in options]
    markup = getattr(method, "reply_markup", None)
    if markup is not None and language != "uz_latn":
        markup = markup.model_copy(deep=True)
        if isinstance(markup, ReplyKeyboardMarkup):
            for row in markup.keyboard:
                for button in row:
                    button.text = translate_text(button.text, language)
        elif hasattr(markup, "inline_keyboard"):
            for row in markup.inline_keyboard:
                for button in row:
                    button.text = translate_text(button.text, language)
        method.reply_markup = markup
    logger.debug("Localized Telegram method %s for language %s", type(method).__name__, language)
    return await handler(bot, method)
