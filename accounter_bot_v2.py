import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
)

# Включаем логированиеfrom telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
)
from datetime import datetime
import pandas as pd
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["ACCOUNTER_BOT_TOKEN"]

# TRANSACTIONS_FILE = "transactions2.xlsx" # orig
# TRANSACTIONS_FILE_serg = "transactions22.xlsx" # tmp
# TRANSACTIONS_FILE_ivan = "transactions22.xlsx" # tmp
# CHAT_ID = "-1002596355233" # tmp
CHAT_ID_SERG = -1002402146131 # orig
CHAT_ID_IVAN = -1002402146131

# At the top with other constants:
FILE_OPTIONS = {
    1908371931: "transactions22_serg.xlsx",  # Serg's file
    669446393: "transactions23_ivan.xlsx",  # Ivan's file
    8159819525: "transactions23_ivan.xlsx",  
    7964402415:"transactions23_ivan.xlsx"
}
USERS = {669446393:'SERG', 1908371931:'IVAN', 8159819525:'KOVY', 7964402415:'KOLYA'}
FILE_CHANNEL_MAP = {"transactions22_serg.xlsx": CHAT_ID_SERG,
                    "transactions23_ivan.xlsx":CHAT_ID_IVAN}

TRANSACTIONS_FILE = None  # Default file
ALLOWED_USER_IDS = [8159819525]  # Replace with actual admin user IDs

def check_user(user_id):
    if user_id in list(USERS.keys()):
        return True
    return False
    

# Инициализация бота
bot = Bot(token=TOKEN)

# Глобальные переменные для хранения данных
user_balances = {'SERG':{}, 'IVAN':{}, 'KOVY':{}, 'KOLYA':{}}
pending_transactions = {}
CURRENCIES = ["Рубль наличные", "Рубль онлайн", "Синий доллар", "Зеленый доллар", "Евро", "Синий доллар займ",
              "Зеленый доллар займ", "Евро займ"]
PROFITS = {"За день":'day', "За неделю":'week', "За месяц":'month', "За последнюю сделку":'transaction', "За все время":'all_days'}
cur_map = {"rub_cash":"Рубль наличные", "rub_online":"Рубль онлайн", 
            "blue_dol":"Синий доллар", "green_dol":"Зеленый доллар", "euro":"Евро",
            "blue_dollar_loan":"Синий доллар займ", "green_dollar_loan":"Зеленый доллар займ",
            "euro_loan":"Евро займ"}

def get_balance_text(user_id: int) -> str:
    """Возвращает форматированный текст с балансом пользователя."""
    # if user_id not in user_balances[USERS[user_id]]:
    #     user_balances[USERS[user_id]][user_id] = {cur: 0 for cur in CURRENCIES}
    load_balances()
    global user_balances
    
    balances = defaultdict(int)
    for cur in list(user_balances[USERS[user_id]].keys()):
        balances[cur] += int(user_balances[USERS[user_id]][cur])

    # print(balances)
    # print('-----------')
    balance_text = "\n".join([f"{cur}: {int(amt)}" for cur, amt in balances.items() if cur not in ["Добавить в кошелек", "Изъять из кошелек"]])
    # print(balance_text)
    return f"📊 Ваш баланс:\n{balance_text}"

def send_transaction_to_group(transaction_text, user_id):
    """Отправляет сообщение о сделке в Telegram-группу."""
    try:
        bot.send_message(chat_id=FILE_CHANNEL_MAP[FILE_OPTIONS[user_id]], text=transaction_text, parse_mode='Markdown')
    except Exception as e:
        print(f"Ошибка при отправке сообщения в группу: {e}")

def save_transaction(user_id, transaction_type, currency_in, amount_in, currency_out=0, amount_out=0, exchange_rate=None):
    """Сохраняет данные о сделке в Excel, записывая изменения баланса по всем валютам."""
    transaction_data = {
        "Дата": datetime.now().strftime("%Y-%m-%d"),
        "Время": datetime.now().strftime("%H:%M:%S"),
        "Пользователь ID": user_id,
        "Тип": transaction_type,
        "Курс": exchange_rate if exchange_rate else "-"
    }
    
    for cur in CURRENCIES:
        if cur == currency_in:
            transaction_data[cur] = amount_in
        elif cur == currency_out:
            transaction_data[cur] = -amount_out
        else:
            transaction_data[cur] = 0
    
    df = pd.DataFrame([transaction_data])
    
    try:
        # TRANSACTIONS_FILE = check_user_file(TRANSACTIONS_FILE, user_id)
        existing_df = pd.read_excel(FILE_OPTIONS[user_id])
        df = pd.concat([existing_df, df], ignore_index=True)
    except FileNotFoundError:
        pass  # Файл создастся при первой записи
    # TRANSACTIONS_FILE = check_user_file(TRANSACTIONS_FILE, user_id)
    df.to_excel(FILE_OPTIONS[user_id], index=False)
    if int(amount_out) != 0:
        transaction_text = (f"Сделка:\n"
                            f"```{currency_in} +{amount_in}\n```"
                            f"```{currency_out} -{amount_out}\n```"
                            f"Курс {exchange_rate}")
    elif int(amount_in) > 0:
        transaction_text = (f"Пополнение кошелька:\n"
                            f"```{currency_in} +{amount_in}```")
    elif int(amount_in) < 0:
        transaction_text = (f"Изъятие из кошелька:\n"
                            f"```{currency_in} {amount_in}```")
    send_transaction_to_group(transaction_text, user_id)

def load_balances():
    """Загружает данные из Excel и рассчитывает баланс каждого пользователя."""
    global user_balances, FILE_OPTIONS
    user_balances = {'SERG':{}, 'IVAN':{}, 'KOVY':{}, 'KOLYA':{}}  # Сбрасываем перед загрузкой
    # TRANSACTIONS_FILE = check_user_file(TRANSACTIONS_FILE)
    # user_balance = {}
    for k, file in FILE_OPTIONS.items():
        try:
            df = pd.read_excel(file)
            # print(file)
            for _, row in df.iterrows():
                # user_id = row["Пользователь ID"]
                if USERS[k] not in user_balances or user_balances[USERS[k]] == {}:
                    user_balances[USERS[k]] = {cur: 0 for cur in CURRENCIES}
                # print(user_balances)
                for cur in CURRENCIES:
                    user_balances[USERS[k]][cur] += row[cur]
            
        except FileNotFoundError:
            print("Файл транзакций отсутствует, создаем новый баланс с нуля.")
        except Exception as e:
            print(f"Ошибка при загрузке баланса: {e}")
    

def start(update: Update, context: CallbackContext):
    """Обрабатывает команду /start."""
    user_id = update.effective_user.id
    if check_user(user_id):
        # user_balances[USERS[user_id]] =  {cur: 0 for cur in CURRENCIES}

        keyboard = [[InlineKeyboardButton(cur, callback_data=f"add_{cur}")] for cur in CURRENCIES]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text("Привет! Выберите валюту для пополнения:", reply_markup=reply_markup)
    else:
        update.message.reply_text("Привет! Мы не знакомы:(")

def profit_transaction_logic(in_cur, out_cur, user_id):
    if 'займ' not in in_cur.lower() and 'займ' not in out_cur.lower():
        out = profit_transaction(False, user_id)
        return f"Профит за сделку: {out} руб\n"
    elif 'займ' in in_cur.lower() and 'займ' not in out_cur.lower():
        out = profit_transaction(in_cur, user_id)
        if 'нужно' in str(out).lower():
            return out
        return f"Профит за сделку: {out} руб\n"
    elif 'займ' not in in_cur.lower() and 'займ' in out_cur.lower():
        out = profit_transaction(out_cur, user_id)
        if 'нужно' in str(out).lower():
            return out
        return f"Профит за сделку: {out} руб\n"
    print(in_cur, out_cur)
    return ''
    

def profit_transaction(is_loan, user_id):
    from profit_calculation import Profit
    # TRANSACTIONS_FILE = check_user_file(TRANSACTIONS_FILE, user_id)
    ptf = Profit(FILE_OPTIONS[user_id])
    out = ptf.get_profit('transaction', is_loan)
    return out

def profit(update: Update, context: CallbackContext):
    """Обрабатывает команду /profit."""
    user_id = update.effective_user.id
    if check_user(user_id):
        # user_balances.setdefault(user_id, {prf: 0 for prf in list(PROFITS.keys())})

        keyboard = [[InlineKeyboardButton(prf, callback_data=f"profit_{prf}")] for prf in list(PROFITS.keys()) if prf != "За последнюю сделку"]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text("Выберите интересующий профит:", reply_markup=reply_markup)
    else:
        update.message.reply_text("Привет! Мы не знакомы:(")

def handle_currency_selection(update: Update, context: CallbackContext):
    """Обрабатывает выбор валюты для пополнения."""
    query = update.callback_query
    query.answer()

    user_id = query.from_user.id
    currency = query.data.split("_")[1]
    pending_transactions[user_id] = {"add_currency": currency}

    query.edit_message_text(f"Введите сумму пополнения для {currency}:")
    context.user_data["awaiting_add_amount"] = True  # Устанавливаем состояние ожидания суммы пополнения

def handle_profit_selection(update: Update, context: CallbackContext):
    """Обрабатывает выбор валюты для пополнения."""
    query = update.callback_query
    query.answer()

    user_id = query.from_user.id
    profit_select = query.data.split("_")[1]
    req = PROFITS[profit_select]
    # pending_transactions[user_id] = {"add_currency": currency}
    from profit_calculation import Profit
    # TRANSACTIONS_FILE = check_user_file(TRANSACTIONS_FILE, user_id)
    prf = Profit(FILE_OPTIONS[user_id])
    res = prf.get_profit(req, False)

    query.edit_message_text(f"Профит - {profit_select}: {res} руб")
    # context.user_data["awaiting_add_amount"] = True  # Устанавливаем состояние ожидания суммы пополнения

def handle_add_amount(update: Update, context: CallbackContext):
    """Обрабатывает ввод суммы пополнения и запрашивает валюту для списания."""
    if update.message is not None:
        user_id = update.message.from_user.id
        
        # Проверяем, что это сообщение для пополнения, а не для списания
        if "awaiting_subtract_amount" in context.user_data:
            handle_subtract_amount(update, context)
            return  # Пропускаем, если ожидается сумма списания

        if "awaiting_add_amount" not in context.user_data or not update.message.text.isdigit():
            update.message.reply_text("❌ Введите корректную сумму пополнения (число).")
            return
        
        # Сохраняем сумму пополнения
        pending_transactions[user_id]["add_amount"] = int(update.message.text)
        
        del context.user_data["awaiting_add_amount"]  # Очищаем состояние
        
        # Запрашиваем валюту для списания
        keyboard = [[InlineKeyboardButton(cur, callback_data=f"subtract_{cur}")] for cur in CURRENCIES]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text("Выберите валюту для списания:", reply_markup=reply_markup)


def handle_subtract_currency(update: Update, context: CallbackContext):
    """Обрабатывает выбор валюты для списания и запрашивает сумму списания."""
    query = update.callback_query
    query.answer()

    user_id = query.from_user.id
    currency = query.data.split("_")[1]
    pending_transactions[user_id]["subtract_currency"] = currency
    
    
    # Устанавливаем флаг для ожидания суммы списания
    context.user_data["awaiting_subtract_amount"] = True

    query.edit_message_text(f"Введите сумму списания для {currency}:")



def handle_subtract_amount(update: Update, context: CallbackContext):
    """Обрабатывает ввод суммы списания и выводит подтверждение сделки."""
    user_id = update.message.from_user.id
    message_text = update.message.text
    # print('-------------')
    # print(f"[DEBUG] handle_subtract_amount called with text: {message_text}")  # Отладочное сообщение

    # Проверяем, что ожидается сумма списания
    if "awaiting_subtract_amount" not in context.user_data:
        # print("[DEBUG] awaiting_subtract_amount flag is missing.")  # Отладочное сообщение
        return

    # Проверяем, что введено число
    if not message_text.isdigit():
        update.message.reply_text("❌ Введите корректную сумму списания (число).")
        return

    # Сохраняем сумму списания
    subtract_amount = int(message_text)
    pending_transactions[user_id]["subtract_amount"] = subtract_amount
    del context.user_data["awaiting_subtract_amount"]  # Очищаем состояние

    # Получаем данные о сделке
    add_currency = pending_transactions[user_id]["add_currency"]
    add_amount = pending_transactions[user_id]["add_amount"]
    subtract_currency = pending_transactions[user_id]["subtract_currency"]

    # Рассчитываем курс обмена
    if add_amount > subtract_amount:
        exchange_rate = round(add_amount / subtract_amount, 2)
        rate_text = f"📉 1 {subtract_currency} ≈ {round(exchange_rate,2)} {add_currency}"
    else:
        exchange_rate = round(subtract_amount / add_amount, 2)
        rate_text = f"📉 1 {add_currency} ≈ {round(exchange_rate,2)} {subtract_amount}"

    # if subtract_currency.startswith("Рубль"):
    #     cost_per_unit = round(subtract_amount / add_amount, 2)
    #     rate_text = f"📉 Стоимость 1 рубля: {round(cost_per_unit,2)} {add_currency}"
    # else:
    #     cost_per_unit = round(add_amount / subtract_amount, 4)
    # rate_text = f"📉 1 {subtract_currency} ≈ {round(cost_per_unit,2)} {add_currency}"

    # Получаем текущий баланс
    balance_text = get_balance_text(user_id)
    # profit_value = profit_transaction_logic(add_currency, subtract_currency)
    # Формируем текст для подтверждения
    confirm_text = (f"```{balance_text}```\n\n"
                    f"🔄 Сделка:\n"
                    f"➕ {add_amount} {add_currency}\n"
                    f"➖ {subtract_amount} {subtract_currency}\n"
                    f"\n**{exchange_rate}** {add_currency} за **1** {subtract_currency}\n"
                    # f"{rate_text}\n"
                    # f"Подтвердить?"
                    # f"{profit_value}\n"
                    )

    # Создаем клавиатуру для подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ]

    # Отправляем сообщение с подтверждением
    update.message.reply_text(confirm_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    print("[DEBUG] Confirmation message sent.")  # Отладочное сообщение


def confirm_transaction(update: Update, context: CallbackContext):
    """Обрабатывает подтверждение или отмену сделки."""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id

    if query.data == "cancel":
        pending_transactions.pop(user_id, None)
        query.edit_message_text("🚫 Сделка отменена.")
        return

    # Обновляем баланс
    transaction = pending_transactions.pop(user_id, {})
    add_currency = transaction.get("add_currency")
    add_amount = transaction.get("add_amount", 0)
    subtract_currency = transaction.get("subtract_currency")
    subtract_amount = transaction.get("subtract_amount", 0)
    balances = defaultdict(int)
    for cur in list(user_balances[USERS[user_id]].keys()):
        balances[cur] += int(user_balances[USERS[user_id]][cur])

    if balances[subtract_currency] < subtract_amount:
        query.edit_message_text(f"❌ Ошибка: недостаточно средств на балансе {subtract_currency}.")
        return
    if subtract_currency == add_currency:
        query.edit_message_text("❌ Введите валюту списания отличную от валюты пополнения.")
        return

    user_balances[USERS[user_id]][add_currency] += add_amount
    user_balances[USERS[user_id]][subtract_currency] -= subtract_amount

    # Рассчитываем курс
    if add_amount > subtract_amount:
        exchange_rate = round(add_amount / subtract_amount, 2)
    else:
        exchange_rate = round(subtract_amount / add_amount, 2)
    save_transaction(user_id, "Обмен", add_currency, add_amount, subtract_currency, subtract_amount, exchange_rate)
    profit_value = profit_transaction_logic(add_currency, subtract_currency, user_id)
    query.edit_message_text(f"✅ Сделка подтверждена!\n\n```{get_balance_text(user_id)}```\n"
                           f"📉 Курс: {exchange_rate} {add_currency} за 1 {subtract_currency}\n"
                           f"{profit_value}", parse_mode='Markdown')
    


def add_money(update: Update, context: CallbackContext):
    """Пополняет баланс пользователя."""
    user_id = update.effective_user.id
    if check_user(user_id):
        try:
            # Получаем аргументы команды
            curs = ', '.join(list(cur_map.keys()))
            args = context.args
            if len(args) != 2:
                update.message.reply_text(f"❌ Используйте команду так: /add_money <валюта> <сумма>\nИспользуй <валюта>:\n{curs}.")
                return

            currency = cur_map.get(args[0], args[0])
            amount = int(args[1])

            # Проверяем, что валюта существует
            if currency not in CURRENCIES:
                
                update.message.reply_text(f"❌ Валюта '{currency}' не поддерживается\nИспользуй {curs}.")
                return

            # Получаем ID пользователя
            

            # Пополняем баланс
            # if user_id not in user_balances[USERS[user_id]]:
            #     user_balances[USERS[user_id]][user_id] = {cur: 0 for cur in CURRENCIES}
            
            user_balances[USERS[user_id]][currency] += amount
            save_transaction(user_id, "Пополнение", currency, amount)
            # Отправляем сообщение с обновленным балансом
            update.message.reply_text(f"✅ Баланс пополнен на {amount} {currency}.\n\n```{get_balance_text(user_id)}```", parse_mode='Markdown')
        except ValueError:
            update.message.reply_text("❌ Сумма должна быть числом.")
    else:
        update.message.reply_text("Привет! Мы не знакомы:(")




def substruct_money(update: Update, context: CallbackContext):
    """Пополняет баланс пользователя."""
    user_id = update.effective_user.id
    if check_user(user_id):
        try:
            # Получаем аргументы команды
            curs = ', '.join(list(cur_map.keys()))
            args = context.args
            if len(args) != 2:
                update.message.reply_text(f"❌ Используйте команду так: /sub_money <валюта> <сумма>\nИспользуй <валюта>:\n{curs}.")
                return

            currency = cur_map.get(args[0], args[0])
            amount = int(args[1])

            # Проверяем, что валюта существует
            if currency not in CURRENCIES:
                update.message.reply_text(f"❌ Валюта '{currency}' не поддерживается\nИспользуй {curs}.")
                return
            
            

            # Пополняем баланс
            # if user_id not in user_balances[USERS[user_id]]:
            #     user_balances[USERS[user_id]] = {cur: 0 for cur in CURRENCIES}

            balances = defaultdict(int)
            # print(user_balances[USERS[user_id]])
            for cur in list(user_balances[USERS[user_id]].keys()):
                balances[cur] += int(user_balances[USERS[user_id]][cur])

            if balances[currency] < amount:
                update.message.reply_text(f"❌ Баланс валюты '{currency}' = {balances[currency]} меньше изымаемой суммы {amount}")
                return
            user_balances[USERS[user_id]][currency] -= amount
            save_transaction(user_id, "Изъятие", currency, -amount)
            # Отправляем сообщение с обновленным балансом
            if update.message is not None:
                update.message.reply_text(f"✅ Баланс уменьшили на {amount} {currency}.\n\n```{get_balance_text(user_id)}```", parse_mode='Markdown')
        except ValueError:
            update.message.reply_text("❌ Сумма должна быть числом.")
    else:
        update.message.reply_text("Привет! Мы не знакомы:(")


def get_balance(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if check_user(user_id):
    # print(f"-----------{user_id}------------")
        update.message.reply_text(f"```{get_balance_text(user_id)}```", parse_mode='Markdown')
    else:
        update.message.reply_text("Привет! Мы не знакомы:(")



# Modified switch_file function:
def switch_file(update: Update, context: CallbackContext):
    """Handles file switching between Serg and Ivan"""
    if update.effective_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("❌ У вас нет прав для смены файла")
        return
        
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"file_{name}") 
         for name in FILE_OPTIONS.values()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user_id = update.effective_user.id
    # Show current file in message
    current_file = next(v for k,v in FILE_OPTIONS.items() if v ==FILE_OPTIONS[user_id] )
    update.message.reply_text(
        f"Текущий файл: {current_file}\nВыберите новый файл для работы:",
        reply_markup=reply_markup
    )

# Modified handle_file_selection function:
def handle_file_selection(update: Update, context: CallbackContext):
    """Handles file selection callback"""
    global FILE_OPTIONS
    query = update.callback_query
    query.answer()
    if query.from_user.id not in ALLOWED_USER_IDS:
        query.edit_message_text("❌ У вас нет прав для смены файла")
        return
    
    # file_name = query.from_user.id
    
    FILE_OPTIONS[update.effective_user.id] = query['data']
    file_name = FILE_OPTIONS[update.effective_user.id]
    # Reload data from new file
    load_balances()
    
    query.edit_message_text(
        f"✅ Файл изменен на: {file_name}\n"
        f"Балансы перезагружены из нового файла."
    )

def show_current_file(update: Update, context: CallbackContext):
    # global TRANSACTIONS_FILE
    # print(update['message']['chat']['id'])
    user_id = update['message']['chat']['id']
    # TRANSACTIONS_FILE = check_user_file(TRANSACTIONS_FILE, user_id)
    current = next(v for k,v in FILE_OPTIONS.items() if v == FILE_OPTIONS[user_id])
    update.message.reply_text(f"📂 Текущий активный файл: {current}")


def main():
    """Запускает бота."""
    load_balances()
    # Создаем Updater и передаем ему токен
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Existing handlers...
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("add_money", add_money))
    dispatcher.add_handler(CommandHandler("sub_money", substruct_money)) 
    dispatcher.add_handler(CommandHandler("balance", get_balance))
    dispatcher.add_handler(CommandHandler("profit", profit))
    dispatcher.add_handler(CommandHandler("switch_file", switch_file))  # Add this line
    dispatcher.add_handler(CommandHandler("current_file", show_current_file))
    # Existing callback handlers...
    dispatcher.add_handler(CallbackQueryHandler(handle_profit_selection, pattern="^profit_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_currency_selection, pattern="^add_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_subtract_currency, pattern="^subtract_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_file_selection, pattern="^file_"))  # Add this line
    
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_add_amount))
    dispatcher.add_handler(CallbackQueryHandler(confirm_transaction, pattern="^(confirm|cancel)$"))

    # Запускаем бота
    print("Бот запущен...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()