import os
import logging
import asyncio
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

# ---------- Настройки (замени на свои) ----------
BOT_TOKEN = "8949357849:AAHD9BzJ2ziFFNxJtbsJXZfl_VxZaMOlCcI"
YANDEX_TOKEN = "y0__wgBEPfkrfMCGNuWAyCRjrO9GaTb38VAsxX1EJooQ6YNva3perKW"

YANDEX_API = "https://cloud-api.yandex.net/v1/disk"
YANDEX_FOLDER = "фото"   # папка на Яндекс.Диске
TEMP_DIR = Path("temp_uploads")
TEMP_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------- Яндекс.Диск ----------
async def ensure_yandex_folder(session: aiohttp.ClientSession, headers: dict, folder: str) -> None:
    """Создаёт папку на Яндекс.Диске, если её ещё нет."""
    async with session.put(
        f"{YANDEX_API}/resources",
        headers=headers,
        params={"path": f"/{folder}"},
    ) as resp:
        if resp.status in (201, 409):
            # 201 — создали, 409 — уже существует. Оба варианта ок.
            return
        text = await resp.text()
        raise Exception(f"Yandex create folder {resp.status}: {text}")


async def upload_to_yandex(file_path: Path, remote_name: str) -> str:
    """Заливает файл в папку YANDEX_FOLDER. Перезаписывает, если файл с таким именем уже есть."""
    headers = {"Authorization": f"OAuth {YANDEX_TOKEN}"}
    remote_path = f"/{YANDEX_FOLDER}/{remote_name}"

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 0) Убеждаемся, что папка существует
        await ensure_yandex_folder(session, headers, YANDEX_FOLDER)

        # 1) Получаем ссылку на загрузку
        async with session.get(
            f"{YANDEX_API}/resources/upload",
            headers=headers,
            params={"path": remote_path, "overwrite": "true"},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Yandex upload-URL {resp.status}: {text}")
            upload_url = (await resp.json())["href"]

        # 2) PUT-ом заливаем файл
        with open(file_path, "rb") as f:
            async with session.put(upload_url, data=f) as put:
                if put.status not in (200, 201, 202):
                    text = await put.text()
                    raise Exception(f"Yandex PUT {put.status}: {text}")

    return remote_path


# ---------- Хендлеры ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Пришли мне фото — сохраню его для розыгрыша под твоим тегом. Новое фото заменит предыдущее."
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Как пользоваться:\n"
        f"• Отправь мне фото — я загружу его в папку <code>/{YANDEX_FOLDER}</code> "
        "под твоим тегом.\n"
        "• Новое фото заменит предыдущее.\n"
        "• Всё остальное я не принимаю."
    )


@dp.message(F.photo)
async def handle_photo(message: Message):
    photo = message.photo[-1]

    if message.from_user.username:
        tag = f"@{message.from_user.username}"
    else:
        tag = f"user_{message.from_user.id}"

    safe_name = "".join(c for c in tag if c not in r'\/:*?"<>|')
    file_name = f"{safe_name}.jpg"

    local_path = TEMP_DIR / f"{message.from_user.id}_{file_name}"

    try:
        await bot.download(photo, destination=local_path)
        remote_path = await upload_to_yandex(local_path, file_name)
        local_path.unlink(missing_ok=True)

        await message.answer(
            f"Спасибо, записали тебя ✅\n"
        )
    except Exception:
        import traceback
        logging.error("Ошибка при обработке фото:\n%s", traceback.format_exc())
        local_path.unlink(missing_ok=True)
        await message.answer(
            "Что-то не так. Напиши Кандыбе и он попробует все исправить."
        )


@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Не понял, что это \n"
        "Пришли фото — и я его сохраню."
    )

# ---------- Запуск ----------
async def main():
    logging.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    logging.info("Webhook сброшен, начинаю polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(main())
    except RuntimeError:
        asyncio.run(main())