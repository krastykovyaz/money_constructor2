import asyncio
import websockets
import json

# Валютные пары на Binance (пример: USDT/RUB, EUR/USDT)
pairs = {
    "USD/RUB": "usdttry",  # USDT/RUB (через TRY)
    "USD/RUB": "tryrub",  # USDT/RUB (через TRY)
    "EUR/RUB": "eurusdt",  # EUR/USDT (можно пересчитать на RUB)
    "EUR/USD": "eurusdt"   # EUR/USD
}

# URL WebSocket Binance
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

async def get_currency_rates():
    # Формируем подписку на валютные пары
    streams = "/".join([f"{symbol}@trade" for symbol in pairs.values()])
    url = f"{BINANCE_WS_URL}/{streams}"

    async with websockets.connect(url) as websocket:
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            
            # Получаем цену
            symbol = data["s"]
            price = float(data["p"])
            
            # Выводим обновление курса
            print(f"Курс {symbol}: {price}")

# Запуск WebSocket клиента
if __name__ == '__main__':
    asyncio.run(get_currency_rates())