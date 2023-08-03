import re
import random
import json

import httpx
import socksio
from google_play_scraper import app

from exceptions import (TgtgConnectionError, TgtgForbiddenError,
                        TgtgLoggedOutError, TgtgRequestError,
                        TgtgUnauthorizedError)

BASE_URL = "https://apptoogoodtogo.com/api/"
AUTH_BY_EMAIL = "auth/v3/authByEmail"
AUTH_POLLING_ID = "auth/v3/authByRequestPollingId"
REFRESH = "auth/v3/token/refresh"
ITEM = "item/v8"
ACTIVE_ORDERS = "order/v6/active"
INACTIVE_ORDERS = "order/v6/inactive"
BUCKET = "discover/v1/bucket"


class TooGoodToGoApi:
    def __init__(self, config_fname="config.json"):
        self.config_fname = config_fname
        self.config = self.loadConfig()
        self.config["origin"] = self.randomizeLocation(self.config.get("origin"))
        self.baseurl = BASE_URL
        self.requests_count = 0
        self.failed_requests = 0
        self.proxy = ""
        self.newClient()

    def updateAppVersion(self):
        tgtg = app("com.app.tgtg")
        version = tgtg.get("version")
        if version:
            user_agent = self.getUserAgent()
            self.config["api"]["headers"]["user-agent"] = re.sub(r"TGTG/[0-9]+\.[0-9]+\.[0-9]+", f"TGTG/{version}", user_agent)
            self.saveConfig()
            return True
        return False

    def getUserAgent(self):
        return self.config.get("api").get("headers").get("user-agent")

    def randomizeLocation(self, origin):
        var = 1 + random.randint(-100, 100)/1000
        origin["latitude"] = origin.get("latitude") * var
        origin["longitude"] = origin.get("longitude") * var
        return origin

    def url(self, endpoint):
        return f"{self.baseurl}{endpoint}"

    def newClient(self, use_proxy=False):
        self.client = httpx.Client(cookies=httpx.Cookies(), params=self.config.get("api").get("params"))

    def post(self, endpoint, json={}, headers={}):
        self.requests_count += 1
        self.failed_requests += 1
        try:
            post = self.client.post(self.url(endpoint), json=json, headers={**headers, **self.getHeaders()})
        except (socksio.exceptions.ProtocolError, httpx.RequestError) as error:
            raise TgtgRequestError(repr(error))
        if not post.is_success:
            message = f"Error {post.status_code} for post request {endpoint}"
            if post.status_code == 401:
                raise TgtgUnauthorizedError(message)
            elif post.status_code == 403:
                raise TgtgForbiddenError(message)
            else:
                raise TgtgConnectionError(message)
        self.failed_requests = 0
        return post

    def authByEmail(self):
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": self.getCredentials().get("email")
        }
        return self.post(AUTH_BY_EMAIL, json=json)

    def authPoll(self, polling_id):
        credentials = self.getCredentials()
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": credentials.get("email"),
            "request_polling_id": polling_id,
        }
        post = self.post(AUTH_POLLING_ID, json=json)
        login = post.json()
        self.config["api"]["session"] = {
            "userId": login["startup_data"]["user"]["user_id"],
            "accessToken": login["access_token"],
            "refreshToken": login["refresh_token"]
        }
        self.saveConfig()
        return post

    def getSession(self):
        return self.config.get("api").get("session")

    def getHeaders(self):
        return self.config.get("api").get("headers")

    def getCredentials(self):
        return self.config.get("api").get("credentials")

    def refreshToken(self):
        session = self.getSession()
        json = {"refresh_token": session.get("refreshToken")}
        res = self.post(REFRESH, json=json)
        self.config["api"]["session"]["refreshToken"] = res.json().get("refresh_token")
        self.config["api"]["session"]["accessToken"] = res.json().get("access_token")
        self.saveConfig()
        self.requests_count = 0
        return res

    def login(self):
        session = self.getSession()
        if session.get("refreshToken", None):
            return self.refreshToken()
        raise TgtgLoggedOutError("You are not logged in")

    def updateSession(self, token):
        self.config["api"]["session"]["accessToken"] = token["refresh_token"]
        return token

    def listFavoriteBusinesses(self, radius=200, page=0, page_size=50):
        session = self.getSession()
        json = {
            "origin": self.config.get("origin"),
            "radius": radius,
            "user_id": session.get("userId"),
            "paging": {"page": page, "size": page_size},
            "bucket": {"filler_type": "Favorites"}
        }
        headers = {"Authorization": f"Bearer {session.get('accessToken')}"}
        return self.post(BUCKET, json=json, headers=headers)

    def getActiveOrders(self):
        session = self.getSession()
        json = {
            "user_id": session.get("userId")
        }
        headers = {"Authorization": f"Bearer {session.get('accessToken')}"}
        return self.post(ACTIVE_ORDERS, json=json, headers=headers)

    def getInactiveOrders(self, page=0, page_size=20):
        session = self.getSession()
        json = {
            "paging": {"page": page, "size": page_size},
            "user_id": session.get("userId")
        }
        headers = {"Authorization": f"Bearer {session.get('accessToken')}"}
        return self.post(INACTIVE_ORDERS, json=json, headers=headers)

    def saveConfig(self):
        with open(self.config_fname, "w") as outfile:
            json.dump(self.config, outfile, indent=4)

    def loadConfig(self):
        with open(self.config_fname, "r") as infile:
            return json.load(infile)


if __name__ == "__main__":
    api = TooGoodToGoApi()
    auth = api.authByEmail()
