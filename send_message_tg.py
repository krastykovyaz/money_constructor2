import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
URL_SEND_MESSAGE = "https://api.telegram.org/bot{}/sendMessage"
TELEGRAM_TOKEN = os.environ["FINANCIAL_AGENT_BOT_TOKEN"]  # @financialagent_bot

def send_message(chat_id: int,
                 text: str,
                 parse_mode: str = None,
                 buttons: list or None = None,
                 inline_keyboard: list or None = None,
                 one_time_keyboard: bool = True,
                 resize_keyboard: bool = True,
                 remove_keyboard: bool = False,):
    payload = {
        "chat_id": chat_id,
        "text": text[:4095],
        "reply_markup": {
            "remove_keyboard": remove_keyboard
        }
    }

    if parse_mode:
        payload.update({"parse_mode": parse_mode})

    if buttons:
        # TODO hardcode
        keyboards = [[{"text": text}] for text in buttons]
        payload["reply_markup"].update({
            "keyboard": keyboards,
            "resize_keyboard": resize_keyboard,
            "one_time_keyboard": one_time_keyboard
        })

    if inline_keyboard:
        payload["reply_markup"].update({"inline_keyboard": inline_keyboard})

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.get(URL_SEND_MESSAGE.format(TELEGRAM_TOKEN), headers=headers, data=json.dumps(payload), timeout=10)

    response = response.json()

    res = response.get("ok")

    # маскирование текста
    payload["text"] = "*******"


if __name__=='__main__':
    send_message(
        chat_id=143698179,
        text="Вы обновили заказ на 5.500$ синие по 85.20. Если готовы забрать в кассе в течение часа, то напишите, пожалуйста, оператору @helporderconsult. Оператор передаст номер заказа и адрес отделения"
    )