import os
import threading
import requests
import time
import re
import pytz
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
)

from bot_utils import escape_markdown_legacy, parse_rate, AlertCooldown, ConversationState, updated_at_line
from scrapers import get_cbr_currency, get_currency_cnbc, scrape_fintech_rows, session

load_dotenv()
TOKEN = os.environ["ALL_EXCHANGE_BOT_TOKEN"]

def sed_message(MESSAGE):
    CHAT_IDS = [8159819525]
    for CHAT_ID in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": MESSAGE}
        try:
            requests.post(url, json=data, timeout=10)
        except requests.RequestException as e:
            print(f"[ERROR] Failed to notify chat {CHAT_ID}: {type(e).__name__}")
        time.sleep(1)

last_message_lock = threading.Lock()
last_message = ""
user_data = ConversationState()
prev_val_dollar = None
prev_fintech_data = {}

MAX_AMOUNT = 10_000_000

NO_ACTIVE_FLOW_HINT = "Чтобы сделать заказ, откройте /currency и нажмите «Сделать заказ»."

BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"
pairs_binance = {"BTC/USD": "BTCUSDT", "ETH/USD": "ETHUSDT"}
currency_cache = {
    "data": [],
    "updated_at": None
}

rate_alert_cooldown = AlertCooldown(cooldown_seconds=300)

def get_currency_data_fintech():
    try:
        currency_cache["data"] = scrape_fintech_rows()
        moscow_time = datetime.now(pytz.timezone("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')
        currency_cache["updated_at"] = moscow_time
        print(f"[INFO] Updated cache at {currency_cache['updated_at']}")
        return currency_cache
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        return currency_cache

def update_message():
    global last_message
    global prev_val_dollar
    global prev_fintech_data
    while True:
        try:
            fintech_data = get_currency_data_fintech()
            usd_rub = get_currency_cnbc("RUB=")
            eur_usd = get_currency_cnbc("EUR=")
            gbp_usd = get_currency_cnbc("GBP=")
            cbr = get_cbr_currency()

            message = "*📍 Online Курс:*\n"
            if usd_rub:
                message += f"• *USD/RUB*: `{usd_rub:.2f}`\n"
                if prev_val_dollar is not None and abs(prev_val_dollar - usd_rub) > 0.4 \
                        and rate_alert_cooldown.should_send("online_usd"):
                    sed_message(f"Скоро обновится курс в кассе !\nПредыдущая цена - {prev_val_dollar}\nТекущая цена - {usd_rub}")
                prev_val_dollar = usd_rub
            if usd_rub and eur_usd:
                message += f"• *EUR/RUB*: `{eur_usd * usd_rub:.2f}`\n"
            if eur_usd:
                message += f"• *EUR/USD*: `{eur_usd:.4f}`\n"
            if usd_rub and gbp_usd:
                message += f"• *GBP/RUB*: `{gbp_usd * usd_rub:.2f}`\n"
            if gbp_usd:
                message += f"• *GBP/USD*: `{gbp_usd:.4f}`\n"
            if eur_usd or gbp_usd:
                message += "\n"

            if any(fintech_data["data"]):
                message += "*🏦 Наш Курс:* __(от 5000 y.e.)__\n"
            for item in fintech_data["data"]:
                try:
                    cur_sale = parse_rate(item['sale'])
                    cur_buy = parse_rate(item['purchase'])
                except ValueError:
                    continue
                cur_item = item['currency']
                if prev_fintech_data != {} and \
                    cur_item in prev_fintech_data and \
                        abs(prev_fintech_data[cur_item] - cur_sale) > 0.2 and \
                        rate_alert_cooldown.should_send(f"fintech_{cur_item}"):
                    old_val = prev_fintech_data[cur_item]
                    sed_message(f"Обновился курс в кассе по {cur_item}:\nПредыдущая цена - {old_val}\nТекущая цена - {cur_sale}")
                prev_fintech_data[cur_item] = cur_sale

                buy = round(cur_buy - 0.3, 2)
                sell = round(cur_sale + 0.5, 2)
                message += f"• *{escape_markdown_legacy(cur_item)}*\n  Покупка: `{buy}` | Продажа: `{sell}`\n\n"

            if len(pairs_binance) > 0:
                message += "*🟢 Крипто Курс:*\n"
                for pair, symbol in pairs_binance.items():
                    try:
                        rate = float(session.get(BINANCE_API_URL, params={'symbol': symbol}, timeout=10).json()['price'])
                        message += f"• *{pair}*: `{rate}`\n"
                    except Exception:
                        continue
                message += "\n"
            if cbr:
                gbp_line = f"• GBP/RUB: `{cbr['GBP']:.2f}`\n" if cbr.get("GBP") else ""
                message += (
                    f"*🏛 Курс ЦБ РФ (на {escape_markdown_legacy(cbr['date'])}):*\n"
                    f"• USD/RUB: `{cbr['USD']:.2f}`\n"
                    f"• EUR/RUB: `{cbr['EUR']:.2f}`\n"
                    f"{gbp_line}\n"
                )
            message += updated_at_line()
            with last_message_lock:
                last_message = message
            print('Updated currency at', datetime.now())
        except Exception as e:
            print(f"Update error: {e}")

        time.sleep(60)

def currency(update: Update, context: CallbackContext):
    with last_message_lock:
        message = last_message
    if message:
        keyboard = [[InlineKeyboardButton("⭕️ Сделать заказ", callback_data="order_start")]]
        update.message.reply_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        update.message.reply_text("No data available yet.")

def order_start(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("💵 Синий доллар", callback_data="blue_choice")],
        [InlineKeyboardButton("💰 Зеленый доллар", callback_data="green_choice")],
        [InlineKeyboardButton("💶 Евро", callback_data="euro_choice")],
        [InlineKeyboardButton("🪙 Криптовалюта USDT", callback_data="crypto_choice")],
        [InlineKeyboardButton("💳 Оплата инвойсов", callback_data="invoice_choice")],
    ]
    query.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == "order_start":
        order_start(update, context)
    elif query.data.endswith("_choice"):
        ask_amount(update, context)

def ask_amount(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_data.set(query.message.chat_id, {"category": query.data})
    query.message.reply_text("Введите сумму:")

def handle_amount(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    amount = update.message.text
    state = user_data.get(user_id)
    if not state:
        update.message.reply_text(NO_ACTIVE_FLOW_HINT)
        return
    if not re.match(r"^\d+(\.\d+)?$", amount):
        update.message.reply_text("Введите корректное число.")
        return
    elif float(amount) < 5000:
        update.message.reply_text("Обмен производится от 5000у.е.")
        return
    elif float(amount) > MAX_AMOUNT:
        update.message.reply_text(f"Максимальная сумма — {MAX_AMOUNT:.0f}.")
        return

    user_data.pop(user_id)
    category = state.get("category", "Неизвестная категория")
    if update.message.from_user.username is not None:
        username = f"@{update.message.from_user.username}\n"
    else:
        username = 'username'
    message = (
        f"📌 Новый заказ от пользователя:\n"
        f"{update.message.from_user.first_name}\n"
        f"{update.message.from_user.id}\n"
        f"{username}\n"
        f"Категория: {category}\n"
        f"Сумма: {amount}"
    )
    if username == 'username':
        # update.message.reply_text("✅ У Вас не указан username напишите по заказу [оператору](https://t.me/oolyasya)",parse_mode="MarkdownV2")
        update.message.reply_text("✅ У Вас не указан username напишите по заказу оператору - @oolyasya")
    else:
        update.message.reply_text("✅ Заказ отправлен оператору - @oolyasya")
    print(f"[ORDER] category={category} amount={amount}")
    context.bot.send_message(chat_id=8159819525, text=message)

def on_error(update, context):
    print(f"[ERROR] Unhandled exception in handler: {context.error}")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("currency", currency))
    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_amount))
    dp.add_error_handler(on_error)

    threading.Thread(target=update_message, daemon=True).start()
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
