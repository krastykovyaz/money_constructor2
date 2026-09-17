import yfinance as yf
import time
from datetime import datetime

# Символы валютных пар
pairs = {
    "USD/RUB": "USDRUB=X",
    "EUR/RUB": "EURRUB=X",
    "EUR/USD": "EURUSD=X"
}

# Получение текущих курсов
def get_currency_rates():
    rates = {}
    for pair, symbol in pairs.items():
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            # print(data.reset_index()['Date'].tolist()[0])
            rates[pair] = str(data["Close"].iloc[-1].round(2))  # Берем последний доступный курс
        else:
            rates[pair] = None
    return rates

# Вывод данных каждую секунду
try:
    while True:
        rates = get_currency_rates()
        print(rates, f"{datetime.now().hour}:{datetime.now().minute}")
        time.sleep(1)  # Задержка 1 секунда
except KeyboardInterrupt:
    print("Программа завершена.")