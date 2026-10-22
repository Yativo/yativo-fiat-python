"""Errors raised by the SDK. None of them ever contain your API credentials."""

from typing import Any, Dict, Mapping, Optional


class YativoError(Exception):
    """Base class for every SDK error."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        fields: Optional[Mapping[str, Any]] = None,
        retryable: bool = False,
        retry_after: Optional[float] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        #: HTTP status, when the API answered.
        self.status = status
        #: Stable code, e.g. ``validation_error`` or ``duplicate_reference``.
        self.code = code
        #: Messages per field, for validation errors.
        self.fields: Dict[str, Any] = dict(fields or {})
        self.retryable = retryable
        self.retry_after = retry_after
        #: The parsed response body.
        self.body = body

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status!r}, code={self.code!r}, message={self.message!r})"


class BadRequestError(YativoError):
    """400"""


class AuthenticationError(YativoError):
    """401: missing, invalid or revoked API key."""


class PermissionDeniedError(YativoError):
    """403: IP not whitelisted, feature not enabled, or endpoint not allowed with an API key."""


class NotFoundError(YativoError):
    """404"""


class ConflictError(YativoError):
    """409: idempotency conflict or duplicate reference."""


class ValidationError(YativoError):
    """422"""


class RateLimitError(YativoError):
    """429"""


class APIError(YativoError):
    """5xx"""


class APIConnectionError(YativoError):
    """The request never got an answer: network failure or timeout."""


class SignatureVerificationError(YativoError):
    """A webhook's ``Signature`` header didn't match its body."""


_BY_STATUS = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def _first_message(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and value:
        return _first_message(value[0])
    if isinstance(value, dict):
        for v in value.values():
            m = _first_message(v)
            if m:
                return m
    return None


def error_from_response(status: int, body: Any, retry_after_header: Optional[str] = None) -> YativoError:
    env = body if isinstance(body, dict) else {}
    details = env.get("error_details") if isinstance(env.get("error_details"), dict) else {}
    data = env.get("data") if isinstance(env.get("data"), dict) else {}
    code = data.get("code") if isinstance(data.get("code"), str) else details.get("code")
    message = (
        (data.get("error") if isinstance(data.get("error"), str) else None)
        or details.get("message")
        or _first_message(data.get("error") or data.get("errors"))
        or (env.get("message") if isinstance(env.get("message"), str) else None)
        or f"Request failed with status {status}"
    )
    fields = details.get("fields") or data.get("errors") or {}
    retry_after = details.get("retry_after")
    if retry_after is None and retry_after_header:
        try:
            retry_after = float(retry_after_header)
        except ValueError:
            retry_after = None
    cls = _BY_STATUS.get(status) or (APIError if status >= 500 else YativoError)
    return cls(
        message,
        status=status,
        code=code,
        fields=fields if isinstance(fields, dict) else {},
        retryable=bool(details.get("retryable", False)),
        retry_after=retry_after,
        body=body,
    )
