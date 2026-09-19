import requests
from bs4 import BeautifulSoup

def get_usd_rub_cnbc():
    url = "https://www.cnbc.com/quotes/RUB="
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ищем нужный <span> с курсом
        price_element = soup.find("span", class_="QuoteStrip-lastPrice")
        if price_element:
            return float(price_element.text.strip())
    
    return None

if __name__ == '__main__':
    rate = get_usd_rub_cnbc()
    print(f"Курс USD/RUB (CNBC): {rate}")