class TgtgConnectionError(Exception):
    pass

class TgtgUnauthorizedError(TgtgConnectionError):
    pass

class TgtgForbiddenError(TgtgConnectionError):
    def __init__(self, message: str, captcha: str = ""):
        super().__init__(message)
        self.captcha = captcha

class TgtgLoggedOutError(TgtgConnectionError):
    pass

class TgtgOrderError(TgtgConnectionError):
    def __init__(self, message: str, item_id: str, reason: str):
        super().__init__(message)
        self.item_id = item_id
        self.reason = reason

class TgtgRequestError(TgtgConnectionError):
    pass
