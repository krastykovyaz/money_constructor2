import os
import requests
import time
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv

load_dotenv()
CRYPTO_CURRENCY_BOT_TOKEN = os.environ["CRYPTO_CURRENCY_BOT_TOKEN"]

# Binance API URL
BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"

pairs_binance = {
    "BTC/USD": "BTCUSDT",
    "ETH/USD": "ETHUSDT"
}

# Store the latest message
last_message = ""

# Function to get the Binance rates
def get_binance_rates():
    global last_message
    message = "*🟢 Крипто Курс:*\n"
    
    for pair, symbol in pairs_binance.items():
        params = {'symbol': symbol}
        response = requests.get(BINANCE_API_URL, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            price = float(data['price'])
            message += f"• *{pair}*: `{price}`\n"
        else:
            message += f"• *{pair}*: `Error fetching data`\n"

    last_message = message  # Save the last message
    print(f"Updated Message: {last_message}")

# Function to run the script periodically
def run_periodically():
    while True:
        get_binance_rates()
        time.sleep(60)  # Wait for 1 minute before updating again

# Function to handle the /currency command in Telegram
def currency(update: Update, context: CallbackContext):
    global last_message
    if last_message:
        update.message.reply_text(last_message, parse_mode='Markdown')
    else:
        update.message.reply_text("No data available yet.")

# Start the Telegram bot
def main():
    updater = Updater(CRYPTO_CURRENCY_BOT_TOKEN, use_context=True)
    updater.dispatcher.add_handler(CommandHandler("currency", currency))
    updater.start_polling()
    updater.idle()

# Start the periodic updates in the background
if __name__ == '__main__':
    import threading
    # Start the periodic update in a separate thread
    update_thread = threading.Thread(target=run_periodically)
    update_thread.daemon = True  # Run in background
    update_thread.start()
    
    # Start the Telegram bot
    main()
