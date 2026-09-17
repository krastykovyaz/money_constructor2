import os
import threading
import requests
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

load_dotenv()
TOKEN = os.environ["ALL_EXCHANGE_BOT_TOKEN"]

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
    chrome_binary = os.environ.get("CHROME_BINARY", DEFAULT_CHROME_BINARY)
    if os.path.exists(chrome_binary):
        options.binary_location = chrome_binary
    chromedriver_binary = os.environ.get("CHROMEDRIVER_BINARY", DEFAULT_CHROMEDRIVER_BINARY)
    service = Service(executable_path=chromedriver_binary) if os.path.exists(chromedriver_binary) else None
    return webdriver.Chrome(service=service, options=options) if service else webdriver.Chrome(options=options)

def sed_message(MESSAGE):
    CHAT_IDS = [8159819525]
    for CHAT_ID in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": MESSAGE}
        requests.post(url, json=data)
        time.sleep(1)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})
last_message_lock = threading.Lock()
last_message = ""
user_data = {}
prev_val_dollar = None
prev_fintech_data = {}

BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"
pairs_binance = {"BTC/USD": "BTCUSDT", "ETH/USD": "ETHUSDT"}
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
    except:
        return None

def get_binance_p2p():
    try:
        response = session.get(BINANCE_API_URL, params={'symbol': 'USDTRUB'}, timeout=10)
        return round(float(response.json()['price']), 2) if response.ok else None
    except:
        return None

def get_currency_data_fintech():
    try:
        driver = get_driver()
        driver.get("https://fintech-exchange.ru/")
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

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
        return currency_cache
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")


def update_message():
    global last_message
    global prev_val_dollar
    global prev_fintech_data
    while True:
        try:
            fintech_data = get_currency_data_fintech()
            usd_rub = get_currency_cnbc("RUB=")
            eur_usd = get_currency_cnbc("EUR=")
            binance_p2p = get_binance_p2p()
            cbr = get_cbr_currency()

            message = "*📍 Online Курс:*\n"
            if usd_rub:
                message += f"• *USD/RUB*: `{usd_rub:.2f}`\n"
                if prev_val_dollar is not None and abs(prev_val_dollar - usd_rub) > 0.4:
                    sed_message(f"Скоро обновится курс в кассе !\nПредыдущая цена - {prev_val_dollar}\nТекущая цена - {usd_rub}")
                prev_val_dollar = usd_rub
            if usd_rub and eur_usd:
                message += f"• *EUR/RUB*: `{eur_usd * usd_rub:.2f}`\n"
            if eur_usd:
                message += f"• *EUR/USD*: `{eur_usd:.4f}`\n\n"

            if any(fintech_data["data"]):
                message += "*🏦 Наш Курс:* __(от 5000 y.e.)__\n"
            for item in fintech_data["data"]:
                cur_sale = float(item['sale'])
                cur_buy = float(item['purchase'])
                cur_item = item['currency']
                if prev_fintech_data != {} and \
                    cur_item in prev_fintech_data and \
                        abs(prev_fintech_data[cur_item] - cur_sale) > 0.2:
                    old_val = prev_fintech_data[cur_item]
                    sed_message(f"Обновился курс в кассе по {cur_item}:\nПредыдущая цена - {old_val}\nТекущая цена - {cur_sale}")
                prev_fintech_data[cur_item] = cur_sale
                
                buy = round(cur_buy - 0.3, 2)
                sell = round(cur_sale + 0.5, 2)
                message += f"• *{cur_item}*\n  Покупка: `{buy}` | Продажа: `{sell}`\n\n"
            
            if len(pairs_binance) > 0:
                message += "*🟢 Крипто Курс:*\n"
                for pair, symbol in pairs_binance.items():
                    try:
                        rate = float(session.get(BINANCE_API_URL, params={'symbol': symbol}, timeout=10).json()['price'])
                        message += f"• *{pair}*: `{rate}`\n"
                    except:
                        continue
                message += "\n"
            # if binance_p2p:
            #     message += f"• *USD/RUB P2P*: `{binance_p2p}`\n\n"
            if cbr:
                message += (
                    f"*🏛 Курс ЦБ РФ (на {cbr['date']}):*\n"
                    f"• USD/RUB: `{cbr['USD']:.2f}`\n"
                    f"• EUR/RUB: `{cbr['EUR']:.2f}`\n\n"
                )
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
    user_data[query.message.chat_id] = {"category": query.data}
    query.message.reply_text("Введите сумму:")

def handle_amount(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    amount = update.message.text
    if not re.match(r"^\d+(\.\d+)?$", amount):
        update.message.reply_text("Введите корректное число.")
        return
    elif float(amount) < 5000:
        update.message.reply_text("Обмен производится от 5000у.е.")
        return

    category = user_data.get(user_id, {}).get("category", "Неизвестная категория")
    print(update.message.from_user)
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
    print(message)
    context.bot.send_message(chat_id=8159819525, text=message)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("currency", currency))
    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_amount))

    threading.Thread(target=update_message, daemon=True).start()
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()






