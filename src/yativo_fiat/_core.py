"""HTTP plumbing shared by the client and the generated resources."""

import json
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Protocol, Tuple

from .errors import APIConnectionError, error_from_response

#: (method, url, headers, body, timeout) -> (status, headers, body)
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], Tuple[int, Mapping[str, str], bytes]]

RETRY_STATUSES = {429, 500, 502, 503, 504}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PROTECTED_HEADERS = {"x-api-key", "x-api-secret", "authorization", "idempotency-key"}


def quote_path(value: Any) -> str:
    """Encode a path parameter so it can't change the URL path."""
    return urllib.parse.quote(str(value), safe="")


def build_query(query: Optional[Mapping[str, Any]]) -> str:
    if not query:
        return ""
    pairs: List[Tuple[str, str]] = []
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            pairs.extend((f"{key}[]", str(v)) for v in value)
        elif isinstance(value, bool):
            pairs.append((key, "1" if value else "0"))
        else:
            pairs.append((key, str(value)))
    return "?" + urllib.parse.urlencode(pairs) if pairs else ""


def urllib_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes], timeout: float):
    """Default transport: urllib with certificate verification on."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as resp:  # noqa: S310 (https enforced)
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as err:  # 4xx/5xx still carry a JSON body
        return err.code, dict(err.headers.items()) if err.headers else {}, err.read()


@dataclass
class Page:
    """One page of a list. Iterate it to get the items."""

    data: List[Any] = field(default_factory=list)
    pagination: Optional[Dict[str, Any]] = None

    def __iter__(self) -> Iterator[Any]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    @property
    def has_more(self) -> bool:
        p = self.pagination or {}
        return bool(self.data) and int(p.get("current_page", 1)) < int(p.get("last_page", 1))


class Requester(Protocol):
    def request_data(self, method: str, path: str, **kwargs: Any) -> Any: ...

    def request_page(self, method: str, path: str, **kwargs: Any) -> Page: ...


class HttpClient:
    """Sends requests with your API key, retries safely and decodes the envelope."""

    def __init__(self, *, base_url: str, api_key: str, api_secret: str, timeout: float, max_retries: int,
                 transport: Transport, user_agent: str) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport
        self._user_agent = user_agent
        # Credentials live only inside this closure, never as attributes, so
        # they can't leak through vars(), repr(), pickling or error reports.
        def auth_headers() -> Dict[str, str]:
            return {"X-Api-Key": api_key, "X-Api-Secret": api_secret}

        self._auth_headers = auth_headers
        self.masked_api_key = f"{api_key[:10]}…{api_key[-4:]}" if len(api_key) > 14 else "[redacted]"

    def __repr__(self) -> str:
        return f"HttpClient(base_url={self.base_url!r}, api_key={self.masked_api_key!r})"

    def __getstate__(self) -> None:
        raise TypeError("The Yativo client can't be pickled: it holds your API credentials.")

    def request(self, method: str, path: str, *, query: Optional[Mapping[str, Any]] = None,
                body: Optional[Mapping[str, Any]] = None, idempotency_key: Optional[str] = None,
                timeout: Optional[float] = None, max_retries: Optional[int] = None,
                headers: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        """Call any endpoint. Returns the full response envelope."""
        verb = method.upper()
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}{build_query(query)}"
        send: Dict[str, str] = {"Accept": "application/json", "User-Agent": self._user_agent}
        for k, v in (headers or {}).items():
            if k.lower() not in PROTECTED_HEADERS:
                send[k] = v
        send.update(self._auth_headers())
        if verb in WRITE_METHODS:
            send["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
        payload = None
        if body is not None and verb != "GET":
            send["Content-Type"] = "application/json"
            payload = json.dumps(body, default=str).encode("utf-8")

        retries = self.max_retries if max_retries is None else max_retries
        wait = self.timeout if timeout is None else timeout
        attempt = 0
        while True:
            try:
                status, resp_headers, raw = self._transport(verb, url, send, payload, wait)
            except Exception as exc:  # network error or timeout
                if attempt < retries:
                    time.sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise APIConnectionError(f"Could not reach the Yativo API: {type(exc).__name__}") from exc

            try:
                decoded = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                decoded = {"status": "failed", "message": "The API returned a response that is not JSON."}

            failed = status >= 400 or (isinstance(decoded, dict) and decoded.get("status") == "failed")
            if not failed:
                return decoded if isinstance(decoded, dict) else {"data": decoded}

            lower = {k.lower(): v for k, v in (resp_headers or {}).items()}
            if status in RETRY_STATUSES and attempt < retries:
                time.sleep(self._retry_delay(lower.get("retry-after"), attempt))
                attempt += 1
                continue
            code = status if status >= 400 else int(decoded.get("status_code") or 400)
            raise error_from_response(code, decoded, lower.get("retry-after"))

    def request_data(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.request(method, path, **kwargs).get("data")

    def request_page(self, method: str, path: str, **kwargs: Any) -> Page:
        env = self.request(method, path, **kwargs)
        raw = env.get("data")
        if isinstance(raw, list):
            return Page(raw, env.get("pagination"))
        if isinstance(raw, dict) and isinstance(raw.get("data"), list):
            return Page(raw["data"], env.get("pagination") or raw.get("pagination"))
        return Page([], env.get("pagination"))

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(8.0, 0.5 * (2 ** attempt)) + random.random() * 0.25

    def _retry_delay(self, header: Optional[str], attempt: int) -> float:
        try:
            seconds = float(header) if header else 0
        except ValueError:
            seconds = 0
        return min(seconds, 30.0) if seconds > 0 else self._backoff(attempt)
