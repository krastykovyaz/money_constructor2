import os
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()
# Создаем экземпляр бота с токеном
bot = Bot(os.environ["SBER_EXCHANGE_BOT_TOKEN"])

# Проверка статуса пользователя в группе
user_id = 7964402415  # Замените на нужный user_id
chat_id = -1002535510736  # ID группы

def check_user(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status
    except Exception as e:
        print(f"Error: {e}")
    return None





