import csv
import re
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from telegram.utils.helpers import escape_markdown
from sberexchange_bot import html_link_converter

from dotenv import load_dotenv
from os import getenv

load_dotenv()

TOKEN=getenv('REGISTRATION_BOT_TELEGRAM_TOKEN')
# Состояния для ConversationHandler
FIRST_NAME, LAST_NAME, EMAIL = range(3)

# Файл для записи данных
CSV_FILE = 'user_registration.csv'

# Функция для записи данных в CSV файл
def write_to_csv(user_data):
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(user_data)

# Валидация email с помощью регулярных выражений
def is_valid_email(email):
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(email_regex, email) is not None

# Обработчик команды /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Я бот-регистратор. Давайте начнем регистрацию. Пожалуйста, введите ваше Имя и Отчество")
    return FIRST_NAME  # Переходим к следующему состоянию

# Получаем имя сотрудника
def get_first_name(update: Update, context: CallbackContext):
    context.user_data['first_name'] = update.message.text
    update.message.reply_text("Теперь, скажите в каком сервисе сбера можно проверить коллегу ?")
    return LAST_NAME  # Переходим к следующему состоянию

# Получаем фамилию сотрудника
def get_last_name(update: Update, context: CallbackContext):
    context.user_data['last_name'] = update.message.text
    update.message.reply_text("Теперь, пожалуйста, введите ваш корпоративный email.")
    return EMAIL  # Переходим к следующему состоянию

# Получаем email сотрудника с валидацией
def get_email(update: Update, context: CallbackContext):
    email = update.message.text
    if not is_valid_email(email):
        update.message.reply_text("Неверный формат email. Пожалуйста, введите правильный email.")
        return EMAIL  # Повторяем запрос на email

    context.user_data['email'] = email

    # Собираем дополнительные данные из Telegram
    username = update.message.from_user.username
    user_id = update.message.from_user.id
    name = update.message.from_user.full_name
    phone_number = update.message.contact.phone_number if update.message.contact else 'Не указано'

    # Записываем данные в CSV
    user_data = [
        context.user_data['first_name'],
        context.user_data['last_name'],
        context.user_data['email'],
        username,
        user_id,
        name,
        phone_number
    ]
    write_to_csv(user_data)

    # Отправляем данные пользователю с user_id = 7964402415
    target_user_id = 7964402415  # Замените на нужный user_id
    context.bot.send_message(
        chat_id=target_user_id,
        text=f"Новый пользователь зарегистрирован!\n\n"
             f"Имя: {user_data[0]}\n"
             f"Фамилия: {user_data[1]}\n"
             f"Email: {user_data[2]}\n"
             f"Username: {user_data[3]}\n"
             f"User ID: {user_data[4]}\n"
             f"Name: {user_data[5]}\n"
             f"Phone: {user_data[6]}"
    )
    link = "https://t.me/+iiwp9IkYXhM4MDE0"
    text = (f"Регистрация завершена! Ваши данные:\n{user_data[0]}, {user_data[2]}\n"
            f"Мы все проверим и вас одобрим, а пока подавайте заявку на вступление в {html_link_converter(link, 'канал СвойОбмен где появится ваше объявление')}")
    # text = escape_markdown(text, version=2)
    update.message.reply_text(text, parse_mode="HTML")
                            #   f"Username: {user_data[3]}\nUser ID: {user_data[4]}\nName: {user_data[5]}\nPhone: {user_data[6]}")

    # Завершаем разговор
    return ConversationHandler.END

# Обработчик отмены регистрации
def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Регистрация отменена.")
    return ConversationHandler.END

def main():
    """Запуск бота"""
    updater = Updater(TOKEN)  # Замените на ваш токен
    dp = updater.dispatcher

    # Настроим ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FIRST_NAME: [MessageHandler(Filters.text & ~Filters.command, get_first_name)],
            LAST_NAME: [MessageHandler(Filters.text & ~Filters.command, get_last_name)],
            EMAIL: [MessageHandler(Filters.text & ~Filters.command, get_email)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
