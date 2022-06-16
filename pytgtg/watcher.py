
import threading
import time

import api

from .exceptions import (TgtgConnectionError, TgtgForbiddenError,
                         TgtgLoggedOutError, TgtgUnauthorizedError)


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

        input(f"The login email should have been sent to {self.api.getCredentials().get('email')}. Open the email on your PC and click the link. Don't open the email on a phone that has the TooGoodToGo app installed. That won't work. Press the Enter key when you clicked the link.")
        try:
            self.api.authPoll(polling_id)
            print("✔️ Successfully logged in!")
            return True
        except TgtgConnectionError:
            print("❌ Failed to login.")
            return False

    def listMatches(self):
        try:
            businesses = self.api.listFavoriteBusinesses().json()
            for item in businesses.get("items"):
                if item.get("items_available", 0) > 0:
                    print(f"{item.get('display_name')} (available: {item.get('items_available')})")
        except TgtgConnectionError as error:
            print(repr(error))


if __name__ == "__main__":
    watcher = TooGoodToGoWatcher()
    watcher.consoleLogin()
    c = 0
    while True:
        threading.Thread(target=watcher.listMatches())
        if c > 200 == 0:
            print("stopped watching")
            break
        time.sleep(60)
