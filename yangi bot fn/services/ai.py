from openai import AsyncOpenAI
from pathlib import Path

from config import settings

AI_LANGUAGE_NAMES = {
    "uz_latn": "Uzbek (Latin script)",
    "uz_cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
}


async def ask_ai(prompt: str, language: str = "uz_latn") -> str:
    if not settings.openai_api_key:
        return "AI xizmati sozlanmagan. Administrator OPENAI_API_KEY qiymatini .env fayliga kiritsin."
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer clearly, helpfully, and safely. Respond in "
                    f"{AI_LANGUAGE_NAMES.get(language, AI_LANGUAGE_NAMES['uz_latn'])}."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or "Javob yaratilmadi."


async def transcribe_audio(path: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("Ovozni matnga o‘girish uchun OPENAI_API_KEY kerak.")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    with Path(path).open("rb") as audio:
        result = await client.audio.transcriptions.create(model="whisper-1", file=audio)
    return result.text


async def analyze_image(path: str, question: str, language: str = "uz_latn") -> str:
    if not settings.openai_api_key:
        raise RuntimeError("Rasm tahlili uchun OPENAI_API_KEY kerak.")
    import base64

    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            question
                            or "Describe the image in "
                            f"{AI_LANGUAGE_NAMES.get(language, AI_LANGUAGE_NAMES['uz_latn'])}."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                ],
            }
        ],
    )
    return response.choices[0].message.content or "Rasm tahlil qilinmadi."
