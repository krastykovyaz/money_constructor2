import threading
import math
import os
import requests
import shutil
import tempfile
import time
import re
import pytz
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
)

from bot_utils import escape_markdown_legacy, parse_rate, AlertCooldown

# Selenium setup
DEFAULT_CHROME_BINARY = "/opt/chrome-for-testing/chrome-linux64/chrome"
DEFAULT_CHROMEDRIVER_BINARY = "/opt/chrome-for-testing/chromedriver-linux64/chromedriver"

def get_driver():
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-features=site-per-process")
    options.add_argument("--renderer-process-limit=1")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--js-flags=--max-old-space-size=128")
    user_data_dir = tempfile.mkdtemp(prefix='exchange-chrome-')
    options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_binary = os.environ.get("CHROME_BINARY", DEFAULT_CHROME_BINARY)
    if not os.path.exists(chrome_binary):
        shutil.rmtree(user_data_dir, ignore_errors=True)
        raise RuntimeError(
            f"Chrome binary not found at {chrome_binary}. Install it or set CHROME_BINARY."
        )
    options.binary_location = chrome_binary
    chromedriver_binary = os.environ.get("CHROMEDRIVER_BINARY", DEFAULT_CHROMEDRIVER_BINARY)
    service = Service(executable_path=chromedriver_binary) if os.path.exists(chromedriver_binary) else None
    try:
        driver = webdriver.Chrome(service=service, options=options) if service else webdriver.Chrome(options=options)
    except Exception:
        shutil.rmtree(user_data_dir, ignore_errors=True)
        raise
    driver.set_page_load_timeout(20)
    driver.exchange_user_data_dir = user_data_dir
    return driver

def sed_message(MESSAGE):
    for CHAT_ID in (OPERATOR_CHAT_ID,):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": MESSAGE}
        try:
            requests.post(url, json=data, timeout=10)
        except requests.RequestException as e:
            print(f"[ERROR] Failed to notify chat {CHAT_ID}: {type(e).__name__}")
        time.sleep(1)

load_dotenv()
BOT_TOKEN = os.environ["EXCHANGE_DESK_BOT_TOKEN"]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})
last_message_lock = threading.Lock()
last_message = ""
user_data = {}
current_order_rates = {"dollar": None, "euro": None, "usdt": None}
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
OPERATOR_CHAT_ID = int(os.environ.get("OPERATOR_CHAT_ID", "8773698197"))
OPERATOR_CONTACT = "@niccolomachiavelli1469"
currency_cache = {
    "data": [],
    "updated_at": None
}

def get_cbr_currency():
    try:
        response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=10)
        if response.ok:
            soup = BeautifulSoup(response.content, "lxml-xml")
            date = soup.find('ValCurs')['Date']
            usd = soup.find('Valute', ID="R01235")
            eur = soup.find('Valute', ID="R01239")
            usd_value = float(usd.Value.text.replace(',', '.'))
            eur_value = float(eur.Value.text.replace(',', '.'))
            return {
                "date": date,
                "USD": usd_value,
                "EUR": eur_value
            }
    except Exception as e:
        print(f"Error fetching CBR data: {e}")
    return None

def get_currency_cnbc(symbol):
    try:
        response = session.get(f"https://www.cnbc.com/quotes/{symbol}", timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        price_element = soup.find("span", class_="QuoteStrip-lastPrice")
        return float(price_element.text.strip()) if price_element else None
    except Exception:
        return None

def get_binance_p2p():
    try:
        response = session.get(BINANCE_API_URL, params={'symbol': 'USDTRUB'}, timeout=10)
        return round(float(response.json()['price']), 2) if response.ok else None
    except Exception:
        return None

def get_currency_data_fintech():
    global fintech_fail_streak
    driver = None
    try:
        driver = get_driver()
        driver.get("https://fintech-exchange.ru/")
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        table = soup.find("table")
        rows = table.find_all("tr")[1:] if table else []
        parsed = []
        curs = set()
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 4:
                cur = cols[0].text.strip()
                if cur not in curs:
                    parsed.append({
                        "currency": cur,
                        "purchase": cols[1].text.strip(),
                        "sale": cols[2].text.strip(),
                        "volume": cols[3].text.strip()
                    })
                curs.add(cur)


        currency_cache["data"] = parsed
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
    finally:
        if driver is not None:
            user_data_dir = getattr(driver, "exchange_user_data_dir", None)
            try:
                driver.quit()
            except Exception:
                pass
            if user_data_dir:
                shutil.rmtree(user_data_dir, ignore_errors=True)

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
        return parsed
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
    global prev_val_dollar
    global prev_fintech_data
    while True:
        try:
            check_disk_space()
            fintech_data = get_currency_data_fintech() or {"data": [], "updated_at": None}
            ligovka_data = get_currency_data_ligovka() or []
            usd_rub = get_currency_cnbc("RUB=")
            eur_usd = get_currency_cnbc("EUR=")
            binance_p2p = get_binance_p2p()
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
                message += f"• *EUR/USD*: `{eur_usd:.4f}`\n\n"

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
                if cur_item == 'USD синий':
                    our_rates['dollar'] = {'buy': buy, 'sell': sell}
                elif cur_item == 'EUR':
                    our_rates['euro'] = {'buy': buy, 'sell': sell}

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
                    usdt_rates['eur'] = {'buy': eur_usdt_buy, 'sell': eur_usdt_sell}
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
            # if binance_p2p:
            #     message += f"• *USD/RUB P2P*: `{binance_p2p}`\n\n"
            if cbr:
                message += (
                    f"*🏛 Курс ЦБ РФ (на {escape_markdown_legacy(cbr['date'])}):*\n"
                    f"• USD/RUB: `{cbr['USD']:.2f}`\n"
                    f"• EUR/RUB: `{cbr['EUR']:.2f}`\n\n"
                )
            with last_message_lock:
                last_message = message
                current_order_rates = {
                    'dollar': our_rates.get('dollar'),
                    'euro': our_rates.get('euro'),
                    'usdt': usdt_rates.get('usd'),
                }
            print('Updated currency at', datetime.now())
        except Exception as e:
            print(f"Update error: {e}")

        time.sleep(60)

MAX_AMOUNT = 10_000_000

CALC_CURRENCY_LABELS = {"rub": "RUB", "usd": "USD", "eur": "EUR", "usdt": "USDT"}
CALC_RATE_KEYS = {"usd": "dollar", "eur": "euro", "usdt": "usdt"}

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
    for currency in ("rub", "usd", "eur", "usdt"):
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
    ]
    query.message.reply_text("Из какой валюты считаем?", reply_markup=InlineKeyboardMarkup(keyboard))

def calc_pick_currency(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    currency = query.data.split("_", 1)[1]
    user_data[query.message.chat_id] = {"mode": "calc", "currency": currency}
    query.message.reply_text(f"Введите сумму в {CALC_CURRENCY_LABELS[currency]}:")

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.data == "order_start":
        order_start(update, context)
    elif query.data == "calc_open":
        calc_start(update, context)
    elif query.data in ("calc_rub", "calc_usd", "calc_eur", "calc_usdt"):
        calc_pick_currency(update, context)
    elif query.data.endswith("_choice"):
        ask_amount(update, context)

def ask_amount(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_data[query.message.chat_id] = {"category": query.data}
    query.message.reply_text("Введите сумму:")

def handle_amount(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    amount = update.message.text
    if not re.match(r"^\d+(\.\d+)?$", amount):
        update.message.reply_text("Введите корректное число.")
        return
    amount_value = float(amount)
    if not (0 < amount_value <= MAX_AMOUNT):
        update.message.reply_text(f"Введите сумму от 0 до {MAX_AMOUNT:.0f}.")
        return

    state = user_data.pop(user_id, {})
    if state.get("mode") == "calc":
        with last_message_lock:
            rates = dict(current_order_rates)
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
    print(message)
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
