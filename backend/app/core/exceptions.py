"""Domain errors raised by services and mapped to HTTP responses in main."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class DuplicateBookingError(ConflictError):
    """The same channel booking (source + external reference) already exists."""


class UnprocessableError(DomainError):
    status_code = 422
