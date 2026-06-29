import asyncpg
from config import DATABASE_URL

_pool: asyncpg.Pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL,
                title TEXT NOT NULL,
                parent_id INTEGER REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                external_id TEXT UNIQUE,
                topic_id INTEGER REFERENCES topics(id),
                text TEXT NOT NULL,
                image_url TEXT,
                answer TEXT,
                explanation TEXT,
                question_type TEXT DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS choices (
                id SERIAL PRIMARY KEY,
                question_id INTEGER REFERENCES questions(id),
                letter TEXT NOT NULL,
                text TEXT NOT NULL,
                UNIQUE(question_id, letter)
            );

            CREATE TABLE IF NOT EXISTS user_progress (
                user_id BIGINT NOT NULL,
                question_id INTEGER REFERENCES questions(id),
                answered_at TIMESTAMP DEFAULT NOW(),
                is_correct INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, question_id)
            );

            CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id);
            CREATE INDEX IF NOT EXISTS idx_progress_user ON user_progress(user_id);
        """)


async def get_topics(parent_id=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if parent_id is None:
            return await conn.fetch(
                "SELECT * FROM topics WHERE parent_id IS NULL ORDER BY code"
            )
        return await conn.fetch(
            "SELECT * FROM topics WHERE parent_id=$1 ORDER BY code", parent_id
        )


async def get_topic(topic_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM topics WHERE id=$1", topic_id)


async def get_questions(topic_id, limit=1, offset=0, exclude_ids=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if exclude_ids:
            return await conn.fetch(
                "SELECT * FROM questions WHERE topic_id=$1 AND id != ALL($2) ORDER BY RANDOM() LIMIT $3 OFFSET $4",
                topic_id, exclude_ids, limit, offset,
            )
        return await conn.fetch(
            "SELECT * FROM questions WHERE topic_id=$1 ORDER BY RANDOM() LIMIT $2 OFFSET $3",
            topic_id, limit, offset,
        )


async def get_question(question_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM questions WHERE id=$1", question_id)


async def get_choices(question_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM choices WHERE question_id=$1 ORDER BY letter", question_id
        )


async def count_questions(topic_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM questions WHERE topic_id=$1", topic_id
        )


async def save_progress(user_id, question_id, is_correct):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO user_progress (user_id, question_id, is_correct)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id, question_id) DO UPDATE
               SET is_correct=EXCLUDED.is_correct, answered_at=NOW()""",
            user_id, question_id, int(is_correct),
        )


async def get_user_stats(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*), SUM(is_correct) FROM user_progress WHERE user_id=$1", user_id
        )
        total = row[0] or 0
        correct = row[1] or 0
        return total, correct


async def upsert_topic(code, title, parent_id=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM topics WHERE code=$1", code)
        if row:
            return row["id"]
        return await conn.fetchval(
            "INSERT INTO topics (code, title, parent_id) VALUES ($1,$2,$3) RETURNING id",
            code, title, parent_id,
        )


async def upsert_question(external_id, topic_id, text, image_url, answer, explanation, question_type):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM questions WHERE external_id=$1", external_id
        )
        if row:
            return row["id"]
        return await conn.fetchval(
            """INSERT INTO questions (external_id, topic_id, text, image_url, answer, explanation, question_type)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            external_id, topic_id, text, image_url, answer, explanation, question_type,
        )


async def insert_choices(question_id, choices: list[tuple]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO choices (question_id, letter, text) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
            [(question_id, letter, text) for letter, text in choices],
        )
