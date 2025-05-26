import re
import random
import uuid
import json

import httpx
import socksio
import ua_generator
from google_play_scraper import app

from exceptions import (
    TgtgConnectionError,
    TgtgForbiddenError,
    TgtgLoggedOutError,
    TgtgRequestError,
    TgtgUnauthorizedError,
)

BASE_URL = "https://apptoogoodtogo.com/api/"
COOKIE_DOMAIN = ".apptoogoodtogo.com"

AUTH = "auth/v5/"
AUTH_BY_EMAIL = AUTH + "authByEmail"
LOGOUT = AUTH + "logout"
AUTH_POLLING_ID = AUTH + "authByRequestPollingId"
REFRESH = "token/v1/refresh"

ITEM = "item/v8"
ITEM_INFO = ITEM + "/{}"

SET_FAVORITE = "user/favorite/v1/{}/update"

ORDER = "order/v8/"
ACTIVE_ORDERS = ORDER + "active"
# INACTIVE_ORDERS = ORDER + "inactive" # depreciated
ABORT_ORDER = ORDER + "{}/abort"

INVITATION = "invitation/v1/order/{}/"
ENABLE_INVITATION = INVITATION + "createOrEnable"
DISABLE_INVITATION = "invitation/v1/{}/disable"

BUCKET = "discover/v1/bucket"


class TooGoodToGoApi:
    def __init__(self, config_fname: str = "config.json"):
        self.config_fname = config_fname
        self.config = self.loadConfig()
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

    def newCorrelationId(self) -> None:
        self.config["api"]["headers"]["x-correlation-id"] = str(uuid.uuid4())
        self.saveConfig()

    def randomizeUserAgent(self) -> bool:
        user_agent = self.getUserAgent()
        new_agent = ua_generator.generate(platform='android').text
        pattern = r'(\([^)]+\))'
        match_old = re.search(pattern, user_agent)
        match_new = re.search(pattern, new_agent)
        if match_old and match_new:
            new_device = match_new.group(1)
            user_agent = re.sub(pattern, f'{new_device}', user_agent, count=1)
            self.config["api"]["headers"]["user-agent"] = user_agent
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
            cookies=httpx.Cookies(),
            params=self.config.get("api").get("params"),
            timeout=7.5 # default is 5s
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
                captcha = post.json().get("url", "")
                raise TgtgForbiddenError(message, captcha)
            else:
                raise TgtgConnectionError(message)
        self.failed_requests = 0
        return post

    def authByEmail(self) -> httpx.Response:
        self.newCorrelationId()
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": self.getCredentials().get("email"),
        }
        return self.post(AUTH_BY_EMAIL, json=json)

    def authPoll(self, polling_id: str) -> int:
        credentials = self.getCredentials()
        json = {
            "device_type": self.config.get("api").get("deviceType", "ANDROID"),
            "email": credentials.get("email"),
            "request_polling_id": polling_id,
        }
        post = self.post(AUTH_POLLING_ID, json=json)
        if post.status_code != 200:
            return post.status_code
        login = post.json()
        self.config["api"]["session"] = {
            "accessToken": login["access_token"],
            "refreshToken": login["refresh_token"],
        }
        self.saveConfig()
        return post.status_code

    def logout(self) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        return self.post(LOGOUT, headers=headers)

    def getSession(self) -> dict[str, str]:
        return self.config.get("api").get("session")

    def getHeaders(self) -> dict[str, str]:
        return self.config.get("api").get("headers")

    def getCredentials(self) -> dict[str, str]:
        return self.config.get("api").get("credentials")
    
    def setCookie(self, key:str, value: str) -> None:
        self.client.cookies.set(key, value, COOKIE_DOMAIN)

    def refreshToken(self) -> httpx.Response:
        session = self.getSession()
        json = {"refresh_token": session.get("refreshToken")}
        res = self.post(REFRESH, json=json)
        self.config["api"]["session"]["refreshToken"] = res.json().get("refresh_token")
        self.config["api"]["session"]["accessToken"] = res.json().get("access_token")
        self.config["origin"] = self.randomizeLocation(self.config.get("origin"))
        self.saveConfig()
        self.requests_count = 0
        return res

    def login(self) -> httpx.Response:
        session = self.getSession()
        if session.get("refreshToken", None):
            self.newCorrelationId()
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
            "paging": {"page": page, "size": page_size},
            "bucket": {"filler_type": "Favorites"},
            "filters": []
        }
        headers = self.getAuthHeaders(session)
        return self.post(BUCKET, json=json, headers=headers)

    def getOrders(self, page: int = 0, page_size: int = 20) -> httpx.Response:
        session = self.getSession()
        json = {
            "paging": {"page": page, "size": page_size},
        }
        headers = self.getAuthHeaders(session)
        return self.post(ORDER, json=json, headers=headers)

    def setFavorite(
        self, item_id: str | int, is_favorite: bool = True
    ) -> httpx.Response:
        session = self.getSession()
        json = {"is_favorite": is_favorite}
        headers = self.getAuthHeaders(session)
        return self.post(SET_FAVORITE.format(item_id), json=json, headers=headers)

    def getItemInfo(self, item_id: str | int) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        json = {"origin": None}
        return self.post(ITEM_INFO.format(item_id), json=json, headers=headers)

    def abortOrder(self, order_id: str) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        json = {"cancel_reason_id": 1}
        return self.post(ABORT_ORDER.format(order_id), json=json, headers=headers)

    def createInvitation(self, order_id: str, create: bool=True) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        endpoint = ENABLE_INVITATION if create else INVITATION
        return self.post(endpoint.format(order_id), headers=headers)
    
    def cancelInvitation(self, invitation_id: str) -> httpx.Response:
        session = self.getSession()
        headers = self.getAuthHeaders(session)
        return self.post(DISABLE_INVITATION.format(invitation_id), headers=headers)

    def saveConfig(self) -> None:
        with open(self.config_fname, "w") as outfile:
            json.dump(self.config, outfile, indent=4)

    def loadConfig(self):
        with open(self.config_fname, "r") as infile:
            return json.load(infile)


if __name__ == "__main__":
    api = TooGoodToGoApi()
    auth = api.authByEmail()
