import os
from telegram.ext import Updater, CommandHandler
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import re

load_dotenv()
TELEGRAM_TOKEN = os.environ["LIGOVKA_BOT_TOKEN"]
LIGOVKA_URL = "https://ligovka.ru/"

def escape_md(text: str) -> str:
    return re.sub(r'([_\*\[\]\(\)~`>\#\+\-=|{}.!\\])', r'\\\1', text)

def fetch_ligovka_rates() -> str:
    try:
        response = httpx.get(LIGOVKA_URL, timeout=15.0)
        response.raise_for_status()
    except httpx.RequestError as e:
        return f"⚠️ Ошибка при подключении: {escape_md(str(e))}"

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.find_all("tr")

    results = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) == 10:
            amount = cols[0].text.strip()
            usd_buy = cols[2].text.strip()
            usd_sell = cols[3].text.strip()
            eur_buy = cols[5].text.strip()
            eur_sell = cols[6].text.strip()
            eurusd_buy = cols[8].text.strip()
            eurusd_sell = cols[9].text.strip()

            block = (
                f"💵 От {amount}:\n"
                f"  USD: 🔻 {usd_buy} / 🔺 {usd_sell}\n"
                f"  EUR: 🔻 {eur_buy} / 🔺 {eur_sell}\n"
                f"  EUR/USD: 🔻 {eurusd_buy} / 🔺 {eurusd_sell}\n"
            )
            results.append(block)

    if not results:
        return "Не удалось найти курсы валют на сайте."

    header = "💱 Курсы валют на ligovka.ru\n"
    return escape_md(header) + "\n".join(map(escape_md, results))

def start(update, context):
    update.message.reply_text("Привет! Отправь /rates, чтобы получить курсы валют из Центра обмена СКВ 'Лиговский', 'Скобелевский', 'Благодатный'")

def rates(update, context):
    message = fetch_ligovka_rates()
    update.message.reply_text(message, parse_mode='MarkdownV2', disable_web_page_preview=True)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("rates", rates))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()