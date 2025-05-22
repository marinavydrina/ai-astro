print("=== BOT STARTED ===")

import os
import sqlite3
import traceback
from aiogram import Bot, Dispatcher, types, executor
from openai import OpenAI

# Получение переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')

print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
print(f"OPENAI_API_KEY: {OPENAI_API_KEY}")
print(f"ASSISTANT_ID: {ASSISTANT_ID}")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
client = OpenAI(api_key=OPENAI_API_KEY)

# SQLite для хранения user_id <-> thread_id
conn = sqlite3.connect('db.sqlite')
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS threads (user_id INTEGER PRIMARY KEY, thread_id TEXT)")
conn.commit()

DEFAULT_ASTRO = "Солнце в Рыбах, Луна в Овне, Меркурий в Водолее, Венера в Козероге, Марс в Козероге, Юпитер в Раке, Сатурн в Козероге, Уран в Козероге, Нептун в Козероге, Плутон в Скорпионе."

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Привет! Я ИИ-астролог. Просто напиши мне вопрос о своей натальной карте!")

def get_or_create_thread(user_id):
    cursor.execute("SELECT thread_id FROM threads WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    thread = client.beta.threads.create()
    thread_id = thread.id
    cursor.execute("INSERT INTO threads (user_id, thread_id) VALUES (?, ?)", (user_id, thread_id))
    conn.commit()
    return thread_id

@dp.message_handler()
async def handle_message(message: types.Message):
    print(f"Получено сообщение: {message.text} от user_id {message.from_user.id}")
    try:
        user_id = message.from_user.id
        thread_id = get_or_create_thread(user_id)
        print(f"Thread id для пользователя: {thread_id}")

        content = (
            f"Натальная карта пользователя: {DEFAULT_ASTRO}\n"
            f"Вопрос пользователя: {message.text}\n"
            f"Ответь строго на этот вопрос, используя натальную карту. Не повторяй предыдущие ответы, каждый раз используй новый анализ."
        )

        # Создаём сообщение в треде и сохраняем id этого сообщения
        user_msg = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )
        user_msg_id = user_msg.id

        # Запускаем ассистента
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        import time
        while True:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run.status == "completed":
                break
            time.sleep(1)

        # Даем ассистенту доп. время, чтобы точно сохранить ответ
        time.sleep(2)

        # Получаем все сообщения в треде и печатаем их
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        print("=== СООБЩЕНИЯ В ТРЕДЕ ===")
        for idx, m in enumerate(messages.data):
            role = m.role
            mid = m.id
            text = m.content[0].text.value if m.content else "[no content]"
            print(f"{idx}: role={role} | id={mid} | text={text}")

        # Поиск ответа ассистента, который идёт сразу после user_msg
        bot_reply = ""
        found = False
        for i, m in enumerate(messages.data):
            if m.id == user_msg_id:
                # Ответ ассистента должен быть ближе к началу (меньше индекс)
                if i > 0:
                    next_msg = messages.data[i-1]
                    if next_msg.role == "assistant":
                        bot_reply = next_msg.content[0].text.value
                        found = True
                        break
        if not found:
            # fallback — просто последний ассистентский (на всякий случай)
            for m in messages.data:
                if m.role == "assistant":
                    bot_reply = m.content[0].text.value
                    break

        print(f"Ответ ассистента: {bot_reply}")
        await message.answer(bot_reply)

    except Exception as e:
        print("=== ОШИБКА В ХЕНДЛЕРЕ ===")
        print(f"Ошибка в обработке сообщения: {e}")
        print(traceback.format_exc())
        await message.answer("Извините, произошла ошибка. Попробуйте позже.")

if __name__ == "__main__":
    executor.start_polling(dp)
