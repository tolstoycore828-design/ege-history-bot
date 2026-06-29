import random
import re
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


def _nav_kb(topic_id: int, section_id: int, mode: str = "topic") -> InlineKeyboardMarkup:
    if mode == "task":
        next_cb = f"task_next:{topic_id}"
        back_cb = "tasks:root"
        back_label = "⬅️ К заданиям"
    else:
        next_cb = f"quiz_next:{topic_id}"
        back_cb = f"section:{section_id}"
        back_label = "⬅️ К теме"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data=next_cb)],
        [InlineKeyboardButton(text=back_label, callback_data=back_cb)],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])


def _number_reply_kb(count: int) -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for i in range(1, count + 1):
        row.append(KeyboardButton(text=str(i)))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def _is_sequence_answer(answer: str) -> bool:
    """Проверяет, является ли ответ последовательностью цифр (задание на соответствие)."""
    return bool(answer and re.fullmatch(r'[1-9]{2,6}', answer.strip()))


def _generate_sequence_variants(correct: str) -> list[str]:
    """Генерирует 4 варианта последовательности: правильный + 3 неправильных."""
    digits = list(correct)
    variants = {correct}
    attempts = 0
    while len(variants) < 4 and attempts < 100:
        shuffled = digits[:]
        random.shuffle(shuffled)
        variants.add("".join(shuffled))
        attempts += 1
    variants = list(variants)
    random.shuffle(variants)
    return variants


def _sequence_inline_kb(q_id: int, variants: list[str], correct: str) -> InlineKeyboardMarkup:
    rows = []
    for v in variants:
        rows.append([InlineKeyboardButton(
            text=v,
            callback_data=f"seq_answer:{q_id}:{v}:{correct}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_text(header: str, question: str, choices: list) -> str:
    lines = [header + question, ""]
    for i, c in enumerate(choices, 1):
        lines.append(f"{i}. {c['text']}")
    return "\n".join(lines)


async def _send_question(target, state: FSMContext, mode: str = "topic"):
    data = await state.get_data()
    seen = data.get("seen", [])
    topic_id = data.get("topic_id")
    task_number = data.get("task_number")

    if mode == "task":
        questions = await db.get_questions_by_task(task_number, limit=1, exclude_ids=seen if seen else None)
        if not questions:
            seen = []
            questions = await db.get_questions_by_task(task_number, limit=1)
    else:
        questions = await db.get_questions(topic_id, limit=1, exclude_ids=seen if seen else None)
        if not questions:
            seen = []
            questions = await db.get_questions(topic_id, limit=1)

    # Для вопросов без вариантов проверяем, можно ли сделать соответствие
    if not questions:
        # Попробуем взять вопросы с ответом-последовательностью
        pass

    if not questions:
        text = "В этой теме нет тестовых вопросов."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text, reply_markup=ReplyKeyboardRemove())
        return

    q = questions[0]
    choices = await db.get_choices(q["id"])
    seen.append(q["id"])

    topic = await db.get_topic(q["topic_id"])
    section = await db.get_topic(topic["parent_id"]) if topic["parent_id"] else None
    section_id = section["id"] if section else q["topic_id"]

    await state.update_data(
        seen=seen,
        topic_id=topic_id,
        task_number=task_number,
        section_id=section_id,
        current_q=q["id"],
        mode=mode,
    )
    await state.set_state(QuizState.answering)

    task_label = f" · Задание {q['task_number']}" if q["task_number"] else ""
    header = f"📌 <b>{topic['code']}. {topic['title']}</b>{task_label}\n\n"
    send = target.message if isinstance(target, CallbackQuery) else target

    # Вопрос на соответствие (ответ — последовательность цифр, нет вариантов)
    if not choices and _is_sequence_answer(q["answer"] or ""):
        correct = q["answer"].strip()
        variants = _generate_sequence_variants(correct)
        text = header + q["text"]
        kb = _sequence_inline_kb(q["id"], variants, correct)

        if q["image_url"]:
            try:
                await send.answer_photo(photo=q["image_url"], caption=text[:1024], parse_mode="HTML")
                if isinstance(target, CallbackQuery):
                    await send.answer("Выбери правильную последовательность:", reply_markup=kb)
                else:
                    await send.answer("Выбери правильную последовательность:", reply_markup=kb)
            except Exception:
                if isinstance(target, CallbackQuery):
                    await send.edit_text(text, parse_mode="HTML", reply_markup=kb)
                else:
                    await send.answer(text, parse_mode="HTML", reply_markup=kb)
        else:
            if isinstance(target, CallbackQuery):
                await send.edit_text(text, parse_mode="HTML", reply_markup=kb)
            else:
                await send.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    # Обычный вопрос с вариантами
    text = _build_text(header, q["text"], choices)
    kb = _number_reply_kb(len(choices))

    if q["image_url"]:
        try:
            await send.answer_photo(photo=q["image_url"], caption=text[:1024], parse_mode="HTML")
            await send.answer("Выбери номер ответа:", reply_markup=kb)
        except Exception:
            if isinstance(target, CallbackQuery):
                await send.edit_text(text, parse_mode="HTML")
            else:
                await send.answer(text, parse_mode="HTML")
            await send.answer("Выбери номер ответа:", reply_markup=kb)
    else:
        if isinstance(target, CallbackQuery):
            await send.edit_text(text, parse_mode="HTML")
            await send.answer("Выбери номер ответа:", reply_markup=kb)
        else:
            await send.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("quiz_start:"))
async def cb_quiz_start(cb: CallbackQuery, state: FSMContext):
    topic_id = int(cb.data.split(":")[1])
    await state.update_data(seen=[], topic_id=topic_id, mode="topic")
    await _send_question(cb, state, mode="topic")


@router.callback_query(F.data.startswith("quiz_next:"))
async def cb_quiz_next(cb: CallbackQuery, state: FSMContext):
    topic_id = int(cb.data.split(":")[1])
    await state.update_data(topic_id=topic_id)
    await _send_question(cb, state, mode="topic")


@router.callback_query(F.data.startswith("task_quiz:"))
async def cb_task_quiz(cb: CallbackQuery, state: FSMContext):
    task_number = int(cb.data.split(":")[1])
    await state.update_data(seen=[], task_number=task_number, mode="task")
    await _send_question(cb, state, mode="task")


@router.callback_query(F.data.startswith("task_next:"))
async def cb_task_next(cb: CallbackQuery, state: FSMContext):
    task_number = int(cb.data.split(":")[1])
    await state.update_data(task_number=task_number)
    await _send_question(cb, state, mode="task")


@router.callback_query(F.data.startswith("seq_answer:"))
async def cb_seq_answer(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    q_id, chosen, correct = int(parts[1]), parts[2], parts[3]

    data = await state.get_data()
    topic_id = data.get("topic_id")
    task_number = data.get("task_number")
    section_id = data.get("section_id", topic_id)
    mode = data.get("mode", "topic")

    q = await db.get_question(q_id)
    topic = await db.get_topic(q["topic_id"])

    is_correct = (chosen == correct)
    await db.save_progress(cb.from_user.id, q_id, is_correct)

    task_label = f" · Задание {q['task_number']}" if q["task_number"] else ""
    header = f"📌 <b>{topic['code']}. {topic['title']}</b>{task_label}\n\n"
    result = "✅ <b>Верно!</b>" if is_correct else f"❌ <b>Неверно.</b> Правильный ответ: <b>{correct}</b>"
    explanation = f"\n\n💡 <i>{q['explanation'][:500]}</i>" if q["explanation"] else ""
    text = header + q["text"] + f"\n\n{result}{explanation}"

    nav_topic_id = task_number if mode == "task" else topic_id
    await state.clear()

    await cb.message.edit_text(text, parse_mode="HTML",
                               reply_markup=_nav_kb(nav_topic_id, section_id, mode=mode))


@router.message(QuizState.answering)
async def msg_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    q_id = data.get("current_q")
    topic_id = data.get("topic_id")
    task_number = data.get("task_number")
    section_id = data.get("section_id", topic_id)
    mode = data.get("mode", "topic")

    if not message.text or not message.text.isdigit():
        await message.answer("Нажми на цифру на панели ниже 👇")
        return

    chosen_num = int(message.text)
    choices = await db.get_choices(q_id)

    if chosen_num < 1 or chosen_num > len(choices):
        await message.answer(f"Введи число от 1 до {len(choices)}")
        return

    q = await db.get_question(q_id)
    topic = await db.get_topic(q["topic_id"])

    correct_letter = q["answer"].strip().upper() if q["answer"] else ""
    letters = [c["letter"].upper() for c in choices]

    if correct_letter in letters:
        correct_num = letters.index(correct_letter) + 1
    elif correct_letter.isdigit() and 1 <= int(correct_letter) <= len(choices):
        correct_num = int(correct_letter)
    else:
        # Попробуем найти по первому совпадению цифры в ответе
        digits = re.findall(r'\d+', correct_letter)
        correct_num = int(digits[0]) if digits and 1 <= int(digits[0]) <= len(choices) else None

    is_correct = (chosen_num == correct_num)
    await db.save_progress(message.from_user.id, q_id, is_correct)

    task_label = f" · Задание {q['task_number']}" if q["task_number"] else ""
    header = f"📌 <b>{topic['code']}. {topic['title']}</b>{task_label}\n\n"
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

    nav_topic_id = task_number if mode == "task" else topic_id
    await state.clear()

    await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await message.answer("Что дальше?", reply_markup=_nav_kb(nav_topic_id, section_id, mode=mode))
