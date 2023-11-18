import re
import random
import json

import httpx
import socksio
from google_play_scraper import app

from exceptions import (
    TgtgConnectionError,
    TgtgForbiddenError,
    TgtgLoggedOutError,
    TgtgRequestError,
    TgtgUnauthorizedError,
)

BASE_URL = "https://apptoogoodtogo.com/api/"
AUTH_BY_EMAIL = "auth/v3/authByEmail"
AUTH_POLLING_ID = "auth/v3/authByRequestPollingId"
REFRESH = "auth/v3/token/refresh"
ITEM = "item/v8"
ITEM_INFO = ITEM + "/{}"
SET_FAVORITE = ITEM + "/{}/setFavorite"
ACTIVE_ORDERS = "order/v7/active"
INACTIVE_ORDERS = "order/v7/inactive"
ABORT_ORDER = "order/v7/{}/abort"
BUCKET = "discover/v1/bucket"


class TooGoodToGoApi:
    def __init__(self, config_fname: str = "config.json"):
        self.config_fname = config_fname
        self.config = self.loadConfig()
        self.config["origin"] = self.randomizeLocation(self.config.get("origin"))
        self.baseurl = BASE_URL
        self.requests_count = 0
        self.failed_requests = 0
        self.proxy = ""
        self.newClient()

    def updateAppVersion(self) -> bool:
        tgtg = app("com.app.tgtg")
        version = tgtg.get("version")
        if version:
            user_agent = self.getUserAgent()
            self.config["api"]["headers"]["user-agent"] = re.sub(
                r"TGTG/[0-9]+\.[0-9]+\.[0-9]+", f"TGTG/{version}", user_agent
            )
            self.saveConfig()
            return True
        return False

    def getUserAgent(self) -> str:
        return self.config.get("api").get("headers").get("user-agent")

    def randomizeLocation(self, origin: dict[str, float]) -> dict[str, float]:
        var = 1 + random.randint(-100, 100) / 1000
        origin["latitude"] = origin.get("latitude", 0) * var
        origin["longitude"] = origin.get("longitude", 0) * var
        return origin

    def url(self, endpoint: str) -> str:
        return f"{self.baseurl}{endpoint}"

    def newClient(self, use_proxy: bool = False) -> None:
        self.client = httpx.Client(
            cookies=httpx.Cookies(), params=self.config.get("api").get("params")
        )

    def getAuthHeaders(self, session: dict[str, str]) -> dict[str, str]:
        return {"Authorization": f"Bearer {session.get('accessToken')}"}

    def post(
        self, endpoint: str, json: dict = {}, headers: dict = {}
    ) -> httpx.Response:
        self.requests_count += 1
        self.failed_requests += 1
        try:
            post = self.client.post(
                self.url(endpoint), json=json, headers={**headers, **self.getHeaders()}
            )
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

    def authByEmail(self) -> httpx.Response:
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": self.getCredentials().get("email"),
        }
        return self.post(AUTH_BY_EMAIL, json=json)

    def authPoll(self, polling_id: str) -> httpx.Response:
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
            "refreshToken": login["refresh_token"],
        }
        self.saveConfig()
        return post

    def getSession(self) -> dict[str, str]:
        return self.config.get("api").get("session")

    def getHeaders(self) -> dict[str, str]:
        return self.config.get("api").get("headers")

    def getCredentials(self) -> dict[str, str]:
        return self.config.get("api").get("credentials")

    def refreshToken(self) -> httpx.Response:
        session = self.getSession()
        json = {"refresh_token": session.get("refreshToken")}
        res = self.post(REFRESH, json=json)
        self.config["api"]["session"]["refreshToken"] = res.json().get("refresh_token")
        self.config["api"]["session"]["accessToken"] = res.json().get("access_token")
        self.saveConfig()
        self.requests_count = 0
        return res

    def login(self) -> httpx.Response:
        session = self.getSession()
        if session.get("refreshToken", None):
            return self.refreshToken()
        raise TgtgLoggedOutError("You are not logged in")

    def updateSession(self, token: dict[str, str]) -> None:
        self.config["api"]["session"]["accessToken"] = token["refresh_token"]

    def listFavoriteBusinesses(
        self, radius: int = 200, page: int = 0, page_size: int = 50
    ) -> httpx.Response:
        session = self.getSession()
        json = {
            "origin": self.config.get("origin"),
            "radius": radius,
            "user_id": session.get("userId"),
            "paging": {"page": page, "size": page_size},
            "bucket": {"filler_type": "Favorites"},
        }
        headers = self.getAuthHeaders(session)
        return self.post(BUCKET, json=json, headers=headers)

    def getActiveOrders(self) -> httpx.Response:
        session = self.getSession()
        json = {"user_id": session.get("userId")}
        headers = self.getAuthHeaders(session)
        return self.post(ACTIVE_ORDERS, json=json, headers=headers)

    def getInactiveOrders(self, page: int = 0, page_size: int = 20) -> httpx.Response:
        session = self.getSession()
        json = {
            "paging": {"page": page, "size": page_size},
            "user_id": session.get("userId"),
        }
        headers = self.getAuthHeaders(session)
        return self.post(INACTIVE_ORDERS, json=json, headers=headers)

    def setFavorite(self, item_id: str, is_favorite: bool = True) -> httpx.Response:
        session = self.getSession()
        json = {"is_favorite": is_favorite}
        headers = self.getAuthHeaders(session)
        return self.post(SET_FAVORITE.format(item_id), json=json, headers=headers)

    def getItemInfo(self, item_id: str) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        json = {"user_id": session.get("userId"), "origin": None}
        return self.post(ITEM_INFO.format(item_id), json=json, headers=headers)

    def abortOrder(self, order_id: str) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        json = {"cancel_reason_id": 1}
        return self.post(ABORT_ORDER.format(order_id), json=json, headers=headers)

    def saveConfig(self) -> None:
        with open(self.config_fname, "w") as outfile:
            json.dump(self.config, outfile, indent=4)

    def loadConfig(self):
        with open(self.config_fname, "r") as infile:
            return json.load(infile)


if __name__ == "__main__":
    api = TooGoodToGoApi()
    auth = api.authByEmail()
