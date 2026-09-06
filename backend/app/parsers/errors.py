class DocumentParseError(Exception):
    """Raised whenever a document can't be read.

    The message on this exception is written to be shown directly to the
    user (see error_handling section of the product spec — no stack
    traces, no internal exception names). Route handlers should catch this
    and turn it into an HTTP 400/422, not a 500.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message
