class TgtgConnectionError(Exception):
    def __init__(self, message: str, response=None):
        super().__init__(message)
        self.response = response

class TgtgUnauthorizedError(TgtgConnectionError):
    pass

class TgtgForbiddenError(TgtgConnectionError):
    def __init__(self, message: str, captcha: str = "", response=None):
        super().__init__(message, response=response)
        self.captcha = captcha

class TgtgLoggedOutError(TgtgConnectionError):
    pass

class TgtgOrderError(TgtgConnectionError):
    def __init__(self, message: str, item_id: str, reason: str, response=None):
        super().__init__(message, response=response)
        self.item_id = item_id
        self.reason = reason

class TgtgRequestError(TgtgConnectionError):
    pass
