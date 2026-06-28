#!/bin/bash
# Если база пустая — сначала парсим, потом запускаем бота
if [ ! -f "ege_history.db" ] || [ $(python -c "import sqlite3; c=sqlite3.connect('ege_history.db'); print(c.execute('SELECT COUNT(*) FROM questions').fetchone()[0] if c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='questions'\").fetchone() else 0)") -eq 0 ]; then
    echo "База данных пустая, запускаю парсер..."
    python parser.py
fi

echo "Запускаю бота..."
python bot.py
