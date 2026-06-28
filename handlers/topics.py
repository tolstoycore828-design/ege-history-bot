from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database as db

router = Router()

BACK_ROOT = InlineKeyboardButton(text="⬅️ К разделам", callback_data="topics:root")
BACK_MAIN = InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery):
    from handlers.start import main_menu_kb
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "topics:root")
async def cb_topics_root(cb: CallbackQuery):
    sections = await db.get_topics(parent_id=None)
    if not sections:
        await cb.answer("База вопросов ещё не загружена. Запустите parser.py", show_alert=True)
        return

    rows = []
    for s in sections:
        count = await _count_section(s["id"])
        label = f"{s['code']}. {s['title']} ({count} вопр.)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"section:{s['id']}")])
    rows.append([BACK_MAIN])

    await cb.message.edit_text(
        "📋 <b>Кодификатор ЕГЭ по Истории</b>\n\nВыбери раздел:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _count_section(section_id: int) -> int:
    subtopics = await db.get_topics(parent_id=section_id)
    total = 0
    for t in subtopics:
        total += await db.count_questions(t["id"])
    return total


@router.callback_query(F.data.startswith("section:"))
async def cb_section(cb: CallbackQuery):
    section_id = int(cb.data.split(":")[1])
    section = await db.get_topic(section_id)
    subtopics = await db.get_topics(parent_id=section_id)

    rows = []
    for t in subtopics:
        count = await db.count_questions(t["id"])
        label = f"{t['code']}. {t['title']} ({count})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"quiz_start:{t['id']}")])
    rows.append([BACK_ROOT])

    await cb.message.edit_text(
        f"📂 <b>{section['code']}. {section['title']}</b>\n\nВыбери тему:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    total, correct = await db.get_user_stats(cb.from_user.id)
    pct = round(correct / total * 100) if total else 0
    await cb.message.edit_text(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"Решено вопросов: <b>{total}</b>\n"
        f"Правильных: <b>{correct}</b>\n"
        f"Процент верных: <b>{pct}%</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 К темам", callback_data="topics:root")],
            [BACK_MAIN],
        ]),
    )
