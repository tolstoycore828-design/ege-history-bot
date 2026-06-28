import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from config import BOT_TOKEN
from handlers import start, topics, quiz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Укажи BOT_TOKEN в файле .env")

    await db.init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(topics.router)
    dp.include_router(quiz.router)

    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
