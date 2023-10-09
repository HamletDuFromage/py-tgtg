# py-tgtg

Unofficial TooGoodTooGo API. Login, fetch your favorites, refresh your access tokens.

## API

The api, located at `py-tgtg/api.py` expects a config file. Grab a copy of `config.json.defaults` and enter your email address and, optionally, your location and user-agent of choice. 

## CLI watcher

A very rudimentary favorites watcher, written as a proof of concept. Read its source `py-tgtg/watcher.py` to understand how to use the API. It expects a config file named `config.json` in its working directory.

## Telegram Bot

Polished Telegram bot. Supports multiple users, can work in group chats, auto-refreshes tokens, can be fully controlled from Telegram.

It requires that you provide your bot's token as an environnement variable (`TGTG_TELEGRAM_TOKEN`).

### Usage
- Set your email address with `/set_email`, then login with `/login`
- Target specific stores from you favorites with `/add_target [store_url]`. Make sure to disable web previews in your messages.
- Watch for available magic bags with `/watch [watch_interval]`
- Plenty of other commands are available too. 

### Like the app?
- Liberapay : <a href="https://liberapay.com/HamletDuFromage/donate"><img alt="Donate using Liberapay" src="https://liberapay.com/assets/widgets/donate.svg"></a>
- BTC: `1CoFc1bY5AHLP6Noe1zmqnJnp7ZWBxyo79`
- ETH: `0xf68f568e21a15934e0e9a6949288c3ca009140ba`
