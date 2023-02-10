import asyncio
import datetime
from dateutil import parser
import logging
import os
import pathlib
import random
import re
import shutil

from telegram import Bot, Update
from telegram import constants, helpers
from telegram.ext import (ApplicationBuilder, CallbackContext, CommandHandler,
                          MessageHandler, filters)

from api import TooGoodToGoApi
from exceptions import (TgtgConnectionError, TgtgForbiddenError,
                        TgtgLoggedOutError, TgtgUnauthorizedError)

MAX_REQUESTS = 1_000_000
MAX_REQUESTS_PHOTO_ID = "AgACAgQAAxkDAAIE_WKTbr9hZFdYN9atFpB_inbKLJBcAAJVrjEbvMucUN6ucAsMN1bdAQADAgADcwADJAQ"
MAX_FAILED_REQUESTS = 3

DEFAULT_WATCH_INTERVAL = 15.0

PATH = pathlib.Path(__file__).parent.resolve()


class User:
    def __init__(self, update):
        self.chat_id = update.effective_chat.id
        self.type = update.effective_chat.type
        self.user_id = update.effective_user.id
        self.username = update.effective_user.username
        self.name = update.effective_user.first_name
        self.config_fname = f"config_{self.chat_id}.json"
        self.createConfig(self.config_fname)
        self.polling_id = None
        self.watch_interval = DEFAULT_WATCH_INTERVAL
        self.watching = False
        self.watcher = None
        self.seen = {}
        self.api = TooGoodToGoApi(self.config_fname)
        self.api.config.setdefault("targets", {})
        if self.username:
            self.api.config.setdefault("telegram_username", self.username)
        self.targets = self.api.config.get("targets")
        self.pinning = True
        logging.warn(f"User {self.name} logged in. chat_id: {self.chat_id} | user_id: {self.user_id} | username: {self.username}")

    def createConfig(self, f_name):
        if not os.path.exists(f_name):
            shutil.copy(f"{PATH}/config.json.defaults", f_name)

    def stopWatching(self):
        self.watching = False
        self.watch_interval = DEFAULT_WATCH_INTERVAL
        try:
            self.watcher.cancel()
        except AttributeError:
            pass
        self.seen = {}

    def shouldWatch(self):
        return True

    def clearHistory(self):
        self.seen = {}

    def getPrice(self, item):
        price = item.get('item').get('price_including_taxes')
        res = f"{price.get('minor_units') / 10 ** price.get('decimals'):.2f}"
        code = price.get("code")
        if code == "EUR":  # use match/case statement in the future
            res += "€"
        elif code == "USD":
            res = f"${res}"
        else:
            res += code
        return res

    def matchesDesired(self, display_name, targets):
        if "*" in targets:
            return "*"
        for target in targets:
            store = target.lower().replace('_', ' ')
            try:
                description = re.search(r".+\((.+)\)+$", store).group(1)
                store = store[:-len(description) - 2]
            except AttributeError:
                description = ""
            display_name = display_name.lower()
            if store in display_name and description in display_name:
                return target
        return False

    def getMatches(self, targets, minQty=1):
        res = {}
        if targets == {}:
            return res
        businesses = self.api.listFavoriteBusinesses().json()
        for item in businesses.get("items"):
            available = item.get("items_available", 0)
            display_name = item.get("display_name")
            if available >= minQty:
                match = self.matchesDesired(display_name, targets.keys())
                if match:
                    res[item.get("item").get("item_id")] = {"display_name": display_name,
                                                            "quantity": targets.get(match),
                                                            "available": available,
                                                            "purchase_end": item.get("purchase_end"),
                                                            "pickup_interval": item.get("pickup_interval"),
                                                            "price": self.getPrice(item)}
            elif display_name in self.seen:
                self.seen.pop(display_name)  # remove item from seen list in case of a future restock
        return res


class TooGoodToGoTelegram:
    def __init__(self, TOKEN):
        self.LOGS = "telegrambot.log"
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            level=logging.INFO, filename=self.LOGS)
        self.TOKEN = TOKEN

        self.application = ApplicationBuilder().token(TOKEN).build()

        self.commands = {self.help: "List available commands", self.set_email: "Set your TGTG email login", self.login: "Request TGTG login",
                         self.login_continue: "Confirm login request", self.add_target: "Add an item to watch", self.remove_target: "Remove a watched item", self.show_targets: "Show currently watched items",
                         self.watch: "Start watching items", self.stop_watching: "Stop watching items", self.dry_run: "See favourites magic bags matching targets", self.pin_results: "Pin messages about available Magic Bags",
                         self.status: "Show the bot's status", self.clear_history: "Clear history for seen items", self.refresh: "Get a new set of tokens",
                         self.shutdown: "Shut your client down", self.error: "See common errors", self.start: "Welcome"}
        self.users = {}

    def runBot(self):
        self.handleHandlers()
        self.application.run_polling()

    def handleHandlers(self):
        for func in self.commands.keys():
            self.application.add_handler(CommandHandler(func.__name__, func), group=0)
        self.application.add_handler(MessageHandler(filters.COMMAND, self.wrong_command), group=0)
        self.application.add_handler(MessageHandler(filters.COMMAND, self.command_logger), group=1)

    def getUser(self, update):
        chat_id = update.effective_chat.id
        if chat_id not in self.users:
            self.users[chat_id] = User(update)
        return self.users.get(chat_id)

    def errorText(self, error):
        return f"{repr(error)}\nType /error for more info."

    async def handleError(self, error, user, update, context):
        await context.bot.send_message(chat_id=user.chat_id, text=self.errorText(error), disable_notification=True)
        if type(error) == TgtgUnauthorizedError:
            await self.refresh(update, context)
        elif type(error) == TgtgForbiddenError:
            user.api.newClient()

    def randMultiplier(self):
        return 1 + random.randint(-100, 100)/1000

    def calculatePickupInterval(self, pickup_interval):
        now = datetime.datetime.now(datetime.timezone.utc)
        start_delta = parser.parse(pickup_interval["start"]) - now
        end_delta = parser.parse(pickup_interval["end"]) - now
        return (f"{start_delta.seconds//3600} hours and {(start_delta.seconds//60)%60} minutes", f"{end_delta.seconds//3600} hours and {(end_delta.seconds//60)%60} minutes")

    async def sendPinnedMessage(self, context, chat_id, text, parse_mode=None, pinned=True):
        message = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
        if pinned:
            await context.bot.pin_chat_message(chat_id=chat_id, message_id=message.message_id, disable_notification=False)

    async def exceedQuota(self, user, context, update):
        if user.api.requests_count >= MAX_REQUESTS:
            await context.bot.send_photo(chat_id=user.chat_id, photo=MAX_REQUESTS_PHOTO_ID, caption=f"You've sent too many requests (more than {MAX_REQUESTS}). Stopping for now.")
            await self.refresh(update, context)
            user.api.requests_count = 0
            return True
        if user.api.failed_requests >= MAX_FAILED_REQUESTS:
            await context.bot.send_photo(chat_id=user.chat_id, photo=MAX_REQUESTS_PHOTO_ID, caption=f"Too many requests have failed (more than {MAX_FAILED_REQUESTS}). Stopping for now.")
            user.api.failed_requests = 0
            return True
        return False

    async def hasOwnerRights(self, update):
        return update.effective_chat.type == "private" or \
            update.effective_user in [admin.user for admin in await update.effective_chat.get_administrators()]

    def createHyperlink(self, link, text):
        return f"<a href=\"{link}\">{text}</a>"

    async def watchLoop(self, update, context):
        user = self.getUser(update)
        while user.watching and not await self.exceedQuota(user, context, update):
            start = datetime.datetime.now()
            try:
                if user.shouldWatch():
                    text = ""
                    matches = user.getMatches(user.targets)
                    for key, value in matches.items():
                        available = value.get("available")
                        display_name = value.get('display_name')
                        purchase_end = value.get("purchase_end")
                        if user.seen.get(display_name, None) != purchase_end:
                            text += f"👉🏻 {self.createHyperlink(f'https://share.toogoodtogo.com/item/{key}/', display_name)} - {value.get('price')} (avail: {available})\n"
                            user.seen[display_name] = purchase_end
                    if text:
                        await self.sendPinnedMessage(context=context, chat_id=user.chat_id, text=text, parse_mode=constants.ParseMode.HTML, pinned=user.pinning)
            except TgtgConnectionError as error:
                await self.handleError(error, user, update, context)
            sleep_time = max(user.watch_interval - (datetime.datetime.now() - start).total_seconds(), 0)
            await asyncio.sleep(sleep_time * self.randMultiplier())
        await self.stop_watching(update, context)

    async def dry_run(self, update, context):
        await self.show_targets(update, context)
        user = self.getUser(update)
        try:
            text = ""
            matches = user.getMatches(user.targets, minQty=0)
            for key, value in matches.items():
                available = value.get("available")
                display_name = value.get('display_name')
                text += f"👉🏻 {self.createHyperlink(f'https://share.toogoodtogo.com/item/{key}/', display_name)} - {value.get('price')} (avail: {available})\n"
            if text:
                await context.bot.send_message(chat_id=user.chat_id, text=text, parse_mode=constants.ParseMode.HTML, disable_web_page_preview=True)
            else:
                await context.bot.send_message(chat_id=user.chat_id, text="No magic matches targets.")
        except TgtgConnectionError as error:
            await self.handleError(error, user, update, context)

    async def watch(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        try:
            user.watch_interval = float(context.args[0])
        except IndexError:
            await context.bot.send_message(chat_id=user.chat_id, text="🤓 Don't forget that you can set an interval with /watch [sec].\n")
        except ValueError:
            await context.bot.send_message(chat_id=user.chat_id, text="Usage:\n/watch [sec].")
            return
        await context.bot.send_message(chat_id=user.chat_id, text=f"🔄 Refreshing the favorites with an interval of {user.watch_interval} seconds.\nStop watching by typing /stop_watching.")
        await self.show_targets(update, context)
        user.watching = True
        if user.watcher is None or user.watcher.done():
            user.watcher = asyncio.create_task(self.watchLoop(update, context))

    async def stop_watching(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        await context.bot.send_message(chat_id=user.chat_id, text="Stopped watching the favorites.")
        user.stopWatching()

    async def add_target(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        try:
            quantity = int(context.args[1])
            keyword = context.args[0].lower()
            if quantity > 0:
                user.targets.update({keyword: quantity})
                text = f"Targeting item {keyword} with quantity {quantity}."
            else:
                user.targets.pop(keyword)
                text = f"Removed {keyword} from targets."
            user.api.saveConfig()
        except (IndexError, ValueError):
            text = "Usage:\n/add_target [keyword_for_store] [quantity]\nFilter specific Magic Bags with /add_target [keyword_for_store(keyword_for_bag)] [quantity]\nWatch all the favorites with /add_target * [quantity]"
        except KeyError:
            text = f"Can't remove \"{keyword}\" since it isn't being targeted."
        await context.bot.send_message(chat_id=user.chat_id, text=text)

    async def remove_target(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        try:
            keyword = context.args[0].lower()
            user.targets.pop(keyword)
            user.api.saveConfig()
            text = f"Removed {keyword} from targets."
        except (IndexError, ValueError):
            text = "Usage:\n/remove_target [keyword]"
        except KeyError:
            text = f"Can't remove \"{keyword}\" since it isn't being targeted."
        await context.bot.send_message(chat_id=user.chat_id, text=text)

    async def show_targets(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        text = "Targeting the following items:\n" + "\n".join(
            (f"📌 {key} (qty: {value})" for key, value in user.targets.items()))
        await context.bot.send_message(chat_id=user.chat_id, text=text)

    async def pin_results(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        try:
            user.pinning = context.args[0] != "0"
            text = f"Now pinning results: {user.pinning}"
        except (IndexError, ValueError):
            text = "Usage:\n/pin_results [0-1]"
        await context.bot.send_message(chat_id=user.chat_id, text=text)

    async def status(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        await context.bot.send_message(chat_id=user.chat_id, text=f"👀 Watching status: [{user.watching}] with interval: {user.watch_interval}s.")

    async def set_email(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        try:
            user.api.config["api"]["credentials"]["email"] = context.args[0]
            user.api.saveConfig()
            text = f"Successfully changed email address to {context.args[0]}!"
        except IndexError:
            text = "Usage:\n/set_email name@domain.tld"
        await context.bot.send_message(chat_id=user.chat_id, text=text)

    async def login(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        user = self.getUser(update)
        try:
            auth_email_response = user.api.authByEmail()
            user.polling_id = auth_email_response.json().get("polling_id")
            text = f"📧 The login email should have been sent to {user.api.getCredentials().get('email')}. Open the email on your PC and click the link. Don't open the email on a phone that has the TooGoodToGo app installed. That won't work.\nSend /login_continue when you clicked the link."
            await context.bot.send_message(chat_id=user.chat_id, text=text)
        except TgtgConnectionError as error:
            await self.handleError(error, user, update, context)

    async def login_continue(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        user = self.getUser(update)
        if user.polling_id is None:
            text = "Run /login before running this command."
        else:
            try:
                user.api.authPoll(user.polling_id)
                text = "✅ Successfully logged in!"
            except TgtgConnectionError:
                text = "⛔ Failed to login."
        await context.bot.send_message(chat_id=user.chat_id, text=text)

    async def refresh(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        try:
            user.api.login()
            await context.bot.send_message(chat_id=user.chat_id, text=f"🔄 Refreshed the tokens.", disable_notification=True)
        except TgtgConnectionError as error:
            await self.handleError(error, user, update, context)

    async def shutdown(self, update: Update, context: CallbackContext):
        await self.stop_watching(update, context)
        chat_id = update.effective_chat.id
        try:
            self.users.pop(chat_id)
            text = "Shut your instance of the TooGoodNotToBotClient down."
        except KeyError:
            text = "No instance of the TooGoodNotToBot is running."
        await context.bot.send_message(chat_id=chat_id, text=text)

    async def clear_history(self, update: Update, context: CallbackContext):
        user = self.getUser(update)
        user.clearHistory()
        await context.bot.send_message(chat_id=user.chat_id, text="🗑️ Cleared history for seen items.")

    async def start(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        user = self.getUser(update)
        await context.bot.send_message(chat_id=user.chat_id, text=f"👋🏻 Welcome to the TooGoodNotToBot!\nType /help to get started.")

    async def help(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        text = "\n".join(
            (f"/{command.__name__} → {description}" for command, description in self.commands.items()))
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    async def error(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ Common errors and possible diagnosis:\n- 403: Bot's IP is temporally banned.\n- 401: You've been kicked, try refreshing your tokens with /refresh or log back in with /login.")

    async def wrong_command(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🤔 Invalid command.\nType /help for help.")

    async def command_logger(self, update: Update, context: CallbackContext.DEFAULT_TYPE):
        logging.info(f"`{update.message.text}` --- chat:{update.effective_chat.id} | {update.effective_user.first_name}: {update.effective_user.id}")

    async def setCommands(self):
        init = Bot(self.TOKEN)
        hints = []
        for key, value in self.commands.items():
            hints.append(("/" + key.__name__, value))
        async with init:
            await init.setMyCommands(hints)


if __name__ == '__main__':

    TOKEN = os.getenv("TGTG_TELEGRAM_TOKEN")
    if TOKEN is None:
        logging.error("Didn't find the TGTG_TELEGRAM_TOKEN environment variable")
    else:
        bot = TooGoodToGoTelegram(TOKEN)

        loop = asyncio.new_event_loop()
        commands = loop.run_until_complete(bot.setCommands())
        loop.close()

        bot.runBot()
