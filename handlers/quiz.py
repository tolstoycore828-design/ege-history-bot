from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()


class QuizState(StatesGroup):
    answering = State()


def _nav_kb(topic_id: int, section_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data=f"quiz_next:{topic_id}")],
        [InlineKeyboardButton(text="⬅️ К теме", callback_data=f"section:{section_id}")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])


def _number_reply_kb(count: int) -> ReplyKeyboardMarkup:
    row_size = 4
    rows = []
    row = []
    for i in range(1, count + 1):
        row.append(KeyboardButton(text=str(i)))
        if len(row) == row_size:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def _build_text(header: str, question: str, choices: list) -> str:
    lines = [header + question, ""]
    for i, c in enumerate(choices, 1):
        lines.append(f"{i}. {c['text']}")
    return "\n".join(lines)


async def _send_question(target, topic_id: int, state: FSMContext):
    data = await state.get_data()
    seen = data.get("seen", [])

    questions = await db.get_questions(topic_id, limit=1, exclude_ids=seen if seen else None)
    if not questions:
        seen = []
        questions = await db.get_questions(topic_id, limit=1)

    # Пропускаем вопросы без вариантов ответа
    attempts = 0
    while questions:
        q = questions[0]
        choices = await db.get_choices(q["id"])
        if choices:
            break
        seen.append(q["id"])
        attempts += 1
        if attempts > 20:
            q = None
            break
        questions = await db.get_questions(topic_id, limit=1, exclude_ids=seen)

    if not questions or not q:
        text = "В этой теме нет тестовых вопросов с вариантами ответов."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text, reply_markup=ReplyKeyboardRemove())
        return

    choices = await db.get_choices(q["id"])
    seen.append(q["id"])

    topic = await db.get_topic(topic_id)
    section = await db.get_topic(topic["parent_id"])
    section_id = section["id"] if section else topic_id

    await state.update_data(
        seen=seen,
        topic_id=topic_id,
        section_id=section_id,
        current_q=q["id"],
        correct_letter=q["answer"].strip().upper() if q["answer"] else "",
        choices=[dict(c) for c in choices],
    )
    await state.set_state(QuizState.answering)

    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    text = _build_text(header, q["text"], choices)
    kb = _number_reply_kb(len(choices))

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML")
        await target.message.answer("Выбери номер ответа:", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("quiz_start:"))
async def cb_quiz_start(cb: CallbackQuery, state: FSMContext):
    topic_id = int(cb.data.split(":")[1])
    await state.update_data(seen=[], topic_id=topic_id)
    await _send_question(cb, topic_id, state)


@router.callback_query(F.data.startswith("quiz_next:"))
async def cb_quiz_next(cb: CallbackQuery, state: FSMContext):
    topic_id = int(cb.data.split(":")[1])
    await _send_question(cb, topic_id, state)


@router.message(QuizState.answering)
async def msg_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    q_id = data.get("current_q")
    topic_id = data.get("topic_id")
    section_id = data.get("section_id")
    choices = data.get("choices", [])

    if not message.text or not message.text.isdigit():
        await message.answer("Нажми на цифру на панели ниже 👇")
        return

    chosen_num = int(message.text)
    if chosen_num < 1 or chosen_num > len(choices):
        await message.answer(f"Введи число от 1 до {len(choices)}")
        return

    q = await db.get_question(q_id)
    topic = await db.get_topic(q["topic_id"])

    correct_letter = q["answer"].strip().upper() if q["answer"] else ""
    letters = [c["letter"].upper() for c in choices]

    if correct_letter in letters:
        correct_num = letters.index(correct_letter) + 1
    elif correct_letter.isdigit():
        correct_num = int(correct_letter)
    else:
        correct_num = None

    is_correct = (chosen_num == correct_num)
    await db.save_progress(message.from_user.id, q_id, is_correct)

    header = f"📌 <b>{topic['code']}. {topic['title']}</b>\n\n"
    choices_text = ""
    for i, c in enumerate(choices, 1):
        if i == correct_num:
            choices_text += f"<b>{i}. {c['text']} ✅</b>\n"
        elif i == chosen_num and not is_correct:
            choices_text += f"<s>{i}. {c['text']}</s> ❌\n"
        else:
            choices_text += f"{i}. {c['text']}\n"

    result = "✅ <b>Верно!</b>" if is_correct else f"❌ <b>Неверно.</b> Правильный ответ: <b>{correct_num}</b>"
    explanation = f"\n\n💡 <i>{q['explanation'][:500]}</i>" if q["explanation"] else ""

    text = header + q["text"] + "\n\n" + choices_text.strip() + f"\n\n{result}{explanation}"

    await state.clear()
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Что дальше?",
        reply_markup=_nav_kb(topic_id, section_id),
    )
