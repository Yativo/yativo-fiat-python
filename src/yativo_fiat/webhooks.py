"""Verify and route Yativo webhooks.

Every delivery is a POST with a JSON body and a ``Signature`` header:
``hex(HMAC-SHA256(raw_body, webhook_secret))``. Always verify the raw body,
before parsing it.
"""

import fnmatch
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from .errors import SignatureVerificationError, YativoError

logger = logging.getLogger("yativo_fiat")

SIGNATURE_HEADER = "Signature"
TIMESTAMP_HEADER = "Timestamp"  # Unix seconds. Not part of the signature.

RawBody = Union[bytes, bytearray, memoryview, str]


class EventType:
    """Event types you are likely to handle. New types are added over time; ignore unknown ones."""

    DEPOSIT_CREATED = "deposit.created"
    DEPOSIT_UPDATED = "deposit.updated"
    PAYOUT_UPDATED = "payout.updated"
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    ENDORSEMENT_UPDATED = "endorsement.updated"
    VIRTUAL_ACCOUNT_CREATED = "virtual_account.created"
    VIRTUAL_ACCOUNT_UPDATED = "virtual_account.updated"
    VIRTUAL_ACCOUNT_DELETED = "virtual_account.deleted"
    VIRTUAL_ACCOUNT_DEPOSIT = "virtual_account.deposit"
    CRYPTO_WALLET_CREATED = "crypto.wallet.created"
    CRYPTO_DEPOSIT_COMPLETED = "crypto.deposit.completed"
    CRYPTO_DEPOSIT_LEGACY = "crypto_deposit"
    WALLET_DELETED = "wallet.deleted"
    CARD_CHECKOUT_ORDER_CREATED = "card_checkout.order.created"
    CARD_CHECKOUT_ORDER_REQUIRES_ACTION = "card_checkout.order.requires_action"
    CARD_CHECKOUT_ORDER_PROCESSING = "card_checkout.order.processing"
    CARD_CHECKOUT_ORDER_PAID = "card_checkout.order.paid"
    CARD_CHECKOUT_ORDER_PAYMENT_FAILED = "card_checkout.order.payment_failed"
    CARD_CHECKOUT_ORDER_UNDER_REVIEW = "card_checkout.order.under_review"
    CARD_CHECKOUT_ORDER_PARTIALLY_REFUNDED = "card_checkout.order.partially_refunded"
    CARD_CHECKOUT_ORDER_REFUNDED = "card_checkout.order.refunded"
    CARD_CHECKOUT_ORDER_DISPUTED = "card_checkout.order.disputed"
    CARD_CHECKOUT_ORDER_EXPIRED = "card_checkout.order.expired"
    METADATA_CREATED = "metadata.created"
    METADATA_UPDATED = "metadata.updated"
    TRACKING_CREATED = "tracking.created"
    USER_UPDATED = "user.updated"
    WEBHOOK_UPDATED = "webhook_updated"
    PAYIN_METHOD_ENABLED = "payin_method.enabled"
    PAYIN_METHOD_DISABLED = "payin_method.disabled"
    PAYOUT_METHOD_ENABLED = "payout_method.enabled"
    PAYOUT_METHOD_DISABLED = "payout_method.disabled"


@dataclass
class WebhookEvent:
    #: The ``event.type`` value, e.g. ``deposit.updated``.
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    #: The decoded body exactly as sent.
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """A key for deduplicating deliveries: store it and skip events you've seen."""
        p = self.payload
        if p.get("event_id"):
            return f"{self.type}:{p['event_id']}"
        ident = p.get("id") or p.get("transaction_id") or p.get("deposit_id") or p.get("payout_id") \
            or p.get("account_id") or p.get("customer_id") or ""
        return f"{self.type}:{ident}:{p.get('status') or p.get('updated_at') or ''}"


def _to_bytes(body: RawBody) -> bytes:
    if isinstance(body, str):
        return body.encode("utf-8")
    if isinstance(body, (bytes, bytearray, memoryview)):
        return bytes(body)
    raise YativoError("Pass the raw request body (bytes or str), not a parsed object.")


def compute_signature(raw_body: RawBody, secret: str) -> str:
    """The value Yativo puts in the ``Signature`` header."""
    return hmac.new(secret.encode("utf-8"), _to_bytes(raw_body), hashlib.sha256).hexdigest()


def verify_signature(raw_body: RawBody, signature: Optional[str], secret: str) -> bool:
    """Constant-time check of a ``Signature`` header against the raw body."""
    if not secret or not signature:
        return False
    return hmac.compare_digest(compute_signature(raw_body, secret), str(signature).strip().lower())


def get_header(headers: Mapping[str, Any], name: str) -> Optional[str]:
    lower = name.lower()
    for k, v in headers.items():
        if str(k).lower() == lower or str(k).upper() == "HTTP_" + name.upper():
            return v[0] if isinstance(v, (list, tuple)) else v
    return None


def construct_event(raw_body: RawBody, signature: Optional[str], secret: str) -> WebhookEvent:
    """Verify a delivery and decode it. Raises SignatureVerificationError on a mismatch."""
    if not secret:
        raise YativoError("Webhook secret is not set. Pass webhook_secret or set YATIVO_WEBHOOK_SECRET.")
    body = _to_bytes(raw_body)
    if not verify_signature(body, signature, secret):
        raise SignatureVerificationError("Webhook signature does not match.", status=401)
    try:
        raw = json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise SignatureVerificationError("Webhook body is not valid JSON.", status=400) from exc
    event_type = str(raw.get("event.type") or raw.get("event") or raw.get("type") or "")
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    return WebhookEvent(type=event_type, payload=payload, raw=raw)


Listener = Callable[[WebhookEvent], Any]


class WebhookHandler:
    """Verify deliveries and route them to listeners by event type.

    .. code-block:: python

        handler = WebhookHandler(os.environ["YATIVO_WEBHOOK_SECRET"])

        @handler.on("deposit.updated")
        def deposit(event):
            ...

    Yativo waits 3 seconds for an answer, so keep listeners fast: store or
    queue the event and do slow work in the background.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret
        self._listeners: Dict[str, List[Listener]] = {}

    def __repr__(self) -> str:
        return f"WebhookHandler(listeners={sorted(self._listeners)})"

    def on(self, event_type: str, listener: Optional[Listener] = None):
        """Register a listener for a type, a pattern such as ``virtualcard.*``, or ``*``.

        Use as ``handler.on("deposit.updated", fn)`` or as a decorator.
        """
        def register(fn: Listener) -> Listener:
            self._listeners.setdefault(event_type, []).append(fn)
            return fn

        return register(listener) if listener else register

    def handle(self, raw_body: RawBody, headers_or_signature: Union[Mapping[str, Any], str, None]) -> WebhookEvent:
        """Verify, decode and run the matching listeners."""
        if isinstance(headers_or_signature, str) or headers_or_signature is None:
            signature = headers_or_signature
        else:
            signature = get_header(headers_or_signature, SIGNATURE_HEADER)
        event = construct_event(raw_body, signature, self._secret)
        for pattern, listeners in self._listeners.items():
            if pattern == "*" or pattern == event.type or fnmatch.fnmatchcase(event.type, pattern):
                for fn in listeners:
                    fn(event)
        return event

    def respond(self, raw_body: RawBody, headers: Mapping[str, Any]) -> int:
        """Like handle(), but returns the HTTP status to answer with.

        200 when listeners succeed, 401 for a bad signature, and 500 when a
        listener raises, so Yativo delivers the event again later.
        """
        try:
            self.handle(raw_body, headers)
            return 200
        except SignatureVerificationError:
            return 401
        except Exception:  # noqa: BLE001 - any listener failure means "retry later"
            logger.exception("Yativo webhook listener failed")
            return 500

    # -------- framework helpers --------------------------------------------
    def flask_view(self):
        """A Flask view: ``app.add_url_rule('/webhooks/yativo', view_func=handler.flask_view(), methods=['POST'])``."""
        def view():
            from flask import request  # imported lazily so Flask stays optional
            return ("ok", self.respond(request.get_data(), request.headers))

        view.__name__ = "yativo_webhook"
        return view

    def django_view(self):
        """A Django view (CSRF-exempt): ``path('webhooks/yativo', handler.django_view())``."""
        from django.http import HttpResponse
        from django.views.decorators.csrf import csrf_exempt
        from django.views.decorators.http import require_POST

        @csrf_exempt
        @require_POST
        def view(request):
            return HttpResponse("ok", status=self.respond(request.body, request.headers))

        return view

    def fastapi_route(self):
        """A FastAPI/Starlette endpoint: ``app.post('/webhooks/yativo')(handler.fastapi_route())``."""
        from starlette.requests import Request
        from starlette.responses import PlainTextResponse

        async def endpoint(request: Request):
            body = await request.body()
            return PlainTextResponse("ok", status_code=self.respond(body, request.headers))

        return endpoint
