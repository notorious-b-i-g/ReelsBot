import asyncio
import logging
import aiohttp
from aiogram import types
from config import OPENAI_API_KEY, PROXY_URL, PROXY_AUTH, SYSTEM_PROMPT

async def animate_progress(message: types.Message) -> None:
    """
    Показываем анимацию точки-запятая, пока генерируется ответ.
    """
    base_text = "Запрос принят, обрабатываю"
    last_text = ""
    i = 0
    try:
        while True:
            dots = '.' * ((i % 5) + 1)
            new_text = f"{base_text}{dots}"
            if new_text != last_text:
                try:
                    await message.edit_text(new_text)
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logging.error(f"Ошибка обновления анимации: {e}")
                last_text = new_text
            i += 1
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        return

async def call_gpt_api(history: list, system_prompt: str) -> str:
    """
    Отправка запроса к GPT-API с учётом истории диалога + системного промпта.
    """
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    messages = [{"role": "system", "content": system_prompt}] + history
    data = {
        "model": "gpt-4o",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000,
        "top_p": 0.9,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.2
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers=headers,
            json=data,
            proxy=PROXY_URL,
            proxy_auth=PROXY_AUTH
        ) as response:
            if response.status == 200:
                result = await response.json()
                try:
                    return result["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    return "Не удалось разобрать ответ GPT API."
            else:
                error_text = await response.text()
                logging.error(f"Ошибка GPT API: {response.status} - {error_text}")
                return "Ошибка при вызове GPT API."

def get_main_reply_keyboard() -> types.ReplyKeyboardMarkup:
    """
    Главное меню с кнопками.
    """
    kb = [
        [types.KeyboardButton(text="🗑 Стереть историю")],
        [
            types.KeyboardButton(text="Стандартная модель"),
            types.KeyboardButton(text="Напиши пост")
        ],
        [
            types.KeyboardButton(text="Придумай Reels"),
            types.KeyboardButton(text="Что показать в stories")
        ]
    ]
    return types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        one_time_keyboard=False
    )
