import os
import platform
from typing import Any, Callable, Dict, Iterator, Mapping, Optional
from urllib.parse import urlparse

from ._core import HttpClient, Page, Transport, urllib_transport
from ._version import __version__
from .errors import YativoError
from .resources import RESOURCE_CLASSES
from .webhooks import WebhookHandler

ENVIRONMENTS = {
    "production": "https://api.yativo.com/api/v1",
    "sandbox": "https://smtp.yativo.com/api/v1",
}


def _resolve_base_url(environment: Optional[str], base_url: Optional[str]) -> str:
    env = environment or os.environ.get("YATIVO_ENVIRONMENT") or "production"
    url = base_url or os.environ.get("YATIVO_BASE_URL") or ENVIRONMENTS.get(env)
    if not url:
        raise YativoError(f'Unknown environment "{env}". Use "production" or "sandbox".')
    parsed = urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise YativoError("base_url must use https. Your API key would be sent unencrypted otherwise.")
    return url.rstrip("/")


class Yativo:
    """Yativo Fiat API client.

    .. code-block:: python

        from yativo_fiat import Yativo

        yativo = Yativo()  # reads YATIVO_API_KEY and YATIVO_API_SECRET
        balances = yativo.wallets.balance()
    """

    customers: Any
    kyc: Any
    lookups: Any
    payment_methods: Any
    rates: Any
    deposits: Any
    card_checkout: Any
    virtual_accounts: Any
    wallets: Any
    beneficiaries: Any
    payouts: Any
    send_money: Any
    swaps: Any
    transactions: Any
    virtual_cards: Any
    crypto: Any
    corporate_cards: Any
    webhook_endpoints: Any
    events: Any
    ip_whitelist: Any
    sandbox: Any

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        environment: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        webhook_secret: Optional[str] = None,
        transport: Optional[Transport] = None,
    ) -> None:
        key = api_key or os.environ.get("YATIVO_API_KEY")
        secret = api_secret or os.environ.get("YATIVO_API_SECRET")
        if not key or not secret:
            raise YativoError("Pass api_key and api_secret, or set YATIVO_API_KEY and YATIVO_API_SECRET.")
        self._http = HttpClient(
            base_url=_resolve_base_url(environment, base_url),
            api_key=key,
            api_secret=secret,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport or urllib_transport,
            user_agent=f"yativo-fiat-python/{__version__} python/{platform.python_version()}",
        )
        #: Verify and route webhooks (uses webhook_secret or YATIVO_WEBHOOK_SECRET).
        self.webhooks = WebhookHandler(webhook_secret or os.environ.get("YATIVO_WEBHOOK_SECRET", ""))
        for name, cls in RESOURCE_CLASSES.items():
            setattr(self, name, cls(self._http))

    @property
    def base_url(self) -> str:
        return self._http.base_url

    def request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        """Call any endpoint, including ones the SDK doesn't wrap yet. Returns the full envelope.

        Keyword arguments: query, body, idempotency_key, timeout, max_retries, headers.
        """
        return self._http.request(method, path, **kwargs)

    def paginate(self, list_method: Callable[..., Page], params: Optional[Mapping[str, Any]] = None,
                 **kwargs: Any) -> Iterator[Any]:
        """Walk every page of a list: ``for d in yativo.paginate(yativo.deposits.list, per_page=100)``."""
        query = {**(params or {}), **kwargs}
        page = int(query.pop("page", 1))
        while True:
            result = list_method({**query, "page": page})
            yield from result.data
            if not result.has_more:
                return
            page = int((result.pagination or {}).get("current_page", page)) + 1

    def __repr__(self) -> str:
        return f"Yativo(base_url={self.base_url!r}, api_key={self._http.masked_api_key!r})"
