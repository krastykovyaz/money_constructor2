import requests

def get_usd_rub_moex():
    url = "https://iss.moex.com/iss/engines/currency/markets/selt/securities.json?securities=USD000UTSTOM"
    
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        try:
            # Данные о последней цене находятся в первом элементе списка "marketdata"
            last_price = data["marketdata"]["data"][0][8]
            return float(last_price)
        except (IndexError, KeyError, TypeError):
            return None
    return None

if __name__ == '__main__':
    rate = get_usd_rub_moex()
    print(f"Текущий курс USD/RUB (MOEX): {rate}")