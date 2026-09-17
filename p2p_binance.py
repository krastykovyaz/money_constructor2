import requests

def get_binance_p2p():
    url = "https://api.binance.com/api/v3/ticker/price"
    
    # Getting the P2P market price for USD/RUB
    params = {
        'symbol': 'USDTRUB',
    }

    response = requests.get(url, params=params)
    data = response.json()

    if response.status_code == 200:
        return round(float(data['price']), 2)
    else:
        return None

print(get_binance_p2p())
