import asyncio
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter


def _prepare_dir() -> Path:
    path = Path("generated")
    path.mkdir(exist_ok=True)
    return path


def create_qr(text: str) -> str:
    output = _prepare_dir() / f"{uuid.uuid4().hex}.png"
    qrcode.make(text).save(output)
    return str(output)


def convert_image(source: str, image_format: str = "PNG") -> str:
    output = _prepare_dir() / f"{uuid.uuid4().hex}.{image_format.lower()}"
    with Image.open(source) as image:
        if image_format.upper() in {"JPEG", "JPG"} and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(output, format="JPEG" if image_format.upper() == "JPG" else image_format.upper())
    return str(output)


def compress_image(source: str) -> str:
    output = _prepare_dir() / f"{uuid.uuid4().hex}.webp"
    with Image.open(source) as image:
        image.thumbnail((1600, 1600))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        image.save(output, "WEBP", quality=75, method=6)
    return str(output)


def merge_pdfs(sources: list[str]) -> str:
    writer = PdfWriter()
    for source in sources:
        writer.append(source)
    output = _prepare_dir() / f"{uuid.uuid4().hex}.pdf"
    with output.open("wb") as target:
        writer.write(target)
    return str(output)


def split_pdf(source: str) -> str:
    reader = PdfReader(source)
    if len(reader.pages) > 100:
        raise ValueError("Bir PDF uchun 100 sahifa limiti mavjud.")
    output_dir = _prepare_dir() / uuid.uuid4().hex
    output_dir.mkdir()
    for index, page in enumerate(reader.pages, 1):
        writer = PdfWriter()
        writer.add_page(page)
        with (output_dir / f"page-{index:03}.pdf").open("wb") as target:
            writer.write(target)
    archive = _prepare_dir() / f"{output_dir.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        for item in output_dir.iterdir():
            target.write(item, item.name)
    shutil.rmtree(output_dir)
    return str(archive)


async def _run_process(*args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Konvertatsiya 3 daqiqadan oshdi va to‘xtatildi.") from None
    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"Tashqi konvertor xatosi: {detail}")


async def convert_media(source: str, mode: str) -> str:
    output_dir = _prepare_dir()
    output = output_dir / f"{uuid.uuid4().hex}.{mode}"
    if mode in {"png", "jpg", "jpeg", "webp"}:
        return await asyncio.to_thread(convert_image, source, mode.upper())
    if mode == "compress":
        return await asyncio.to_thread(compress_image, source)
    ffmpeg = shutil.which("ffmpeg")
    if mode in {"mp3", "ogg", "gif"}:
        if not ffmpeg:
            raise RuntimeError("Audio/video konvertatsiyasi uchun FFmpeg o‘rnatib PATH ga qo‘shing.")
        if mode == "mp3":
            await _run_process(ffmpeg, "-y", "-i", source, "-vn", "-codec:a", "libmp3lame", str(output))
        elif mode == "ogg":
            await _run_process(ffmpeg, "-y", "-i", source, "-vn", "-c:a", "libopus", "-b:a", "64k", "-f", "ogg", str(output))
        else:
            await _run_process(
                ffmpeg, "-y", "-i", source, "-vf", "fps=12,scale=480:-1:flags=lanczos",
                "-loop", "0", str(output),
            )
        return str(output)
    if mode == "docx2pdf":
        office = shutil.which("soffice") or shutil.which("libreoffice")
        if not office:
            raise RuntimeError("DOCX→PDF uchun LibreOffice (soffice) o‘rnatilishi kerak.")
        with tempfile.TemporaryDirectory() as output_dir:
            await _run_process(
                office, "--headless", "--convert-to", "pdf", "--outdir", output_dir, source
            )
            converted = Path(output_dir) / f"{Path(source).stem}.pdf"
            if not converted.exists():
                raise RuntimeError("LibreOffice PDF faylini yaratmadi.")
            return await asyncio.to_thread(_copy_output, converted, output)
    if mode == "pdf2docx":
        return await asyncio.to_thread(_pdf_to_docx, source, output)
    raise ValueError("Noma’lum konvertatsiya turi.")


def _copy_output(source: Path, destination: Path) -> str:
    shutil.copy2(source, destination)
    return str(destination)


def _pdf_to_docx(source: str, destination: Path) -> str:
    from pdf2docx import Converter

    converter = Converter(source)
    try:
        converter.convert(str(destination))
    finally:
        converter.close()
    return str(destination)


def create_card(name: str, job: str, phone: str) -> str:
    output = _prepare_dir() / f"{uuid.uuid4().hex}.png"
    image = Image.new("RGB", (1200, 675), "#15263f")
    draw = ImageDraw.Draw(image)
    font_path = next(
        (
            candidate
            for candidate in (
                "C:\\Windows\\Fonts\\arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            )
            if Path(candidate).is_file()
        ),
        None,
    )
    font = ImageFont.truetype(font_path, 52) if font_path else ImageFont.load_default()
    secondary_font = ImageFont.truetype(font_path, 38) if font_path else ImageFont.load_default()
    draw.rounded_rectangle((45, 45, 1155, 630), radius=36, fill="#203b5d", outline="#73d5d0", width=5)
    draw.text((100, 160), name, fill="white", font=font)
    draw.text((100, 270), job, fill="#73d5d0", font=secondary_font)
    draw.text((100, 400), phone, fill="white", font=secondary_font)
    image.save(output)
    return str(output)


def create_cv_pdf(name: str, contact: str, summary: str, experience: str) -> str:
    output = _prepare_dir() / f"{uuid.uuid4().hex}.pdf"
    pdf = canvas.Canvas(str(output), pagesize=A4)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path = next(
        (
            candidate
            for candidate in (
                "C:\\Windows\\Fonts\\arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            )
            if Path(candidate).is_file()
        ),
        None,
    )
    if font_path:
        pdfmetrics.registerFont(TTFont("ResumeFont", font_path))
        regular_font = "ResumeFont"
        bold_font = "ResumeFont"
    else:
        regular_font = bold_font = "Helvetica"
    _, height = A4
    y = height - 70
    pdf.setFont(bold_font, 20)
    pdf.drawString(55, y, name[:90])
    pdf.setFont(regular_font, 11)
    for heading, text in (("Aloqa", contact), ("Qisqacha", summary), ("Tajriba", experience)):
        y -= 45
        pdf.setFont(bold_font, 13)
        pdf.drawString(55, y, heading)
        pdf.setFont(regular_font, 11)
        y -= 20
        for line in text.splitlines() or [""]:
            pdf.drawString(55, y, line[:110])
            y -= 16
            if y < 60:
                pdf.showPage()
                y = height - 60
                pdf.setFont(regular_font, 11)
    pdf.save()
    return str(output)


def create_payment_invoice(
    invoice_number: str,
    paid_at: datetime,
    customer_name: str,
    customer_id: int,
    summary: str,
    amount: int,
    phone: str,
    admin_username: str,
    language: str = "uz_latn",
) -> tuple[str, str]:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas
    from services.i18n import translate_text

    output_dir = _prepare_dir()
    stem = uuid.uuid4().hex
    image_path = output_dir / f"{stem}.png"
    pdf_path = output_dir / f"{stem}.pdf"
    font_path = next(
        (
            candidate
            for candidate in (
                "C:\\Windows\\Fonts\\arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            )
            if Path(candidate).is_file()
        ),
        None,
    )
    title_font = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path, 30) if font_path else ImageFont.load_default()
    small_font = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default()
    localized_summary = translate_text(summary, language)
    width = 1200
    padding = 72
    entries = [
        (translate_text("Chek raqami", language), invoice_number, body_font, "#182c40"),
        (translate_text("Sana", language), f"{paid_at:%Y-%m-%d %H:%M} (Toshkent)", body_font, "#182c40"),
        (translate_text("Xaridor", language), customer_name, body_font, "#182c40"),
        ("Telegram ID", str(customer_id), body_font, "#182c40"),
        (translate_text("Xarid / xizmat", language), "", body_font, "#182c40"),
        *[("", line, small_font, "#40566d") for line in localized_summary.splitlines()],
        (translate_text("Jami", language), f"{amount:,} UZS", body_font, "#182c40"),
        (translate_text("To‘lov holati", language), translate_text("PAID / TO‘LANDI", language), body_font, "#087a48"),
        (translate_text("Telefon", language), phone, body_font, "#182c40"),
        (translate_text("Admin", language), f"@{admin_username}", body_font, "#182c40"),
    ]

    image = Image.new("RGB", (width, 500), "#f3f6fa")
    draw = ImageDraw.Draw(image)
    y = 180
    wrapped: list[tuple[str, str, ImageFont.FreeTypeFont | ImageFont.ImageFont, str]] = []
    max_text_width = width - 2 * padding
    for label, value, font, color in entries:
        text = f"{label}: {value}" if label else value
        words = text.split()
        current = ""
        text_lines: list[str] = []
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_text_width:
                text_lines.append(current)
                current = word
            else:
                current = candidate
        if current or not text_lines:
            text_lines.append(current)
        for line in text_lines:
            wrapped.append((line, "", font, color))
            y += max(44, draw.textbbox((0, 0), line or " ", font=font)[3] + 20)

    height = y + 45
    image = Image.new("RGB", (width, height), "#f3f6fa")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 30, width - 30, height - 30), radius=28, fill="white", outline="#234b70", width=4)
    draw.rounded_rectangle((32, 32, width - 32, 145), radius=26, fill="#173b5e")
    draw.text((padding, 62), translate_text("TO‘LOV CHEKI", language), font=title_font, fill="white")
    y = 175
    for line, _, font, color in wrapped:
        draw.text((padding, y), line, font=font, fill=color)
        y += max(44, draw.textbbox((padding, y), line or " ", font=font)[3] - y + 20)
    image.save(image_path)

    page_width = 595.27
    page_height = page_width * height / width
    pdf = pdf_canvas.Canvas(str(pdf_path), pagesize=(page_width, page_height))
    pdf.drawImage(ImageReader(image), 0, 0, width=page_width, height=page_height)
    pdf.save()
    return str(image_path), str(pdf_path)
