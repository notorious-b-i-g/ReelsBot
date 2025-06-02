import sqlite3
import json
import os
from config import SYSTEM_PROMPT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILENAME = os.path.join(BASE_DIR, 'database.db')

def init_db() -> None:
    """Создаём базы и при необходимости добавляем недостающие колонки."""
    with sqlite3.connect(DB_FILENAME) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_contexts (
                user_id INTEGER PRIMARY KEY,
                dog_ctx TEXT,
                post_ctx TEXT,
                system_prompt TEXT
            )
            """
        )
        # migrate old schema with column "history"
        columns = [c[1] for c in conn.execute("PRAGMA table_info(user_contexts)")]
        if "dog_ctx" not in columns:
            conn.execute("ALTER TABLE user_contexts ADD COLUMN dog_ctx TEXT")
        if "post_ctx" not in columns:
            conn.execute("ALTER TABLE user_contexts ADD COLUMN post_ctx TEXT")
        if "history" in columns:
            conn.execute(
                "UPDATE user_contexts SET dog_ctx = history WHERE dog_ctx IS NULL"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS allowed_users (
                user_id INTEGER PRIMARY KEY
            )
            """
        )
        conn.commit()

def get_user_context(user_id: int, ctx: str = "dog") -> list:
    """Возвращает историю выбранного контекста."""
    column = "dog_ctx" if ctx == "dog" else "post_ctx"
    with sqlite3.connect(DB_FILENAME) as conn:
        cursor = conn.execute(
            f"SELECT {column} FROM user_contexts WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return []

def update_user_context(user_id: int, context: list, ctx: str = "dog") -> None:
    """Сохраняет историю указанного контекста."""
    history_json = json.dumps(context)
    with sqlite3.connect(DB_FILENAME) as conn:
        cursor = conn.execute(
            "SELECT dog_ctx, post_ctx, system_prompt FROM user_contexts WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        dog_json = row[0] if row and row[0] else "[]"
        post_json = row[1] if row and row[1] else "[]"
        system_prompt = row[2] if row and row[2] else SYSTEM_PROMPT

        if ctx == "dog":
            dog_json = history_json
        else:
            post_json = history_json

        conn.execute(
            "REPLACE INTO user_contexts (user_id, dog_ctx, post_ctx, system_prompt) VALUES (?, ?, ?, ?)",
            (user_id, dog_json, post_json, system_prompt),
        )
        conn.commit()

def clear_user_context(user_id: int, ctx: str | None = None) -> None:
    """Очищает историю: одного контекста или обоих."""
    with sqlite3.connect(DB_FILENAME) as conn:
        if ctx in ("dog", "post"):
            column = "dog_ctx" if ctx == "dog" else "post_ctx"
            conn.execute(
                f"UPDATE user_contexts SET {column} = '' WHERE user_id = ?",
                (user_id,),
            )
        else:
            conn.execute(
                "UPDATE user_contexts SET dog_ctx = '', post_ctx = '' WHERE user_id = ?",
                (user_id,),
            )
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
