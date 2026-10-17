import threading
import math
import os
import requests
import shutil
import time
import re
import pytz
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
)

from bot_utils import (
    escape_markdown_legacy, parse_rate, try_parse_rate, AlertCooldown, ConversationState,
    telegram_send, updated_at_line, validate_operator_chat_id,
)
from scrapers import get_cbr_currency, get_currency_cnbc, scrape_fintech_rows, session

def sed_message(MESSAGE):
    for CHAT_ID in (OPERATOR_CHAT_ID,):
        ok, error = telegram_send(BOT_TOKEN, CHAT_ID, MESSAGE)
        if not ok:
            print(f"[ERROR] Failed to notify chat {CHAT_ID}: {error}")
        time.sleep(1)

load_dotenv()
BOT_TOKEN = os.environ["EXCHANGE_DESK_BOT_TOKEN"]

last_message_lock = threading.Lock()
last_message = ""
user_data = ConversationState()
current_order_rates = {"dollar": None, "euro": None, "usdt": None}
current_calc_rates = {"dollar": None, "euro": None, "usdt": None, "gbp": None}
prev_val_dollar = None
prev_fintech_data = {}

DISK_FREE_THRESHOLD_BYTES = 2 * 1024 ** 3  # 2 GiB
disk_alert_sent = False

FINTECH_FAIL_ALERT_THRESHOLD = 3
fintech_fail_streak = 0

rate_alert_cooldown = AlertCooldown(cooldown_seconds=300)

def check_disk_space():
    global disk_alert_sent
    try:
        free_bytes = shutil.disk_usage("/").free
    except Exception:
        return
    free_gb = free_bytes / 1024 ** 3
    if free_bytes < DISK_FREE_THRESHOLD_BYTES:
        if not disk_alert_sent:
            sed_message(f"⚠️ Мало места на диске: осталось {free_gb:.1f} GB.")
            disk_alert_sent = True
    elif disk_alert_sent:
        sed_message(f"✅ Место на диске восстановлено: {free_gb:.1f} GB свободно.")
        disk_alert_sent = False

BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"
pairs_binance = {"BTC/USD": "BTCUSDT", "ETH/USD": "ETHUSDT"}
LIGOVKA_URL = "https://ligovka.ru/"
OPERATOR_CHAT_ID = os.environ.get("OPERATOR_CHAT_ID")
OPERATOR_CONTACT = "@niccolomachiavelli1469"
currency_cache = {
    "data": [],
    "updated_at": None
}

def get_currency_data_fintech():
    global fintech_fail_streak
    try:
        currency_cache["data"] = scrape_fintech_rows()
        moscow_time = datetime.now(pytz.timezone("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')
        currency_cache["updated_at"] = moscow_time
        print(f"[INFO] Updated cache at {currency_cache['updated_at']}")
        if fintech_fail_streak >= FINTECH_FAIL_ALERT_THRESHOLD:
            sed_message(f"✅ fintech-exchange.ru снова отдаёт курс после {fintech_fail_streak} неудачных попыток подряд.")
        fintech_fail_streak = 0
        return currency_cache
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        fintech_fail_streak += 1
        if fintech_fail_streak == FINTECH_FAIL_ALERT_THRESHOLD:
            sed_message(f"⚠️ Не удаётся получить курс с fintech-exchange.ru уже {fintech_fail_streak} раза подряд: {e}")
        return currency_cache

def get_currency_data_ligovka():
    try:
        response = session.get(LIGOVKA_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        parsed = []
        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) != 10:
                continue
            amount = cols[0].text.strip()
            parsed.extend([
                {"currency": f"USD ({amount})", "purchase": cols[2].text.strip(), "sale": cols[3].text.strip()},
                {"currency": f"EUR ({amount})", "purchase": cols[5].text.strip(), "sale": cols[6].text.strip()},
                {"currency": f"EUR/USD ({amount})", "purchase": cols[8].text.strip(), "sale": cols[9].text.strip()},
            ])
        return [
            item for item in parsed
            if try_parse_rate(item["purchase"]) is not None and try_parse_rate(item["sale"]) is not None
        ]
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch Ligovka data: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to parse Ligovka data: {e}")
        return []

def round_buy_price(value):
    whole = int(value)
    fraction = round(value - whole, 10)
    if 0.10 <= fraction <= 0.69:
        return whole + 0.5
    return float(round(value))

def round_sell_price(value):
    return math.floor(value * 2 + 0.5) / 2

GBP_MARKUP = 1.06

def gbp_calculator_rate(gbp_usd, eur_usd, ligovka_eur_sale):
    if not gbp_usd or not eur_usd or not ligovka_eur_sale:
        return None
    gbp_in_eur = gbp_usd / eur_usd
    return {
        'buy': gbp_in_eur * ligovka_eur_sale,
        'sell': gbp_in_eur * ligovka_eur_sale * GBP_MARKUP,
    }

def choose_exchange_rates(fintech_data, ligovka_data):
    ligovka_by_currency = {}
    for item in ligovka_data:
        if '(от 1)' not in item['currency']:
            continue
        currency = item['currency'].split(' (', 1)[0]
        ligovka_by_currency[currency] = item

    chosen = []
    for item in fintech_data:
        currency = item['currency']
        base_currency = 'EUR' if currency.startswith('EUR') else 'USD'
        ligovka_item = ligovka_by_currency.get(base_currency)
        if ligovka_item is None:
            chosen.append(dict(item))
            continue

        fintech_buy = parse_rate(item['purchase'])
        fintech_sell = parse_rate(item['sale'])
        ligovka_buy = parse_rate(ligovka_item['purchase'])
        ligovka_sell = parse_rate(ligovka_item['sale'])
        selected_sell = (
            max(fintech_sell, ligovka_sell)
            if currency == 'USD' or currency.startswith('EUR')
            else min(fintech_sell, ligovka_sell)
        )
        selected_buy = (
            min(fintech_buy, ligovka_buy)
            if currency.startswith('USD') or currency.startswith('EUR')
            else max(fintech_buy, ligovka_buy)
        )
        chosen.append({
            'currency': currency,
            'purchase': selected_buy,
            'sale': selected_sell,
        })
    return chosen


def update_message():
    global last_message
    global current_order_rates
    global current_calc_rates
    global prev_val_dollar
    global prev_fintech_data
    while True:
        try:
            check_disk_space()
            fintech_data = get_currency_data_fintech() or {"data": [], "updated_at": None}
            ligovka_data = get_currency_data_ligovka() or []
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

            selected_rates = choose_exchange_rates(fintech_data["data"], ligovka_data)
            selected_rates = [
                item for item in selected_rates
                if item['currency'] not in {'EUR 500', 'USD белый'}
            ]
            online_eur_rub = eur_usd * usd_rub if usd_rub and eur_usd else None
            for item in selected_rates:
                if item['currency'].startswith('USD') and usd_rub:
                    item['purchase'] = usd_rub
                elif item['currency'].startswith('EUR') and online_eur_rub:
                    item['purchase'] = online_eur_rub
            if selected_rates:
                message += "*🏦 Текущий курс:* __на счет EU/US__\n"
            our_rates = {}
            exact_rates = {}
            for item in selected_rates:
                cur_sale = parse_rate(str(item['sale']))
                cur_buy = parse_rate(str(item['purchase']))
                cur_item = item['currency']
                if prev_fintech_data != {} and \
                    cur_item in prev_fintech_data and \
                        abs(prev_fintech_data[cur_item] - cur_sale) > 0.2 and \
                        rate_alert_cooldown.should_send(f"fintech_{cur_item}"):
                    old_val = prev_fintech_data[cur_item]
                    sed_message(f"Обновился курс в кассе по {cur_item}:\nПредыдущая цена - {old_val}\nТекущая цена - {cur_sale}")
                prev_fintech_data[cur_item] = cur_sale
                
                buy = round_buy_price(cur_buy)
                sell = cur_sale * 1.06 if cur_item.startswith(('USD', 'EUR')) else cur_sale
                if cur_item.startswith(('USD', 'EUR')):
                    sell = round_sell_price(sell)
                display_label = {'USD синий': 'USD/RUB', 'EUR': 'EUR/RUB'}.get(cur_item, cur_item)
                message += f"• *{escape_markdown_legacy(display_label)}*\n  Покупка: `{buy:.2f}` | Продажа: `{sell:.2f}`\n\n"
                exact_sell = cur_sale * 1.06 if cur_item.startswith(('USD', 'EUR')) else cur_sale
                if cur_item == 'USD синий':
                    our_rates['dollar'] = {'buy': buy, 'sell': sell}
                    exact_rates['dollar'] = {'buy': cur_buy, 'sell': exact_sell}
                elif cur_item == 'EUR':
                    our_rates['euro'] = {'buy': buy, 'sell': sell}
                    exact_rates['euro'] = {'buy': cur_buy, 'sell': exact_sell}

            usd_ligovka = next((item for item in ligovka_data if item['currency'] == 'USD (от 1)'), None)
            eur_usd_ligovka = next((item for item in ligovka_data if item['currency'] == 'EUR/USD (от 1)'), None)
            usdt_rates = {}
            message += "*USDT Курс:*\n"
            if usd_ligovka or eur_usd_ligovka:
                if usd_ligovka:
                    online_buy = usd_rub if usd_rub else parse_rate(usd_ligovka['purchase'])
                    usdt_sell = parse_rate(usd_ligovka['sale']) + 0.5
                    usdt_rates['usd'] = {'buy': parse_rate(str(online_buy)), 'sell': usdt_sell}
                    message += (
                        f"• *USDT/RUB*\n"
                        f"  Покупка: `{online_buy:.2f}` | Продажа: `{usdt_sell:.2f}`\n\n"
                    )
                if eur_usd_ligovka:
                    eur_usdt_buy = parse_rate(eur_usd_ligovka['purchase'])
                    eur_usdt_sell = parse_rate(eur_usd_ligovka['sale'])
                    message += (
                        f"• *EUR/USDT*\n"
                        f"  Покупка: `{eur_usdt_buy:.4f}` | Продажа: `{eur_usdt_sell:.4f}`\n\n"
                    )
            else:
                message += "• Данные Ligovka пока недоступны.\n\n"
            
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
            eur_ligovka = next((item for item in ligovka_data if item['currency'] == 'EUR (от 1)'), None)
            gbp_rate = gbp_calculator_rate(
                gbp_usd, eur_usd, parse_rate(eur_ligovka['sale']) if eur_ligovka else None
            )
            with last_message_lock:
                last_message = message
                current_order_rates = {
                    'dollar': our_rates.get('dollar'),
                    'euro': our_rates.get('euro'),
                    'usdt': usdt_rates.get('usd'),
                }
                current_calc_rates = {
                    'dollar': exact_rates.get('dollar'),
                    'euro': exact_rates.get('euro'),
                    'usdt': usdt_rates.get('usd'),
                    'gbp': gbp_rate,
                }
            print('Updated currency at', datetime.now())
        except Exception as e:
            print(f"Update error: {e}")

        time.sleep(60)

MAX_AMOUNT = 10_000_000

NO_ACTIVE_FLOW_HINT = "Чтобы сделать заказ или посчитать в калькуляторе, откройте /currency и нажмите нужную кнопку."

CALC_CURRENCY_LABELS = {"rub": "RUB", "usd": "USD", "eur": "EUR", "usdt": "USDT", "gbp": "GBP"}
CALC_RATE_KEYS = {"usd": "dollar", "eur": "euro", "usdt": "usdt", "gbp": "gbp"}

def convert_currency(amount, from_currency, rates):
    def rate_for(currency):
        return rates.get(CALC_RATE_KEYS[currency])

    if from_currency == "rub":
        rub_amount = amount
    else:
        rate = rate_for(from_currency)
        if not rate or not rate.get("sell"):
            return None
        rub_amount = amount * rate["sell"]

    results = {"rub": rub_amount}
    for currency in CALC_RATE_KEYS:
        if currency == from_currency:
            continue
        rate = rate_for(currency)
        results[currency] = rub_amount / rate["sell"] if rate and rate.get("sell") else None
    return results

def format_calc_reply(amount, from_currency, results):
    lines = [f"💱 {amount:.2f} {CALC_CURRENCY_LABELS[from_currency]} =\n"]
    missing = []
    for currency in ("rub", "usd", "eur", "usdt", "gbp"):
        if currency == from_currency:
            continue
        value = results.get(currency)
        if value is None:
            missing.append(CALC_CURRENCY_LABELS[currency])
            continue
        lines.append(f"• {value:.2f} {CALC_CURRENCY_LABELS[currency]}")
    if missing:
        lines.append(f"\n(Курс {', '.join(missing)} пока недоступен)")
    return "\n".join(lines)

def currency(update: Update, context: CallbackContext):
    with last_message_lock:
        message = last_message
    if message:
        keyboard = [
            [InlineKeyboardButton("⭕️ Сделать заказ", callback_data="order_start")],
            [InlineKeyboardButton("🧮 Калькулятор", callback_data="calc_open")],
        ]
        update.message.reply_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        update.message.reply_text("No data available yet.")

def order_start(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("💵 Доллар", callback_data="dollar_choice")],
        [InlineKeyboardButton("💶 Евро", callback_data="euro_choice")],
        [InlineKeyboardButton("🪙 USDT", callback_data="usdt_choice")],
        [InlineKeyboardButton("💳 Оплата инвойса", callback_data="invoice_choice")],
        [InlineKeyboardButton("🔄 Операции с криптовалютой", callback_data="crypto_operations_choice")],
    ]
    query.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))

def calc_start(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("₽ RUB", callback_data="calc_rub")],
        [InlineKeyboardButton("💵 USD", callback_data="calc_usd")],
        [InlineKeyboardButton("💶 EUR", callback_data="calc_eur")],
        [InlineKeyboardButton("🪙 USDT", callback_data="calc_usdt")],
        [InlineKeyboardButton("💷 GBP", callback_data="calc_gbp")],
    ]
    query.message.reply_text("Из какой валюты считаем?", reply_markup=InlineKeyboardMarkup(keyboard))

def calc_pick_currency(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    currency = query.data.split("_", 1)[1]
    user_data.set(query.message.chat_id, {"mode": "calc", "currency": currency})
    query.message.reply_text(f"Введите сумму в {CALC_CURRENCY_LABELS[currency]}:")

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == "order_start":
        order_start(update, context)
    elif query.data == "calc_open":
        calc_start(update, context)
    elif query.data in ("calc_rub", "calc_usd", "calc_eur", "calc_usdt", "calc_gbp"):
        calc_pick_currency(update, context)
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
    amount_value = float(amount)
    if not (0 < amount_value <= MAX_AMOUNT):
        update.message.reply_text(f"Введите сумму от 0 до {MAX_AMOUNT:.0f}.")
        return

    user_data.pop(user_id)
    if state.get("mode") == "calc":
        with last_message_lock:
            rates = dict(current_calc_rates)
        results = convert_currency(amount_value, state["currency"], rates)
        if results is None:
            update.message.reply_text("Курс пока обновляется, попробуйте чуть позже.")
        else:
            update.message.reply_text(format_calc_reply(amount_value, state["currency"], results))
        return

    category = state.get("category", "Неизвестная категория")
    rate_key = {
        'dollar_choice': 'dollar',
        'euro_choice': 'euro',
        'usdt_choice': 'usdt',
    }.get(category)
    with last_message_lock:
        rates = current_order_rates.get(rate_key) if rate_key else None

    calculation = ""
    if rates:
        buy_total = amount_value * rates['buy']
        sell_total = amount_value * rates['sell']
        calculation = (
            f"\nОценка по курсу:\n"
            f"Покупка: {rates['buy']:.2f} × {amount_value:.2f} = {buy_total:.2f}\n"
            f"Продажа: {rates['sell']:.2f} × {amount_value:.2f} = {sell_total:.2f}\n"
        )
    elif rate_key:
        calculation = "\nКурс пока обновляется. Оператор уточнит расчет.\n"

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
        f"{calculation}"
    )
    print(f"[ORDER] category={category} amount={amount}")
    try:
        context.bot.send_message(chat_id=OPERATOR_CHAT_ID, text=message)
        delivery_status = f"✅ Заказ отправлен оператору - {OPERATOR_CONTACT}"
    except Exception as e:
        print(f"Operator notification error: {e}")
        delivery_status = (
            "⚠️ Расчет готов, но не удалось отправить заказ оператору.\n"
            f"Напишите, пожалуйста, напрямую оператору - {OPERATOR_CONTACT}"
        )
    update.message.reply_text(f"{calculation}\n{delivery_status}")

def on_error(update, context):
    print(f"[ERROR] Unhandled exception in handler: {context.error}")

def main():
    global OPERATOR_CHAT_ID
    OPERATOR_CHAT_ID = validate_operator_chat_id(OPERATOR_CHAT_ID, BOT_TOKEN)
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", currency))
    dp.add_handler(CommandHandler("currency", currency))
    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_amount))
    dp.add_error_handler(on_error)

    threading.Thread(target=update_message, daemon=True).start()
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
