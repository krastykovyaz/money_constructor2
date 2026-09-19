import requests

def get_binance_p2p():
    url = "https://api.binance.com/api/v3/ticker/price"
    
    # Getting the P2P market price for USD/RUB
    params = {
        'symbol': 'USDTRUB',
    }

    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    if response.status_code == 200:
        return round(float(data['price']), 2)
    else:
        return None

if __name__ == '__main__':
    print(get_binance_p2p())
