import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, MessageEntity
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
)
from telegram.utils.helpers import escape_markdown
from telegram import Bot
from dotenv import load_dotenv
from os import getenv
import time 

load_dotenv()

TOKEN=getenv('TELEGRAM_TOKEN')

# Включаем логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# 🔹 Этапы диалога
CATEGORY, PRICE, DESCRIPTION, CURRENCY_TAG, IMAGES, USERDATA, CONFIRM = range(7)

# 🔹 Популярные теги валют
CURRENCY_TAGS = ["#зеленые", "#синие", "#доллар", "#европа", "#евро", "#бады", "#рубль", "#другое"]

# CHANNEL_ID = -1002535510736   # ID канала тест
CHANNEL_ID = -1002430300247 # сберобмен


# 🔹 Словарь для хранения объявлений
ads_data = {}


def escape_markdown_v2(text):
    text = str(text)
    """
    Escapes special characters in a string for use in Telegram's MarkdownV2 formatting.
    """
    # Define special characters that need to be escaped in MarkdownV2
    special_chars = r'_*[]()~`>#+-=|{}.!#'
    # Escape each character by prefixing it with a backslash
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)

def html_link_converter(link, text):
    """makes a html formatted ling from link and text"""
    return f"<a href='{link}'>{text}</a>"

def start(update: Update, context: CallbackContext):
    """Приветственное сообщение"""
    update.message.reply_text("Привет! Нажмите /create, чтобы создать объявление.")

def create(update: Update, context: CallbackContext):
    """Начало создания объявления"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or f"[{update.message.from_user.first_name}](tg://user?id={user_id})"
    
    ads_data[user_id] = {"photos": [], "username": username}  # Сохраняем данные пользователя

    keyboard = [
        [InlineKeyboardButton("💰 Куплю", callback_data="Куплю"),
         InlineKeyboardButton("💵 Продам", callback_data="Продам"),
         InlineKeyboardButton("🔄 Обменяю", callback_data="Обменяю")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text("Выберите тип объявления:", reply_markup=reply_markup)
    return CATEGORY

def set_category(update: Update, context: CallbackContext):
    """Сохранение категории объявления"""
    query = update.callback_query
    user_id = query.from_user.id
    ads_data[user_id]["category"] = query.data

    query.answer()
    query.edit_message_text(f"Вы выбрали: {query.data}")
    query.message.reply_text("Назови свою цену (в рублях):")
    return PRICE

def set_price(update: Update, context: CallbackContext):
    """Сохранение цены с валидацией"""
    user_id = update.message.from_user.id
    try:
        price = int(update.message.text)
        if price <= 0:
            raise ValueError("Цена должна быть больше 0")
        if price > 10_000_000:
            raise ValueError("Слишком большая цена, введите реальную сумму")

        ads_data[user_id]["price"] = price
        update.message.reply_text("Присылай описание объявления:")
        return DESCRIPTION
    except ValueError as e:
        update.message.reply_text(f"Ввудите цифры! Попробуйте снова.")
        return PRICE

def set_description(update: Update, context: CallbackContext):
    """Сохранение описания и запрос тега валюты"""
    user_id = update.message.from_user.id
    ads_data[user_id]["description"] = update.message.text

    keyboard = [
        [InlineKeyboardButton(tag, callback_data=tag) for tag in CURRENCY_TAGS[i:i+3]]
        for i in range(0, len(CURRENCY_TAGS), 3)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text("Выберите, какой тег валюты поставить в объявление:", reply_markup=reply_markup)
    return CURRENCY_TAG

def set_currency_tag(update: Update, context: CallbackContext):
    """Сохранение выбранного тега валюты"""
    query = update.callback_query
    user_id = query.from_user.id
    ads_data[user_id]["currency_tag"] = query.data

    query.answer(), MessageEntity
    query.edit_message_text(f"Вы выбрали тег: {query.data}")
    query.message.reply_text("Теперь отправьте хотя бы одно фото (до 10). После добавления всех фото нажмите /publish.")
    return IMAGES

def set_images(update: Update, context: CallbackContext):
    """Добавление фото"""
    user_id = update.message.from_user.id
    if len(ads_data[user_id]["photos"]) < 10:
        file_id = update.message.photo[-1].file_id
        ads_data[user_id]["photos"].append(file_id)
        update.message.reply_text(f"Фото добавлено ({len(ads_data[user_id]['photos'])}/10).")
    else:
        update.message.reply_text("Вы уже добавили 10 фото.")
    return IMAGES

def publish(update: Update, context: CallbackContext):
    """Публикация объявления"""
    user_id = update.message.from_user.id
    if user_id not in ads_data:
        update.message.reply_text("Ошибка! Начните заново с /create.")
        return ConversationHandler.END

    # Формируем текст объявления
    first_name = escape_markdown(update.effective_user.first_name, version=2)
    username = f"[{first_name}](tg://user?id={user_id})"
    category = escape_markdown(ads_data[user_id]["category"], version=2)
    price = escape_markdown(str(ads_data[user_id]["price"]), version=2)
    description = escape_markdown(ads_data[user_id]["description"], version=2)
    currency_tag = escape_markdown(ads_data[user_id].get("currency_tag", ""), version=2)
    

    text = f"{description}\n{currency_tag}\n\n*{category}* за *{price} ₽*\n\n📌 Автор: {username}"

    # Кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Опубликовать", callback_data="confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем изображение и текст объявления
    if not ads_data[user_id]["photos"]:
        update.message.reply_text(text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        # Для нескольких изображений формируем media_group
        media_group = [
            InputMediaPhoto(photo, caption=text if i == 0 else "", parse_mode="MarkdownV2")
            for i, photo in enumerate(ads_data[user_id]["photos"])
        ]
        update.message.reply_media_group(media=media_group)
        update.message.reply_text('Все оk?', reply_markup=reply_markup, parse_mode="MarkdownV2")

    return CONFIRM

# def check_user(user_id, chat_id):
#     try:
#         bot = Bot(token=TOKEN)
#         member = bot.get_chat_member(chat_id, user_id)
#         return member.status
#     except Exception as e:
#         print(f"Error: {e}")
#     return None

from telegram import ParseMode
from telegram.ext import CallbackQueryHandler, MessageHandler, Filters, CommandHandler

def send_user_data_to_owner(bot, user_data):
    # Отправка данных владельцу группы
    owner_chat_id = "OWNER_CHAT_ID"  # Замените на свой chat_id владельца группы
    message = f"ФИО: {user_data['name']}\nКорпоративная почта: {user_data['email']}"
    bot.send_message(owner_chat_id, message)

def get_user_status_in_channel(update, context):
    """Получение статуса пользователя в канале."""
    query = update.callback_query
    user_id = query.from_user.id
    
    
    try:
        chat_member = context.bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status
    except Exception as e:
        print(f"Ошибка при получении статуса пользователя: {e}")
        return None

def check_user_in_channel(update, context):
    """Проверка, находится ли пользователь в нужном статусе в группе."""
    is_user_in_channel = get_user_status_in_channel(update, context)
    if is_user_in_channel is None or is_user_in_channel not in ['creator', 'administrator', 'member']:
        # Если пользователь не в группе, сообщаем ему об этом
        # query = update.callback_query
        # query.message.reply_text("Для продолжения, пожалуйста, присоединитесь к группе.")
        # return ConversationHandler.END  # Закрываем разговор
        return False
    return True  # Статус подходящий, можно продолжить

def set_user_info(update, context):
    print('----------0-----------')
    """Запрашиваем у пользователя информацию, если он прошел проверку."""
    user_data = update.message.text
    user_info = user_data.split("\n")
    name = user_info[0] if len(user_info) > 0 else None
    email = user_info[1] if len(user_info) > 1 else None
    print('----------1-----------')
    # Проверяем, прошел ли пользователь проверку
    if check_user_in_channel(update, context):
        print('----------2-----------')
        return 

    if not name or not email:
        # Запросить ФИО и почту
        print('----------3-----------')
        context.bot.send_message(update.message.chat.id, "Пожалуйста, введите ваше ФИО и корпоративную почту.")
        return
    else:
        print('----------4-----------')
        # Если все данные собраны, отправляем их владельцу
        send_user_data_to_owner(context.bot, {'name': name, 'email': email})
        

def confirm(update: Update, context: CallbackContext):
    """Подтверждение объявления"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not check_user_in_channel(update, context):
        # Properly format the text link using HTML
        registration_link = "https://t.me/sberex_regbot"
        message = f"Вам надо зарегистрироваться тут -> {html_link_converter(registration_link, 'ссылка на регистрацию в группу СвойОбмен')}"
        query.message.reply_text(message, parse_mode="HTML")
        del ads_data[user_id]
        return ConversationHandler.END
    
    query.answer()
    query.edit_message_text("✅ Объявление опубликовано!")

    first_name = escape_markdown(query.from_user.first_name, version=2)
    username = f"[{first_name}](tg://user?id={user_id})"
    category = escape_markdown(ads_data[user_id]["category"], version=2)
    price = escape_markdown(str(ads_data[user_id]["price"]), version=2)
    description = escape_markdown(ads_data[user_id]["description"], version=2)
    currency_tag = escape_markdown(ads_data[user_id].get("currency_tag", ""), version=2)

    text = f"{description}\n{currency_tag}\n\n*{category}* за *{price} ₽*\n\n📌 Автор: {username}"

    # Отправка объявления и сохранение message_id
    if not ads_data[user_id]["photos"]:
        sent_message = context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="MarkdownV2")
        message_id = sent_message.message_id
    else:
        media_group = [InputMediaPhoto(photo, caption=text if i == 0 else "", parse_mode="MarkdownV2")
                    for i, photo in enumerate(ads_data[user_id]["photos"])]
        sent_messages = context.bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)
        message_id = sent_messages[0].message_id  # Для медиагруппы берем ID первого сообщения

    # Сохраняем информацию о сообщении для возможности удаления
    ads_data[user_id['published_message_id']] = message_id
    ads_data[user_id]['publish_time'] = time.time() 
    # Отправляем пользователю ссылку на сообщение и кнопку для удаления
    message_link = f"https://t.me/c/{str(CHANNEL_ID).replace('-100', '')}/{message_id}"
    
    keyboard = [
        [InlineKeyboardButton("🗑 Удалить объявление", callback_data=f"delete_{message_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.bot.send_message(
        chat_id=user_id,
        text=f"Ваше объявление опубликовано: {message_link}",
        reply_markup=reply_markup
    )
    
    del ads_data[user_id]
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    """Отмена публикации"""
    if update.callback_query:
        # If this is a callback query (from the button)
        query = update.callback_query
        query.answer()  # Answer to remove the loading state
        query.edit_message_text("❌ Объявление отменено.")  # Edit the message text to notify the user
    else:
        # If this is from the command "/cancel"
        update.message.reply_text("❌ Объявление отменено.")
    
    # Remove user data related to the current ad
    user_id = update.message.from_user.id if not update.callback_query else update.callback_query.from_user.id
    if user_id in ads_data:
        del ads_data[user_id]  # Clear any user-related data
    
    # End the conversation
    return ConversationHandler.END

def delete_post(update: Update, context: CallbackContext):
    """Удаление опубликованного объявления"""
    query = update.callback_query
    user_id = query.from_user.id
    message_id = int(query.data.split('_')[1])
    
    # Проверяем, есть ли данные о посте и время публикации
    if user_id not in ads_data or 'publish_time' not in ads_data[user_id]:
        query.answer("Данные об объявлении не найдены или время истекло")
        return
    
    # Проверяем, прошло ли более 5 минут (300 секунд)
    if time.time() - ads_data[user_id]['publish_time'] > 300:
        query.answer("Время для удаления истекло (5 минут)")
        query.edit_message_text("⏳ Время для удаления объявления истекло (5 минут)")
        del ads_data[user_id]  # Очищаем данные
        return
    
    try:
        # Пытаемся удалить сообщение
        context.bot.delete_message(chat_id=CHANNEL_ID, message_id=message_id)
        query.answer("Объявление удалено")
        query.edit_message_text("✅ Объявление удалено")
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщения: {e}")
        query.answer("Не удалось удалить объявление")
    finally:
        # Очищаем данные пользователя в любом случае
        if user_id in ads_data:
            del ads_data[user_id]


def main():
    """Запуск бота"""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create)],
        states={
            CATEGORY: [CallbackQueryHandler(set_category)],
            PRICE: [MessageHandler(Filters.text & ~Filters.command, set_price)],
            DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, set_description)],
            CURRENCY_TAG: [CallbackQueryHandler(set_currency_tag)],
            IMAGES: [MessageHandler(Filters.photo, set_images), CommandHandler("publish", publish)],
            CONFIRM: [
                CallbackQueryHandler(confirm, pattern='^confirm$'),
                CallbackQueryHandler(cancel, pattern='^cancel$')
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(delete_post, pattern='^delete_'))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

