import threading
import time
import api
import argparse
from pprint import pprint

from exceptions import (
    TgtgConnectionError,
    TgtgForbiddenError,
    TgtgLoggedOutError,
    TgtgUnauthorizedError,
)


class TooGoodToGoWatcher:
    def __init__(self, config_fname="config.json"):
        self.api = api.TooGoodToGoApi(config_fname)

    def consoleLogin(self):
        try:
            self.api.login()
            return True
        except TgtgLoggedOutError:
            print("You are not logged in")

        try:
            auth_email_response = self.api.authByEmail()
            polling_id = auth_email_response.json().get("polling_id")
        except TgtgConnectionError as error:
            print(repr(error))
            return False

        input(
            f"The login email should have been sent to {self.api.getCredentials().get('email')}. Open the email on your PC and click the link. Don't open the email on a phone that has the TooGoodToGo app installed. That won't work. Press the Enter key when you clicked the link."
        )
        try:
            self.api.authPoll(polling_id)
            print("✔️ Successfully logged in!")
            self.api.setUserDevice()
            return True
        except TgtgConnectionError:
            print("❌ Failed to login.")
            return False

    def listMatches(self):
        try:
            businesses = self.api.listFavoriteBusinesses().json()
            for item in businesses.get("favourite_items"):
                if item.get("items_available", 0) > 0:
                    print(
                        f"{item.get('display_name')} (available: {item.get('items_available')})"
                    )
        except TgtgConnectionError as error:
            print(repr(error))

    def listOrders(self):
        orders = self.api.getOrders()
        orders = orders.json()
        for month in orders.get("orders_per_month"):
            for order in month.get("orders"):
                print(
                    order.get("time_of_purchase").split("T")[0],
                    order.get("order_id"),
                    order.get("state"),
                    order.get("store_name"),
                )
                

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TooGoodToGo Watcher")
    parser.add_argument(
        "--sleep",
        type=int,
        default=60,
        help="Time to sleep between checks in seconds (default: 60)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="Number of iterations for checking (default: 200)",
    )
    args = parser.parse_args()
    watcher = TooGoodToGoWatcher()
    watcher.consoleLogin()

    watcher.api.updateAppVersion()
    print("user agent:", watcher.api.config["api"]["headers"]["user-agent"])
    watcher.listOrders()

    pprint(watcher.api.getItemInfo(1170509).json().get("display_name"))
    c = 0
    while True:
        print(f"Watched favourites {c} times")
        threading.Thread(target=watcher.listMatches())
        if c > 200 == 0:
            print("stopped watching")
            break
        time.sleep(args.sleep)
        c += 1
