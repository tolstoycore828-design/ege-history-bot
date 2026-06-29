#!/bin/bash
mkdir -p /data

DB=/data/ege_history.db
COUNT=$(python -c "
import sqlite3, os
if not os.path.exists('$DB'):
    print(0)
else:
    try:
        c = sqlite3.connect('$DB')
        n = c.execute(\"SELECT COUNT(*) FROM questions\").fetchone()[0]
        print(n)
    except:
        print(0)
")

if [ "$COUNT" -eq 0 ]; then
    echo "База пустая, запускаю парсер..."
    python parser.py
else
    echo "База уже содержит $COUNT вопросов, парсинг пропущен."
fi

echo "Запускаю бота..."
python bot.py
