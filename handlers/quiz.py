from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()


class QuizState(StatesGroup):
    answering = State()


def _quiz_nav(topic_id: int, section_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data=f"quiz_next:{topic_id}")],
        [InlineKeyboardButton(text="⬅️ К теме", callback_data=f"section:{section_id}")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])


def _choice_kb(question_id: int, choices: list) -> InlineKeyboardMarkup:
    rows = []
    for c in choices:
        rows.append([InlineKeyboardButton(
            text=f"{c['letter']}. {c['text'][:60]}",
            callback_data=f"answer:{question_id}:{c['letter']}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_question(cb_or_msg, topic_id: int, state: FSMContext):
    data = await state.get_data()
    seen = data.get("seen", [])

    questions = await db.get_questions(topic_id, limit=1, exclude_ids=seen if seen else None)
    if not questions:
        # All questions answered — reset
        seen = []
        questions = await db.get_questions(topic_id, limit=1)
        if not questions:
            text = "В этой теме пока нет вопросов. Сначала запустите парсер."
            if isinstance(cb_or_msg, CallbackQuery):
                await cb_or_msg.message.edit_text(text)
            else:
                await cb_or_msg.answer(text)
            return

    q = questions[0]
    seen.append(q["id"])
    await state.update_data(seen=seen, topic_id=topic_id, current_q=q["id"])

    topic = await db.get_topic(topic_id)
    section = await db.get_topic(topic["parent_id"])

    choices = await db.get_choices(q["id"])

    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    question_text = header + q["text"]

    send = cb_or_msg.message if isinstance(cb_or_msg, CallbackQuery) else cb_or_msg

    if choices:
        await state.set_state(QuizState.answering)
        kb = _choice_kb(q["id"], choices)
        if isinstance(cb_or_msg, CallbackQuery):
            await send.edit_text(question_text, parse_mode="HTML", reply_markup=kb)
        else:
            await send.answer(question_text, parse_mode="HTML", reply_markup=kb)
    else:
        # Open-ended: show question, then show answer button
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Показать ответ", callback_data=f"show_answer:{q['id']}:{topic_id}:{section['id'] if section else 0}")],
        ])
        if isinstance(cb_or_msg, CallbackQuery):
            await send.edit_text(question_text, parse_mode="HTML", reply_markup=kb)
        else:
            await send.answer(question_text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("quiz_start:"))
async def cb_quiz_start(cb: CallbackQuery, state: FSMContext):
    topic_id = int(cb.data.split(":")[1])
    await state.update_data(seen=[], topic_id=topic_id)
    await _send_question(cb, topic_id, state)


@router.callback_query(F.data.startswith("quiz_next:"))
async def cb_quiz_next(cb: CallbackQuery, state: FSMContext):
    topic_id = int(cb.data.split(":")[1])
    await _send_question(cb, topic_id, state)


@router.callback_query(F.data.startswith("answer:"))
async def cb_answer(cb: CallbackQuery, state: FSMContext):
    _, q_id_str, chosen = cb.data.split(":")
    q_id = int(q_id_str)

    q = await db.get_question(q_id)
    topic = await db.get_topic(q["topic_id"])
    section = await db.get_topic(topic["parent_id"])

    correct = q["answer"].strip().upper()
    is_correct = chosen.upper() == correct

    await db.save_progress(cb.from_user.id, q_id, is_correct)

    if is_correct:
        result = "✅ <b>Верно!</b>"
    else:
        result = f"❌ <b>Неверно.</b> Правильный ответ: <b>{correct}</b>"

    explanation = ""
    if q["explanation"]:
        explanation = f"\n\n💡 <i>{q['explanation'][:500]}</i>"

    text = (
        f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
        f"{q['text']}\n\n"
        f"{result}{explanation}"
    )

    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_quiz_nav(q["topic_id"], section["id"] if section else q["topic_id"]),
    )
    await state.clear()


@router.callback_query(F.data.startswith("show_answer:"))
async def cb_show_answer(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    q_id, topic_id, section_id = int(parts[1]), int(parts[2]), int(parts[3])

    q = await db.get_question(q_id)
    topic = await db.get_topic(topic_id)

    answer_text = q["answer"] or "—"
    explanation = ""
    if q["explanation"]:
        explanation = f"\n\n💡 <i>{q['explanation'][:500]}</i>"

    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    text = header + q["text"] + f"\n\n✅ <b>Ответ:</b> {answer_text}{explanation}"

    await db.save_progress(cb.from_user.id, q_id, is_correct=True)

    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_quiz_nav(topic_id, section_id),
    )
    await state.clear()
