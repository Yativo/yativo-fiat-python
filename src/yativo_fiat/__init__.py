"""Official Python SDK for the Yativo Fiat API."""

from ._client import ENVIRONMENTS, Yativo
from ._core import Page
from ._version import __version__
from .errors import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SignatureVerificationError,
    ValidationError,
    YativoError,
)
from .webhooks import (
    SIGNATURE_HEADER,
    EventType,
    WebhookEvent,
    WebhookHandler,
    compute_signature,
    construct_event,
    verify_signature,
)

__all__ = [
    "Yativo", "ENVIRONMENTS", "Page", "__version__",
    "YativoError", "BadRequestError", "AuthenticationError", "PermissionDeniedError", "NotFoundError",
    "ConflictError", "ValidationError", "RateLimitError", "APIError", "APIConnectionError",
    "SignatureVerificationError",
    "WebhookHandler", "WebhookEvent", "EventType", "SIGNATURE_HEADER",
    "compute_signature", "verify_signature", "construct_event",
]
