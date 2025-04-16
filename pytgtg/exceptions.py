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
    pass

class TgtgRequestError(TgtgConnectionError):
    pass
