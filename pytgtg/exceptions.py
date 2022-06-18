import httpx

class TgtgConnectionError(httpx.NetworkError):
    pass

class TgtgUnauthorizedError(TgtgConnectionError):
    pass

class TgtgForbiddenError(TgtgConnectionError):
    pass

class TgtgLoggedOutError(TgtgConnectionError):
    pass

class TgtgOrderError(TgtgConnectionError):
    pass
