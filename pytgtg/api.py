
import json
import random

import httpx

from exceptions import (TgtgConnectionError, TgtgForbiddenError,
                        TgtgLoggedOutError, TgtgOrderError,
                        TgtgUnauthorizedError)


class TooGoodToGoApi:
    def __init__(self, config_fname="config.json"):
        self.config_fname = config_fname
        self.config = self.loadConfig()
        self.config["origin"] = self.randomizeLocation(self.config.get("origin"))
        self.baseurl = "https://apptoogoodtogo.com/api/"
        self.newClient()
        self.requests_count = 0
        self.failed_requests = 0

    def randomizeLocation(self, origin):
        var = 1 + random.randint(-100, 100)/1000
        origin["latitude"] = origin.get("latitude") * var
        origin["longitude"] = origin.get("longitude") * var
        return origin

    def url(self, endpoint):
        return f"{self.baseurl}{endpoint}"

    def newClient(self, proxy=""):
        try:
            self.client = httpx.Client(
                cookies=httpx.Cookies(),
                params=self.config.get("api").get("params"),
                proxies=proxy)
        except ValueError:
            self.client = httpx.Client(cookies=httpx.Cookies(), params=self.config.get("api").get("params"))

    def post(self, endpoint, json={}, headers={}):
        self.requests_count += 1
        post = self.client.post(self.url(endpoint), json=json, headers={**headers, **self.getHeaders()})
        if not post.is_success:
            self.failed_requests += 1
            error = f"Error {post.status_code} for post request {endpoint}"
            if post.status_code == 401:
                raise TgtgUnauthorizedError(error)
            elif post.status_code == 403:
                raise TgtgForbiddenError(error)
            else:
                raise TgtgConnectionError(error)
        self.failed_requests = 0
        return post

    def authByEmail(self):
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": self.getCredentials().get("email")
        }
        return self.post("auth/v3/authByEmail", json=json)

    def authPoll(self, polling_id):
        credentials = self.getCredentials()
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": credentials.get("email"),
            "request_polling_id": polling_id,
        }
        post = self.post("auth/v3/authByRequestPollingId", json=json)
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
        self.client = httpx.Client(cookies=httpx.Cookies(), params=self.config.get("api").get("params"))
        session = self.getSession()
        json = {"refresh_token": session.get("refreshToken")}
        res = self.post("auth/v3/token/refresh", json=json)
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

    def listFavoriteBusinesses(self):
        session = self.getSession()
        json = {
            "favorites_only": True,
            "origin": self.config.get("origin"),
            "radius": 200,
            "user_id": session.get("userId")
        }
        headers = {"Authorization": f"Bearer {session.get('accessToken')}"}
        return self.post("item/v7/", json=json, headers=headers)

    def saveConfig(self):
        with open(self.config_fname, "w") as outfile:
            json.dump(self.config, outfile, indent=4)

    def loadConfig(self):
        with open(self.config_fname, "r") as infile:
            return json.load(infile)


if __name__ == "__main__":
    api = TooGoodToGoApi()
    auth = api.authByEmail()
