class TgtgConnectionError(Exception):
    pass

class TgtgUnauthorizedError(TgtgConnectionError):
    pass

class TgtgForbiddenError(TgtgConnectionError):
    pass

class TgtgLoggedOutError(TgtgConnectionError):
    pass

class TgtgOrderError(TgtgConnectionError):
    pass

class TgtgRequestError(TgtgConnectionError):
    pass
