import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY,
                code TEXT NOT NULL,
                title TEXT NOT NULL,
                parent_id INTEGER REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY,
                external_id TEXT UNIQUE,
                topic_id INTEGER REFERENCES topics(id),
                text TEXT NOT NULL,
                image_url TEXT,
                answer TEXT,
                explanation TEXT,
                question_type TEXT DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS choices (
                id INTEGER PRIMARY KEY,
                question_id INTEGER REFERENCES questions(id),
                letter TEXT NOT NULL,
                text TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_progress (
                user_id INTEGER NOT NULL,
                question_id INTEGER REFERENCES questions(id),
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_correct INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, question_id)
            );

            CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id);
            CREATE INDEX IF NOT EXISTS idx_progress_user ON user_progress(user_id);
        """)
        await db.commit()


async def get_topics(parent_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if parent_id is None:
            async with db.execute(
                "SELECT * FROM topics WHERE parent_id IS NULL ORDER BY code"
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM topics WHERE parent_id=? ORDER BY code", (parent_id,)
            ) as cur:
                return await cur.fetchall()


async def get_topic(topic_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)) as cur:
            return await cur.fetchone()


async def get_questions(topic_id, limit=1, offset=0, exclude_ids=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        exclude_clause = ""
        params = [topic_id]
        if exclude_ids:
            placeholders = ",".join("?" * len(exclude_ids))
            exclude_clause = f"AND id NOT IN ({placeholders})"
            params.extend(exclude_ids)
        params.extend([limit, offset])
        async with db.execute(
            f"SELECT * FROM questions WHERE topic_id=? {exclude_clause} ORDER BY RANDOM() LIMIT ? OFFSET ?",
            params,
        ) as cur:
            return await cur.fetchall()


async def get_question(question_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM questions WHERE id=?", (question_id,)) as cur:
            return await cur.fetchone()


async def get_choices(question_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM choices WHERE question_id=? ORDER BY letter", (question_id,)
        ) as cur:
            return await cur.fetchall()


async def count_questions(topic_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM questions WHERE topic_id=?", (topic_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def save_progress(user_id, question_id, is_correct):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_progress (user_id, question_id, is_correct)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, question_id) DO UPDATE SET
               is_correct=excluded.is_correct, answered_at=CURRENT_TIMESTAMP""",
            (user_id, question_id, int(is_correct)),
        )
        await db.commit()


async def get_user_stats(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), SUM(is_correct) FROM user_progress WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            total = row[0] or 0
            correct = row[1] or 0
            return total, correct


async def upsert_topic(code, title, parent_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM topics WHERE code=?", (code,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        async with db.execute(
            "INSERT INTO topics (code, title, parent_id) VALUES (?,?,?)",
            (code, title, parent_id),
        ) as cur:
            await db.commit()
            return cur.lastrowid


async def upsert_question(external_id, topic_id, text, image_url, answer, explanation, question_type):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM questions WHERE external_id=?", (external_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        async with db.execute(
            """INSERT INTO questions (external_id, topic_id, text, image_url, answer, explanation, question_type)
               VALUES (?,?,?,?,?,?,?)""",
            (external_id, topic_id, text, image_url, answer, explanation, question_type),
        ) as cur:
            await db.commit()
            return cur.lastrowid


async def insert_choices(question_id, choices: list[tuple]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO choices (question_id, letter, text) VALUES (?,?,?)",
            [(question_id, letter, text) for letter, text in choices],
        )
        await db.commit()
