import os
import shutil
import tempfile
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.remote_connection import RemoteConnection

from bot_utils import cbr_valute_rate, parse_rate, try_parse_rate

DEFAULT_CHROME_BINARY = "/opt/chrome-for-testing/chrome-linux64/chrome"
DEFAULT_CHROMEDRIVER_BINARY = "/opt/chrome-for-testing/chromedriver-linux64/chromedriver"
FINTECH_URL = "https://fintech-exchange.ru/"
SELENIUM_COMMAND_TIMEOUT = 60

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def get_driver():
    # Selenium's default is no timeout: a wedged chromedriver would block the update thread forever.
    RemoteConnection.set_timeout(SELENIUM_COMMAND_TIMEOUT)
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


def scrape_fintech_rows():
    """Rows from fintech-exchange.ru with parseable rates; always cleans up Chrome and its profile dir."""
    driver = None
    try:
        driver = get_driver()
        driver.get(FINTECH_URL)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table")
        rows = table.find_all("tr")[1:] if table else []
        parsed = []
        seen = set()
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            cur = cols[0].text.strip()
            if cur in seen:
                continue
            seen.add(cur)
            purchase, sale = cols[1].text.strip(), cols[2].text.strip()
            if try_parse_rate(purchase) is None or try_parse_rate(sale) is None:
                print(f"[WARN] Skipping fintech row {cur!r}: unparseable rate")
                continue
            parsed.append({"currency": cur, "purchase": purchase, "sale": sale, "volume": cols[3].text.strip()})
        return parsed
    finally:
        if driver is not None:
            user_data_dir = getattr(driver, "exchange_user_data_dir", None)
            try:
                driver.quit()
            except Exception:
                pass
            if user_data_dir:
                shutil.rmtree(user_data_dir, ignore_errors=True)


def get_cbr_currency():
    try:
        response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=10)
        if response.ok:
            soup = BeautifulSoup(response.content, "lxml-xml")
            date = soup.find('ValCurs')['Date']
            usd = soup.find('Valute', ID="R01235")
            eur = soup.find('Valute', ID="R01239")
            return {
                "date": date,
                "USD": parse_rate(usd.Value.text),
                "EUR": parse_rate(eur.Value.text),
                "GBP": cbr_valute_rate(soup, "R01035"),
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
