class CLIError(Exception):
    pass


class HTTPRequestError(CLIError):
    def __init__(self, url: str, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.code = code
