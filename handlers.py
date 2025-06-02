import asyncio
import logging
from aiogram import types, Router, F, Bot
from aiogram.filters import CommandStart
import tiktoken

from config import (
    SYSTEM_PROMPT,
    TELEGRAM_BOT_TOKEN,
    POST_GENERATION_PERSONALITY,
)
from utils import (
    animate_progress,
    call_gpt_api,
    get_main_reply_keyboard,
    classify_message,
)
from db import (
    get_user_context,
    update_user_context,
    clear_user_context,
    add_allowed_user,
    is_user_allowed,
    update_system_prompt,
    get_system_prompt,
)

router = Router()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Храним только временные сообщения (формы, триггеры и т.д.)
temp_message_ids = {}

def filter_gpt_response(text: str) -> str:
    """
    Удаляем из входной строки символы: "!", "*" и "#".
    """
    symbols_to_remove = ["!", "*", "#"]
    for symbol in symbols_to_remove:
        text = text.replace(symbol, "")
    return text

FIXED_POST_PERSONALITY_PROMPT = (
    "Ты — креативный копирайтер, способный создавать уникальный контент под определённую «личность». "
    "Задача: использовать данные пользователя (ниша, цель, аудитория, формат, стиль) и продумать пост, "
    "который реально цепляет. Подробно:\n"
    "• Сформируй яркий заголовок или вступление\n"
    "• Дай структуру повествования (если подходит)\n"
    "• Добавь элементы, которые показывают «личность»: характерные словечки, манеру общения\n"
    "• Укажи, почему это подойдёт под данную аудиторию и цель\n"
    "• Приведи конкретные примеры или факты (если уместно)\n\n"
    "В конце задай риторические вопросы, которые могут усилить эффект поста, "
    "либо уточни, нужно ли добавить больше эмоциональности."
)
FIXED_POST_PERSONALITY_PROMPT = (
    "Ты — хвостатый ребёнок Алёны Янчевской, счастливо живущий под пальмами. "
    "== Роль копирайтера ==\n"
    "• Каждый раз, когда пользователь просит «пост» или «контент», уточни (если не даны): ниша, цель, аудитория, формат, стиль.\n"
    "• Затем создай пост по структуре:\n"
    "  1. Заголовок или яркое вступление\n"
    "  2. Краткий план/структура (если нужна)\n"
    "  3. Вкрапления фирменных словечек (пальма, мясо, ягодки и т. д.)\n"
    "  4. Объясни, почему пост подходит выбранной аудитории и цели\n"
    "  5. Примеры или факты (когда уместно)\n"
    "  6. Заверши риторическими вопросами или уточнением, нужно ли добавить эмоциональности\n\n"
    "== Темы и ограничения ==\n"
    "- Избегай обсуждения религии, политики и сравнений стран (особенно России и США).\n"
    "- Если запрос вне тем создания/продвижения контента, вежливо откажись и предложи вернуться к контенту.\n\n"
    "== Правило концовок ==\n"
    "Веди счётчик сообщений n = 1, 2, 3 …\n"
    "• Если n mod 4 ≠ 0 — отвечай без прощальной фразы и без ссылки.\n"
    "• Если n mod 4 = 0 — добавь В КОНЦЕ нового абзаца одну прощальную фразу из списка и одну рекламную ссылку, не повторяя ссылку подряд.\n"
    "Список прощальных фраз (без эмодзи):\n"
    "  1. «Все давай пока»\n"
    "  2. «Все, мама пришла не могу говорить»\n"
    "  3. «Все, я побежала под пальмы, пока»\n"
    "  4. «Все, папа пришёл, не могу говорить»\n"
    "  5. «Все, я спать»\n"
    "  6. «Все, я кушать, пока»\n"
    "  7. «Все, мама зовёт reels снимать, пока»\n"
    "  8. «Но если у тебя остались ко мне вопросы, не стесняйся, задавай»\n\n"
    "Ссылки (чередуй, не повторяй одну два раза подряд):\n"
    "1. https://www.instagram.com/alena_yanchevskaya\n"
    "2. https://www.instagram.com/pug__happiness\n"
    "3. https://www.instagram.com/ya__woman\n"
    "4. https://t.me/alenayanchevskaya\n"
    "5. https://t.me/yanchevskaya_reels\n"
    "6. https://t.me/ya_woman_project\n"
    "7. https://pin.it/2vdZQtc4V\n"
    "8. https://youtube.com/@alenayanchevskaya\n"
    "9. https://youtube.com/@alenayanchevskayaa\n"
    "10. https://rutube.ru/channel/39677047/\n"
    "11. https://www.tiktok.com/@alena__yanchevskaya\n"
    "12. https://vk.com/alena_yanchevskia\n\n"
    "== Технические детали ==\n"
    "- Работай только на русском языке.\n"
    "- Не используй эмодзи в ответах.\n"
    "- Помни счётчик n и переменную prev_link между сообщениями."
)
FIXED_REELS_PROMPT = (
    "Ты — эксперт по созданию динамичных и трендовых Reels, способных быстро захватывать внимание. "
    "Преврати идеи пользователя в детальные мини-сценарии, включающие:\n"
    "• Короткий, но цепкий сюжет\n"
    "• Инструменты вовлечения (музыка, текст, визуальные эффекты)\n"
    "• Пошаговые рекомендации (с чего начать, что показать в середине, как закончить)\n"
    "• Советы по хронометражу, переходам и призыву к действию\n\n"
    "Будь максимально конкретным, указывай, какие элементы стоит подчеркнуть визуально, "
    "где добавить юмор или резкие переходы. В конце упомяни, как можно ещё улучшить Reels "
    "с помощью стиля, трендовой музыки, сторителлинга или интерактивных фишек."
)

FIXED_STORIES_PROMPT = (
    "Ты — эксперт по созданию увлекательных Stories в Instagram. Тебе нужно:\n"
    "1) Предложить целостную концепцию, которая начинается с яркого введения, развивает тему "
    "и заканчивается сильным призывом.\n"
    "2) Указать пошаговые подсказки, как именно снимать и оформлять каждую «историю» (текст, опросы, квизы, "
    "визуальные эффекты и т.д.).\n"
    "3) Привести реальные примеры или шаблоны.\n"
    "4) По возможности дать советы по времени публикации и взаимодействию (опросы, вопросы, стикеры).\n\n"
    "В конце предложи идеи, как дополнительно усилить эффект: эксперимент с музыкой, анимацией, сторителлингом."
)
MODEL = "gpt-4o"
MAX_PROMPT_TOKENS = 10_000
MAX_COMPLETION_TOKENS = 2_000
ENC = tiktoken.encoding_for_model(MODEL)

def clip_history_by_tokens(history: list, extra_msgs: list) -> list:
    """Возвращает хвост history, который вместе с extra_msgs укладывается в лимит."""
    used = sum(len(ENC.encode(m["content"])) for m in extra_msgs)
    trimmed = []
    for msg in reversed(history):
        tokens = len(ENC.encode(msg["content"]))
        if used + tokens > MAX_PROMPT_TOKENS:
            break
        trimmed.append(msg)
        used += tokens
    return list(reversed(trimmed))


async def remove_previous_forms(bot: Bot, user_id: int, chat_id: int) -> None:
    if user_id in temp_message_ids:
        data = temp_message_ids[user_id]
        for key in ["standard", "trigger", "example", "form"]:
            msg_id = data.get(key)
            if msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    logging.error(f"Не удалось удалить {key}-сообщение: {e}")
        del temp_message_ids[user_id]


async def send_pinned_main_message(message: types.Message) -> None:

    main_msg = await message.answer(
        "Привет, твой доступ установлен🐾"
        "Теперь я готова помогать тебе создавать контент и вести блог🤍\n",
        reply_markup=get_main_reply_keyboard()
    )

    # Попробуем закрепить (только если группа/супергруппа и у бота есть право pin)
    try:
        await bot.pin_chat_message(
            chat_id=message.chat.id,
            message_id=main_msg.message_id,
            disable_notification=True
        )
    except Exception as e:
        logging.warning(f"Не удалось закрепить сообщение (возможно личка или нет прав): {e}")


@router.message(CommandStart())
async def start_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    command_parts = message.text.split(maxsplit=1)

    if is_user_allowed(user_id):
        await send_pinned_main_message(message)
        return
    else:
        if len(command_parts) > 1 and command_parts[1] == "secretdog":
            add_allowed_user(user_id)
            await send_pinned_main_message(message)
            return
        else:
            await message.answer(
                "🚫Нет доступа! Нужно использовать ссылку с ключом или обратиться к администратору."
            )

@router.message(F.text == "🗑 Стереть историю")
async def clear_history_handler(message: types.Message) -> None:
    clear_user_context(message.from_user.id)
    await message.answer("История сообщений очищена.")


@router.message(F.text == "Стандартная модель")
async def set_standard_personality_handler(message: types.Message, bot: Bot) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем прошлые формы
    await remove_previous_forms(bot, user_id, chat_id)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение пользователя: {e}")

    update_system_prompt(user_id, SYSTEM_PROMPT)

    info_msg = await message.answer("Системный промпт переключен на стандартную модель.")
    temp_message_ids[user_id] = {"standard": info_msg.message_id}


@router.message(F.text == "Напиши пост")
async def set_post_generation_personality_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id

    await remove_previous_forms(bot, user_id, chat_id)

    temp_message_ids[user_id] = {"trigger": message.message_id}

    # Отправляем пример + форму
    example_text = (
        "Представь, что ты опытный копирайтер, способный создавать уникальные посты, опираясь на актуальные тренды и исследования. Придумай пост для меня\n\n"
        "Пример (как заполнить форму):\n"
        "Ниша: блог о путешествиях\n"
        "Цель: вдохновить читателей\n"
        "Аудитория: люди 25-40 лет, стремящиеся к новому опыту\n"
        "Формат: нарратив с элементами описания\n"
        "Стиль: творческий, эмоциональный и информативный\n"
    )
    form_text = (
        "Промт: Личность генерации постов\n"
        "Ниша:\n"
        "Цель:\n"
        "Аудитория:\n"
        "Формат:\n"
        "Стиль:"
    )

    ex_msg = await message.answer(example_text)
    fm_msg = await message.answer(form_text)

    temp_message_ids[user_id]["example"] = ex_msg.message_id
    temp_message_ids[user_id]["form"] = fm_msg.message_id

@router.message(lambda m: m.text and m.text.startswith("Промт: Личность генерации постов"))
async def custom_post_personality_handler(message: types.Message, bot: Bot) -> None:
    lines = message.text.splitlines()
    if len(lines) < 6:
        await message.answer("Неверный формат формы. Попробуйте снова.")
        return

    try:
        niche = lines[1].split(":", 1)[1].strip()
        goal = lines[2].split(":", 1)[1].strip()
        audience = lines[3].split(":", 1)[1].strip()
        format_field = lines[4].split(":", 1)[1].strip()
        style_field = lines[5].split(":", 1)[1].strip()
    except Exception as e:
        logging.error(f"Ошибка разбора формы: {e}")
        await message.answer("Пожалуйста, заполните форму аккуратно.")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем trigger/example/form
    if user_id in temp_message_ids:
        data = temp_message_ids[user_id]
        for key in ["trigger", "example", "form"]:
            msg_id = data.get(key)
            if msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as exc:
                    logging.error(f"Не удалось удалить {key}-сообщение: {exc}")
        del temp_message_ids[user_id]

    # Формируем prompt
    custom_prompt = FIXED_POST_PERSONALITY_PROMPT.format(
        niche=niche,
        goal=goal,
        audience=audience,
        format_field=format_field,
        style_field=style_field
    )

    # GPT
    context = get_user_context(user_id)
    context.append({"role": "user", "content": message.text})

    animation_msg = await message.answer("Запрос принят, обрабатываю...")
    animation_task = asyncio.create_task(animate_progress(animation_msg))

    answer = await call_gpt_api(context, custom_prompt)
    answer = filter_gpt_response(answer)

    animation_task.cancel()
    try:
        await animation_task
    except asyncio.CancelledError:
        pass

    context.append({"role": "assistant", "content": answer})
    update_user_context(user_id, context)

    try:
        await animation_msg.edit_text(answer)
    except Exception as exc:
        logging.error(f"Ошибка обновления ответа: {exc}")


#########################################
# "Придумай Reels"
#########################################
@router.message(F.text == "Придумай Reels")
async def set_reels_prompt_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id

    await remove_previous_forms(bot, user_id, chat_id)

    temp_message_ids[user_id] = {"trigger": message.message_id}

    example_text = (
        "Представь, что ты опытный сценарист коротких роликов и формируешь идеи контента исходя из популярных исследований, связанных с Reels/TikTok. Придумай темы для Reels для меня\n\n"
        "Пример (как заполнить форму):\n"
        "Ниша: нутрициология\n"
        "Цель контента: развеять миф о вреде углеводов\n"
        "Аудитория: женщины 30+, которые боятся кушать хлеб, гречку и полностью отказываются от него\n"
        "Формат: экспертный, но при этом легкий для восприятия\n"
        "Стиль: с юмором\n"
    )
    form_text = (
        "Промт: Придумай Reels\n"
        "Ниша:\n"
        "Цель контента:\n"
        "Аудитория:\n"
        "Формат:\n"
        "Стиль:"
    )

    ex_msg = await message.answer(example_text)
    fm_msg = await message.answer(form_text)

    temp_message_ids[user_id]["example"] = ex_msg.message_id
    temp_message_ids[user_id]["form"] = fm_msg.message_id

@router.message(lambda m: m.text and m.text.startswith("Промт: Придумай Reels"))
async def custom_reels_handler(message: types.Message, bot: Bot) -> None:
    lines = message.text.splitlines()
    if len(lines) < 6:
        await message.answer("Неверный формат формы для Reels.")
        return

    try:
        niche = lines[1].split(":", 1)[1].strip()
        goal = lines[2].split(":", 1)[1].strip()
        audience = lines[3].split(":", 1)[1].strip()
        format_field = lines[4].split(":", 1)[1].strip()
        style_field = lines[5].split(":", 1)[1].strip()
    except Exception as e:
        logging.error(f"Ошибка разбора формы Reels: {e}")
        await message.answer("Ошибка при обработке формы.")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id in temp_message_ids:
        data = temp_message_ids[user_id]
        for key in ["trigger", "example", "form"]:
            msg_id = data.get(key)
            if msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as exc:
                    logging.error(f"Не удалось удалить {key}-сообщение: {exc}")
        del temp_message_ids[user_id]

    custom_prompt = FIXED_REELS_PROMPT.format(
        niche=niche,
        goal=goal,
        audience=audience,
        format_field=format_field,
        style_field=style_field
    )

    context = get_user_context(user_id)
    context.append({"role": "user", "content": message.text})

    animation_msg = await message.answer("Запрос принят, обрабатываю...")
    animation_task = asyncio.create_task(animate_progress(animation_msg))

    answer = await call_gpt_api(context, custom_prompt)
    answer = filter_gpt_response(answer)

    animation_task.cancel()
    try:
        await animation_task
    except asyncio.CancelledError:
        pass

    context.append({"role": "assistant", "content": answer})
    update_user_context(user_id, context)

    try:
        await animation_msg.edit_text(answer)
    except Exception as exc:
        logging.error(f"Ошибка обновления ответа: {exc}")

#########################################
# "Что показать в stories"
#########################################
@router.message(F.text == "Что показать в stories")
async def set_stories_prompt_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id

    await remove_previous_forms(bot, user_id, chat_id)

    temp_message_ids[user_id] = {"trigger": message.message_id}

    example_text = (
        "Представь, что ты опытный сценарист для Instagram Stories, создающий вовлекающие истории. Придумай идеи для меня.\n\n"
        "Пример (как заполнить форму):\n"
        "Ниша: продажи\n"
        "Цель: прогреть аудиторию\n"
        "Аудитория: начинающие онлайн-специалисты\n"
        "Формат: сторис с личным видео и интерактивом\n"
        "Стиль: уверенный, мотивирующий\n"
    )
    form_text = (
        "Промт: Что показать в stories\n"
        "Ниша:\n"
        "Цель:\n"
        "Аудитория:\n"
        "Формат:\n"
        "Стиль:"
    )

    ex_msg = await message.answer(example_text)
    fm_msg = await message.answer(form_text)

    temp_message_ids[user_id]["example"] = ex_msg.message_id
    temp_message_ids[user_id]["form"] = fm_msg.message_id

@router.message(lambda m: m.text and m.text.startswith("Промт: Что показать в stories"))
async def custom_stories_handler(message: types.Message, bot: Bot) -> None:
    lines = message.text.splitlines()
    if len(lines) < 6:
        await message.answer("Неверный формат формы для Stories.")
        return

    try:
        niche = lines[1].split(":", 1)[1].strip()
        goal = lines[2].split(":", 1)[1].strip()
        audience = lines[3].split(":", 1)[1].strip()
        format_field = lines[4].split(":", 1)[1].strip()
        style_field = lines[5].split(":", 1)[1].strip()
    except Exception as e:
        logging.error(f"Ошибка при обработке формы Stories: {e}")
        await message.answer("Ошибка при обработке формы.")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id in temp_message_ids:
        data = temp_message_ids[user_id]
        for key in ["trigger", "example", "form"]:
            msg_id = data.get(key)
            if msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as exc:
                    logging.error(f"Не удалось удалить {key}-сообщение: {exc}")
        del temp_message_ids[user_id]

    custom_prompt = FIXED_STORIES_PROMPT.format(
        niche=niche,
        goal=goal,
        audience=audience,
        format_field=format_field,
        style_field=style_field
    )

    context = get_user_context(user_id)
    context.append({"role": "user", "content": message.text})

    animation_msg = await message.answer("Запрос принят, обрабатываю...")
    animation_task = asyncio.create_task(animate_progress(animation_msg))

    answer = await call_gpt_api(context, custom_prompt)
    answer = filter_gpt_response(answer)

    animation_task.cancel()
    try:
        await animation_task
    except asyncio.CancelledError:
        pass

    context.append({"role": "assistant", "content": answer})
    update_user_context(user_id, context)

    try:
        await animation_msg.edit_text(answer)
    except Exception as exc:
        logging.error(f"Ошибка обновления ответа: {exc}")

#########################################
# Если не подходит ни под одну кнопку/форму
#########################################
@router.message(lambda m: m.text and not m.text.startswith('/'))
async def gpt_handler(message: types.Message) -> None:
    user_id = message.from_user.id

    # 1. проверка доступа
    if not is_user_allowed(user_id):
        await message.answer("Нет доступа.")
        return

    # 2. определяем тип запроса
    ctx_type = await classify_message(message.text)

    # 3. загружаем полную историю
    full_history = get_user_context(user_id, ctx=ctx_type)

    # 4. формируем историю для GPT (последние 20 сообщений + текущий)
    history_for_gpt = full_history[-20:] + [{"role": "user", "content": message.text}]

    system_prompt = (
        POST_GENERATION_PERSONALITY if ctx_type == "POST" else SYSTEM_PROMPT
    )

    logging.info(
        f"UID={user_id} | ctx={ctx_type.lower()}_ctx | prompt={system_prompt[:10]}"
    )

    # 5. вызываем GPT
    anim_msg = await message.answer("Запрос принят, обрабатываю...")
    anim_task = asyncio.create_task(animate_progress(anim_msg))

    answer = await call_gpt_api(history_for_gpt, system_prompt)
    answer = filter_gpt_response(answer)

    anim_task.cancel()
    try:
        await anim_task
    except asyncio.CancelledError:
        pass

    # 6. сохраняем историю (только две реплики)
    full_history.append({"role": "user", "content": message.text})
    full_history.append({"role": "assistant", "content": answer})
    update_user_context(user_id, full_history, ctx=ctx_type)

    # 7. отправляем результат
    try:
        await anim_msg.edit_text(answer)
    except Exception as exc:
        logging.error(f"Ошибка обновления ответа: {exc}")
