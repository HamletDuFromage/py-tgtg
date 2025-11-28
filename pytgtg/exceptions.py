class TgtgConnectionError(Exception):
    def __init__(self, endpoint : str, message: str, response=None):
        super().__init__(message)
        self.endpoint = endpoint
        self.response = response

class TgtgUnauthorizedError(TgtgConnectionError):
    pass

class TgtgForbiddenError(TgtgConnectionError):
    def __init__(self, endpoint: str, message: str, captcha: str = "", response=None):
        super().__init__(endpoint=endpoint, message=message, response=response)
        self.captcha = captcha

class TgtgLoggedOutError(Exception):
    pass

class TgtgOrderError(TgtgConnectionError):
    def __init__(self, endpoint: str, message: str, item_id: str, reason: str, response=None):
        super().__init__(endpoint=endpoint, message=message, response=response)
        self.item_id = item_id
        self.reason = reason

class TgtgRequestError(TgtgConnectionError):
    pass
