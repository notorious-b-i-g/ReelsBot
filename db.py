import sqlite3
import json
import os
from config import SYSTEM_PROMPT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILENAME = os.path.join(BASE_DIR, 'database.db')

def init_db() -> None:
    with sqlite3.connect(DB_FILENAME) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_contexts (
                user_id INTEGER PRIMARY KEY,
                history TEXT,
                system_prompt TEXT
            )
        ''')
        # Создаем таблицу для авторизованных пользователей
        conn.execute('''
            CREATE TABLE IF NOT EXISTS allowed_users (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        conn.commit()

def get_user_context(user_id: int) -> list:
    with sqlite3.connect(DB_FILENAME) as conn:
        cursor = conn.execute(
            'SELECT history FROM user_contexts WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return []

def update_user_context(user_id: int, context: list) -> None:
    history_json = json.dumps(context)
    with sqlite3.connect(DB_FILENAME) as conn:
        # Если записи уже нет, оставляем системный промпт по умолчанию или предыдущее значение
        cursor = conn.execute('SELECT system_prompt FROM user_contexts WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        system_prompt = row[0] if row and row[0] else SYSTEM_PROMPT
        conn.execute(
            'REPLACE INTO user_contexts (user_id, history, system_prompt) VALUES (?, ?, ?)',
            (user_id, history_json, system_prompt)
        )
        conn.commit()

def clear_user_context(user_id: int) -> None:
    with sqlite3.connect(DB_FILENAME) as conn:
        conn.execute('UPDATE user_contexts SET history = "" WHERE user_id = ?', (user_id,))
        conn.execute('UPDATE user_contexts SET system_prompt = "" WHERE user_id = ?', (user_id,))
        conn.commit()

def add_allowed_user(user_id: int) -> None:
    with sqlite3.connect(DB_FILENAME) as conn:
        conn.execute('INSERT OR IGNORE INTO allowed_users (user_id) VALUES (?)', (user_id,))
        conn.commit()

def is_user_allowed(user_id: int) -> bool:
    with sqlite3.connect(DB_FILENAME) as conn:
        cursor = conn.execute('SELECT 1 FROM allowed_users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None

def update_system_prompt(user_id: int, system_prompt: str) -> None:
    with sqlite3.connect(DB_FILENAME) as conn:
        conn.execute(
            'UPDATE user_contexts SET system_prompt = ? WHERE user_id = ?',
            (system_prompt, user_id)
        )
        conn.commit()

def get_system_prompt(user_id: int) -> str:
    with sqlite3.connect(DB_FILENAME) as conn:
        cursor = conn.execute(
            'SELECT system_prompt FROM user_contexts WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
        return SYSTEM_PROMPT

if __name__ == '__main__':
    init_db()
    print("База данных инициализирована.")
