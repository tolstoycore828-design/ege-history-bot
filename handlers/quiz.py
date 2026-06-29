from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()

NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


class QuizState(StatesGroup):
    answering = State()


def _quiz_nav(topic_id: int, section_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data=f"quiz_next:{topic_id}")],
        [InlineKeyboardButton(text="⬅️ К теме", callback_data=f"section:{section_id}")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])


def _build_question_text(header: str, question: str, choices: list) -> str:
    text = header + question + "\n\n"
    for i, c in enumerate(choices, 1):
        text += f"{i}. {c['text']}\n"
    return text.strip()


def _number_kb(question_id: int, choices: list, section_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=str(i),
            callback_data=f"answer:{question_id}:{i}:{section_id}",
        )
        for i in range(1, len(choices) + 1)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def _send_question(cb_or_msg, topic_id: int, state: FSMContext):
    data = await state.get_data()
    seen = data.get("seen", [])

    questions = await db.get_questions(topic_id, limit=1, exclude_ids=seen if seen else None)
    if not questions:
        seen = []
        questions = await db.get_questions(topic_id, limit=1)
        if not questions:
            text = "В этой теме пока нет вопросов."
            if hasattr(cb_or_msg, "message"):
                await cb_or_msg.message.edit_text(text)
            else:
                await cb_or_msg.answer(text)
            return

    q = questions[0]
    seen.append(q["id"])

    topic = await db.get_topic(topic_id)
    section = await db.get_topic(topic["parent_id"])
    section_id = section["id"] if section else topic_id
    choices = await db.get_choices(q["id"])

    await state.update_data(
        seen=seen,
        topic_id=topic_id,
        current_q=q["id"],
        section_id=section_id,
        correct_letter=q["answer"].strip().upper() if q["answer"] else "",
        choices=[dict(c) for c in choices],
    )

    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    send = cb_or_msg.message if hasattr(cb_or_msg, "message") else cb_or_msg

    if choices:
        await state.set_state(QuizState.answering)
        text = _build_question_text(header, q["text"], choices)
        kb = _number_kb(q["id"], choices, section_id)
        if hasattr(cb_or_msg, "message"):
            await send.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await send.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Показать ответ",
                callback_data=f"show_answer:{q['id']}:{topic_id}:{section_id}",
            )],
        ])
        text = header + q["text"]
        if hasattr(cb_or_msg, "message"):
            await send.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await send.answer(text, parse_mode="HTML", reply_markup=kb)


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
    parts = cb.data.split(":")
    q_id, chosen_num, section_id = int(parts[1]), int(parts[2]), int(parts[3])

    q = await db.get_question(q_id)
    topic = await db.get_topic(q["topic_id"])
    choices = await db.get_choices(q_id)

    # Определяем правильный номер по букве из ответа
    correct_letter = q["answer"].strip().upper() if q["answer"] else ""
    letters = [c["letter"].upper() for c in choices]
    correct_num = letters.index(correct_letter) + 1 if correct_letter in letters else None

    # Если ответ — просто цифра (некоторые вопросы так устроены)
    if correct_num is None and correct_letter.isdigit():
        correct_num = int(correct_letter)

    is_correct = (chosen_num == correct_num)
    await db.save_progress(cb.from_user.id, q_id, is_correct)

    # Формируем текст с вариантами, где правильный выделен
    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    choices_text = ""
    for i, c in enumerate(choices, 1):
        if i == correct_num:
            choices_text += f"<b>{i}. {c['text']} ✅</b>\n"
        elif i == chosen_num and not is_correct:
            choices_text += f"<s>{i}. {c['text']}</s> ❌\n"
        else:
            choices_text += f"{i}. {c['text']}\n"

    if is_correct:
        result = "✅ <b>Верно!</b>"
    else:
        result = f"❌ <b>Неверно.</b> Правильный ответ: <b>{correct_num}</b>"

    explanation = f"\n\n💡 <i>{q['explanation'][:500]}</i>" if q["explanation"] else ""

    text = header + q["text"] + "\n\n" + choices_text.strip() + f"\n\n{result}{explanation}"

    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_quiz_nav(q["topic_id"], section_id),
    )
    await state.clear()


@router.callback_query(F.data.startswith("show_answer:"))
async def cb_show_answer(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    q_id, topic_id, section_id = int(parts[1]), int(parts[2]), int(parts[3])

    q = await db.get_question(q_id)
    topic = await db.get_topic(topic_id)

    answer_text = q["answer"] or "—"
    explanation = f"\n\n💡 <i>{q['explanation'][:500]}</i>" if q["explanation"] else ""
    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    text = header + q["text"] + f"\n\n✅ <b>Ответ:</b> {answer_text}{explanation}"

    await db.save_progress(cb.from_user.id, q_id, is_correct=True)
    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_quiz_nav(topic_id, section_id),
    )
    await state.clear()
