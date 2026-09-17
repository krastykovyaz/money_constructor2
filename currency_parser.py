

import os
import time
import threading
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime
from dotenv import load_dotenv
import pytz

load_dotenv()
CURRENCY_PARSER_BOT_TOKEN = os.environ["CURRENCY_PARSER_BOT_TOKEN"]

# === GLOBAL CACHE ===
currency_cache = {
    "data": [],
    "updated_at": None
}

# Selenium setup
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

# Parsing function
def fetch_currency_data():
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
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")

# Background loop to update every 60s
def update_loop():
    while True:
        fetch_currency_data()
        time.sleep(60)

# Telegram command
def currency(update: Update, context: CallbackContext):
    data = currency_cache["data"]
    if not data:
        update.message.reply_text("Нет актуальных данных. Подождите минуту.")
        return
    cur_date = currency_cache['updated_at']
    message = f"*Курсы валют - обновлено {cur_date}:*\n__(от 5000 y.e.)__\n"
    for item in data:
        message += f"\n• *{item['currency']}*\n"
        message += f"  Покупка: `{item['purchase']}` | Продажа: `{item['sale']}`"

    update.message.reply_text(message, parse_mode='Markdown')

# if __name__=='__main__':
#     fetch_currency_data()

# Start Telegram bot
def main():
    threading.Thread(target=update_loop, daemon=True).start()

    updater = Updater(CURRENCY_PARSER_BOT_TOKEN, use_context=True)
    updater.dispatcher.add_handler(CommandHandler("currency", currency))
    updater.dispatcher.add_handler(CommandHandler("start", currency))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()