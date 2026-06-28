from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import database as db

router = Router()


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Выбрать тему", callback_data="topics:root")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats")],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я помогу тебе подготовиться к ЕГЭ по <b>Истории России</b>.\n\n"
        "Выбери тему из кодификатора и решай задания — я покажу правильный ответ и объяснение.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=main_menu_kb())
