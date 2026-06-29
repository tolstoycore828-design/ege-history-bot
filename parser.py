"""
Parser for hist-ege.sdamgia.ru — collects questions organized by EGE codifier topics.
Run directly: python parser.py
"""
import asyncio
import re
import logging
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

import database as db
from config import BASE_URL, PARSE_DELAY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Кодификатор ЕГЭ по Истории (разделы и темы)
CODIFIER = [
    ("1", "Древняя Русь (IX — начало XII в.)", [
        ("1.1", "Возникновение государственности у восточных славян"),
        ("1.2", "Первые киевские князья"),
        ("1.3", "Принятие христианства"),
        ("1.4", "Расцвет Древнерусского государства при Ярославе Мудром"),
        ("1.5", "Культура Древней Руси"),
    ]),
    ("2", "Русь Удельная (XII — XIII вв.)", [
        ("2.1", "Политическая раздробленность"),
        ("2.2", "Монгольское завоевание"),
        ("2.3", "Борьба с западными завоевателями"),
        ("2.4", "Культура XII—XIII вв."),
    ]),
    ("3", "Московская Русь (XIV — XVII вв.)", [
        ("3.1", "Объединение русских земель вокруг Москвы"),
        ("3.2", "Иван III. Образование единого государства"),
        ("3.3", "Иван Грозный. Опричнина"),
        ("3.4", "Смутное время"),
        ("3.5", "Первые Романовы"),
        ("3.6", "Культура XIV—XVII вв."),
    ]),
    ("4", "Российская империя в XVIII в.", [
        ("4.1", "Преобразования Петра I"),
        ("4.2", "Эпоха дворцовых переворотов"),
        ("4.3", "Екатерина II. Просвещённый абсолютизм"),
        ("4.4", "Пугачёвское восстание"),
        ("4.5", "Внешняя политика XVIII в."),
        ("4.6", "Культура XVIII в."),
    ]),
    ("5", "Российская империя в первой половине XIX в.", [
        ("5.1", "Александр I. Реформы начала XIX в."),
        ("5.2", "Отечественная война 1812 года"),
        ("5.3", "Движение декабристов"),
        ("5.4", "Николай I. Консервативная модернизация"),
        ("5.5", "Культура первой половины XIX в."),
    ]),
    ("6", "Российская империя во второй половине XIX в.", [
        ("6.1", "Отмена крепостного права"),
        ("6.2", "Реформы Александра II"),
        ("6.3", "Народническое движение"),
        ("6.4", "Александр III. Контрреформы"),
        ("6.5", "Внешняя политика второй половины XIX в."),
        ("6.6", "Культура второй половины XIX в."),
    ]),
    ("7", "Россия в начале XX в. (1900—1916)", [
        ("7.1", "Политическое развитие в начале XX в."),
        ("7.2", "Русско-японская война"),
        ("7.3", "Революция 1905—1907 гг."),
        ("7.4", "Реформы П.А. Столыпина"),
        ("7.5", "Россия в Первой мировой войне"),
        ("7.6", "Культура начала XX в."),
    ]),
    ("8", "Революция и Гражданская война (1917—1922)", [
        ("8.1", "Февральская революция 1917 г."),
        ("8.2", "Октябрьская революция 1917 г."),
        ("8.3", "Гражданская война"),
        ("8.4", "Политика военного коммунизма"),
    ]),
    ("9", "СССР в 1920—1930-е гг.", [
        ("9.1", "НЭП"),
        ("9.2", "Образование СССР"),
        ("9.3", "Индустриализация и коллективизация"),
        ("9.4", "Политическая система. Сталинизм"),
        ("9.5", "Культура 1920—1930-х гг."),
    ]),
    ("10", "Великая Отечественная война (1941—1945)", [
        ("10.1", "Начало войны. Причины поражений"),
        ("10.2", "Основные сражения"),
        ("10.3", "Тыл в годы войны"),
        ("10.4", "Антигитлеровская коалиция"),
        ("10.5", "Итоги и значение победы"),
    ]),
    ("11", "СССР в 1945—1991 гг.", [
        ("11.1", "Послевоенное восстановление. Апогей сталинизма"),
        ("11.2", "Хрущёвская «оттепель»"),
        ("11.3", "Брежневский «застой»"),
        ("11.4", "Перестройка. Распад СССР"),
        ("11.5", "Холодная война"),
        ("11.6", "Культура 1945—1991 гг."),
    ]),
    ("12", "Российская Федерация (1991 — настоящее время)", [
        ("12.1", "1990-е годы. Становление новой России"),
        ("12.2", "Россия в 2000-е — 2010-е гг."),
        ("12.3", "Внешняя политика России"),
    ]),
]


async def fetch(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                return await resp.text()
            log.warning("HTTP %s for %s", resp.status, url)
    except Exception as e:
        log.error("Fetch error %s: %s", url, e)
    return None


def clean_text(tag) -> str:
    if tag is None:
        return ""
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()


async def parse_problem_page(session: aiohttp.ClientSession, problem_id: str) -> Optional[dict]:
    url = f"{BASE_URL}/problem?id={problem_id}"
    html = await fetch(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    problem_div = soup.find("div", class_="prob_maindiv")
    if not problem_div:
        return None

    # Question text
    statement = problem_div.find("div", class_="pbody")
    text = clean_text(statement) if statement else ""
    if not text:
        return None

    # Image
    img_tag = problem_div.find("img")
    image_url = None
    if img_tag and img_tag.get("src"):
        src = img_tag["src"]
        image_url = src if src.startswith("http") else BASE_URL + src

    # Answer
    answer_div = problem_div.find("div", class_="answer")
    answer = clean_text(answer_div) if answer_div else ""
    if answer.lower().startswith("ответ:"):
        answer = answer[6:].strip()

    # Explanation
    exp_div = problem_div.find("div", class_="solution")
    explanation = clean_text(exp_div) if exp_div else ""

    # Multiple choice options
    choices = []
    for li in problem_div.find_all("li", class_=lambda c: c and "choice" in c):
        letter_tag = li.find("span", class_="choice_letter")
        if not letter_tag:
            continue
        letter = letter_tag.get_text(strip=True).rstrip(".")
        text_tag = li.find("span", class_="choice_text")
        choice_text = clean_text(text_tag) if text_tag else ""
        if choice_text:
            choices.append((letter, choice_text))

    # Task number (номер задания ЕГЭ)
    task_number = None
    topic_tag = soup.find("span", class_="prob_nums")
    if topic_tag:
        m = re.search(r"Задание\s*(\d+)", topic_tag.get_text())
        if m:
            task_number = int(m.group(1))
    if task_number is None:
        # try from breadcrumb or header
        for tag in soup.find_all(text=re.compile(r"Задание\s*\d+")):
            m = re.search(r"Задание\s*(\d+)", tag)
            if m:
                task_number = int(m.group(1))
                break

    q_type = "choice" if choices else "open"

    return {
        "external_id": problem_id,
        "text": text,
        "image_url": image_url,
        "answer": answer,
        "explanation": explanation,
        "question_type": q_type,
        "choices": choices,
        "task_number": task_number,
    }


async def parse_topic_problems(session: aiohttp.ClientSession, topic_code: str, page: int = 1) -> list[str]:
    """Returns list of problem IDs from a topic catalogue page."""
    url = f"{BASE_URL}/test?theme={topic_code}&page={page}"
    html = await fetch(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    ids = []
    for a in soup.find_all("a", href=re.compile(r"/problem\?id=\d+")):
        m = re.search(r"id=(\d+)", a["href"])
        if m:
            ids.append(m.group(1))
    return list(dict.fromkeys(ids))  # deduplicate preserving order


async def parse_catalogue(session: aiohttp.ClientSession) -> dict[str, int]:
    """Parse the main catalogue and map codifier codes to theme IDs on the site."""
    html = await fetch(session, f"{BASE_URL}/")
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    mapping = {}
    for a in soup.find_all("a", href=re.compile(r"theme=\d+")):
        m = re.search(r"theme=(\d+)", a["href"])
        if m:
            label = clean_text(a)
            mapping[label] = m.group(1)
    return mapping


async def run_parser(max_per_topic: int = 50):
    await db.init_db()

    async with aiohttp.ClientSession() as session:
        log.info("Начинаю парсинг...")

        for section_code, section_title, subtopics in CODIFIER:
            section_id = await db.upsert_topic(section_code, section_title)

            for sub_code, sub_title in subtopics:
                topic_id = await db.upsert_topic(sub_code, sub_title, parent_id=section_id)
                log.info("Тема %s — %s", sub_code, sub_title)

                # Search problems by topic keyword
                collected = 0
                for page in range(1, 6):
                    if collected >= max_per_topic:
                        break

                    # Use catalogue search by keyword
                    search_url = f"{BASE_URL}/search?search={sub_title[:30]}&page={page}"
                    html = await fetch(session, search_url)
                    if not html:
                        break

                    soup = BeautifulSoup(html, "lxml")
                    problem_links = soup.find_all("a", href=re.compile(r"/problem\?id=\d+"))
                    if not problem_links:
                        break

                    for a in problem_links:
                        if collected >= max_per_topic:
                            break
                        m = re.search(r"id=(\d+)", a["href"])
                        if not m:
                            continue
                        pid = m.group(1)

                        await asyncio.sleep(PARSE_DELAY)
                        problem = await parse_problem_page(session, pid)
                        if not problem or len(problem["text"]) < 20:
                            continue

                        q_id = await db.upsert_question(
                            external_id=problem["external_id"],
                            topic_id=topic_id,
                            text=problem["text"],
                            image_url=problem["image_url"],
                            answer=problem["answer"],
                            explanation=problem["explanation"],
                            question_type=problem["question_type"],
                            task_number=problem["task_number"],
                        )
                        if problem["choices"]:
                            await db.insert_choices(q_id, problem["choices"])

                        collected += 1
                        log.info("  [%s] Сохранён вопрос #%s (%d)", sub_code, pid, collected)

                    await asyncio.sleep(PARSE_DELAY)

        log.info("Парсинг завершён.")


if __name__ == "__main__":
    asyncio.run(run_parser(max_per_topic=50))
