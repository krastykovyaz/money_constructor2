# money_constructor

A collection of Telegram bots and scrapers for currency/crypto exchange rates
(RUB/USD/EUR/USDT), built around python-telegram-bot 13.x. The actively
deployed bot is `exchange_ligov_fintex_cbr_crypto.py` (see below); the other
scripts in the repo root are earlier/related bots not currently running as
services on this server.

## Setup

Requires Python 3.10+ (deployed and tested on 3.10.12).

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Copy the example env file and fill in real values:

```bash
cp .env-example .env
```

| Variable | Used by | Notes |
|---|---|---|
| `TELEGRAM_TOKEN` | poster bot | |
| `REGISTRATION_BOT_TELEGRAM_TOKEN` | registration bot | |
| `EXCHANGE_DESK_BOT_TOKEN` | `exchange_ligov_fintex_cbr_crypto.py` | token for the `/currency` bot and its update notifications |
| `ALL_EXCHANGE_BOT_TOKEN` | `all_exchange.py` | token for the `/currency` bot in `all_exchange.py` and its update notifications |
| `LIGOVKA_BOT_TOKEN` | `ligovka.py` | |
| `FINANCIAL_AGENT_BOT_TOKEN` | `send_message_tg.py` | @financialagent_bot |
| `ACCOUNTER_BOT_TOKEN` | `accounter_bot_v2.py` | |
| `LEGACY_ACCOUNTER_BOT_TOKEN` | `accounter_bot.py`, `get_profile.py` | shared by both, earlier accounter bot versions |
| `SBER_EXCHANGE_BOT_TOKEN` | `sber_excange_bot.py` | |
| `CURRENCY_PARSER_BOT_TOKEN` | `currency_parser.py` | |
| `CRYPTO_CURRENCY_BOT_TOKEN` | `crypto_currency.py` | |

`.env` is git-ignored — never commit real tokens. Scripts that read config
via `os.getenv`/`os.environ` pick these up automatically through
`python-dotenv`; some of the older scripts in this repo still have
credentials hardcoded inline instead and predate this convention.

## exchange_ligov_fintex_cbr_crypto.py

Polls fintech-exchange.ru (via headless Chrome/Selenium), ligovka.ru, CNBC,
Binance and the CBR XML feed every 60s, and serves the combined rates to
Telegram users via the `/currency` command. Runs as the `exchange_desk`
systemd service.

### Browser dependency

This script needs a real (non-snap) Chromium/Chrome build plus a
version-matched ChromeDriver — snap-packaged Chromium cannot be launched by
ChromeDriver inside a container (`execve` fails with `EACCES` due to
snap-confine). Install
[Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/)
instead:

```bash
mkdir -p /opt/chrome-for-testing
cd /tmp
VER=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['channels']['Stable']['version'])")
curl -sL -o chrome.zip "https://storage.googleapis.com/chrome-for-testing-public/$VER/linux64/chrome-linux64.zip"
curl -sL -o driver.zip "https://storage.googleapis.com/chrome-for-testing-public/$VER/linux64/chromedriver-linux64.zip"
unzip -q -o chrome.zip -d /opt/chrome-for-testing/
unzip -q -o driver.zip -d /opt/chrome-for-testing/
chmod +x /opt/chrome-for-testing/chrome-linux64/chrome /opt/chrome-for-testing/chromedriver-linux64/chromedriver
```

The script defaults to `/opt/chrome-for-testing/chrome-linux64/chrome` and
`/opt/chrome-for-testing/chromedriver-linux64/chromedriver`. Override with
the `CHROME_BINARY` / `CHROMEDRIVER_BINARY` env vars if installed elsewhere.

### Running

```bash
./venv/bin/python exchange_ligov_fintex_cbr_crypto.py
```

### Deploying as a systemd service

`service/exchange_desk.service` and `service/bot_all_exchange.service` match
what's deployed — both `exchange_ligov_fintex_cbr_crypto.py` and
`all_exchange.py` run as services on this host. Install either with:

```bash
sudo cp service/exchange_desk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now exchange_desk.service
```

`service/chrome-tmp-cleanup.timer` runs hourly to remove stale Chrome
profile temp dirs left behind by killed/crashed Selenium sessions:

```bash
sudo cp service/chrome-tmp-cleanup.service service/chrome-tmp-cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chrome-tmp-cleanup.timer
```

Logs: `journalctl -u exchange_desk -f` / `journalctl -u bot_all_exchange -f`.
Journald retention on this host is capped to 3 days / 200MB via a drop-in at
`/etc/systemd/journald.conf.d/retention.conf` (not part of this repo — a
host-level setting).

## Other scripts

The remaining top-level scripts (`accounter_bot*.py`, `currency_parser.py`,
`sberexchange_bot.py`, etc.) and the other unit files under `service/` are
earlier/related bots. They are not currently running on this server and
aren't documented here in detail — check each script's source before
deploying it.
