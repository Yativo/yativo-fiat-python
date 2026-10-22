import hashlib
import hmac
import json
import os
import pickle
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from yativo_fiat import (
    APIConnectionError, AuthenticationError, NotFoundError, Page, SignatureVerificationError,
    ValidationError, WebhookHandler, Yativo, YativoError, construct_event, verify_signature,
)

KEY = "yativo_pk_test_0000000000000000"
SECRET = "yativo_sk_test_1111111111111111"


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        status, payload = nxt[0], nxt[1]
        headers = nxt[2] if len(nxt) > 2 else {}
        return status, headers, json.dumps(payload).encode()


def ok(data, **extra):
    return (200, {"status": "success", "status_code": 200, "message": "Request successful", "data": data, **extra})


def client(transport, **kw):
    return Yativo(KEY, SECRET, transport=transport, **kw)


class ClientTests(unittest.TestCase):
    def test_auth_headers_and_url(self):
        t = FakeTransport(ok({"balance": 1}))
        self.assertEqual(client(t).wallets.balance(), {"balance": 1})
        call = t.calls[0]
        self.assertEqual(call["url"], "https://api.yativo.com/api/v1/wallet/balance")
        self.assertEqual(call["headers"]["X-Api-Key"], KEY)
        self.assertEqual(call["headers"]["X-Api-Secret"], SECRET)
        self.assertNotIn("Authorization", call["headers"])
        self.assertNotIn("Idempotency-Key", call["headers"])

    def test_sandbox(self):
        t = FakeTransport(ok({}))
        client(t, environment="sandbox").ip_whitelist.check()
        self.assertTrue(t.calls[0]["url"].startswith("https://smtp.yativo.com/api/v1/"))

    def test_body_kwargs_and_idempotency(self):
        t = FakeTransport(ok({"deposit_url": "x"}), ok({}))
        y = client(t)
        y.deposits.create({"gateway": 22}, amount=100, currency="CLP")
        first = t.calls[0]
        self.assertEqual(json.loads(first["body"]), {"gateway": 22, "amount": 100, "currency": "CLP"})
        self.assertEqual(len(first["headers"]["Idempotency-Key"]), 36)
        y.deposits.create(gateway=1, idempotency_key="order-42")
        self.assertEqual(t.calls[1]["headers"]["Idempotency-Key"], "order-42")

    def test_path_params_encoded(self):
        t = FakeTransport(ok({}))
        client(t).deposits.retrieve("a/b?c")
        self.assertTrue(t.calls[0]["url"].endswith("/wallet/deposits/a%2Fb%3Fc"))

    def test_query_encoding(self):
        t = FakeTransport(ok([]))
        client(t).payment_methods.payin(country="CHL", currency="CLP", skip=None, flag=True)
        self.assertTrue(t.calls[0]["url"].endswith("/payment-methods/payin?country=CHL&currency=CLP&flag=1"))

    def test_protected_headers(self):
        t = FakeTransport(ok({}))
        client(t).request("GET", "/wallet/balance", headers={"X-Api-Key": "evil", "X-Trace": "1"})
        self.assertEqual(t.calls[0]["headers"]["X-Api-Key"], KEY)
        self.assertEqual(t.calls[0]["headers"]["X-Trace"], "1")

    def test_pages_and_paginate(self):
        def page(n, items):
            return ok(items, pagination={"total": 3, "per_page": 2, "current_page": n, "last_page": 2})
        t = FakeTransport(page(1, [{"id": 1}, {"id": 2}]), page(2, [{"id": 3}]))
        y = client(t)
        ids = [d["id"] for d in y.paginate(y.deposits.list, per_page=2)]
        self.assertEqual(ids, [1, 2, 3])
        self.assertIn("page=2", t.calls[1]["url"])

    def test_list_returns_page(self):
        t = FakeTransport(ok([{"id": 1}], pagination={"current_page": 1, "last_page": 1}))
        result = client(t).customers.list()
        self.assertIsInstance(result, Page)
        self.assertEqual(len(result), 1)
        self.assertFalse(result.has_more)

    def test_retry_same_key(self):
        t = FakeTransport((503, {"status": "failed", "data": {}}), ok({"id": "p1"}))
        y = Yativo(KEY, SECRET, transport=t, max_retries=2)
        self.assertEqual(y.payouts.create(amount=1)["id"], "p1")
        self.assertEqual(t.calls[0]["headers"]["Idempotency-Key"], t.calls[1]["headers"]["Idempotency-Key"])

    def test_no_retry_on_404(self):
        t = FakeTransport((404, {"status": "failed", "status_code": 404, "data": {"error": "Deposit not found"}}))
        with self.assertRaises(NotFoundError) as ctx:
            client(t).deposits.retrieve("nope")
        self.assertEqual(ctx.exception.message, "Deposit not found")
        self.assertEqual(len(t.calls), 1)

    def test_validation_error(self):
        body = {"status": "failed", "status_code": 422, "data": {"customer_email": ["required"]},
                "error_details": {"code": "validation_error", "message": "required", "fields": {"customer_email": ["required"]}}}
        t = FakeTransport((422, body))
        with self.assertRaises(ValidationError) as ctx:
            client(t).customers.create()
        self.assertEqual(ctx.exception.code, "validation_error")
        self.assertIn("customer_email", ctx.exception.fields)

    def test_feature_code(self):
        t = FakeTransport((409, {"status": "failed", "data": {"error": "used", "code": "duplicate_reference"}}))
        with self.assertRaises(YativoError) as ctx:
            client(t).card_checkout.create_order(amount="1.00")
        self.assertEqual(ctx.exception.code, "duplicate_reference")

    def test_200_failed_is_error(self):
        t = FakeTransport((200, {"status": "failed", "status_code": 401, "data": {"error": "Invalid or revoked API credentials."}}))
        with self.assertRaises(AuthenticationError):
            client(t).wallets.balance()

    def test_connection_error(self):
        t = FakeTransport(OSError("down"), OSError("down"))
        with self.assertRaises(APIConnectionError):
            Yativo(KEY, SECRET, transport=t, max_retries=1).wallets.balance()
        self.assertEqual(len(t.calls), 2)

    def test_secrets_never_exposed(self):
        y = client(FakeTransport())
        self.assertNotIn(SECRET, repr(y))
        self.assertNotIn(SECRET, repr(vars(y)))
        self.assertNotIn(SECRET, repr(vars(y._http)))
        with self.assertRaises(TypeError):
            pickle.dumps(y)

    def test_refuses_http_and_missing_credentials(self):
        with self.assertRaises(YativoError):
            Yativo(KEY, SECRET, base_url="http://api.example.com")
        Yativo(KEY, SECRET, base_url="http://localhost:8000/api/v1")
        saved = os.environ.pop("YATIVO_API_KEY", None), os.environ.pop("YATIVO_API_SECRET", None)
        try:
            with self.assertRaises(YativoError):
                Yativo()
        finally:
            for k, v in zip(("YATIVO_API_KEY", "YATIVO_API_SECRET"), saved):
                if v is not None:
                    os.environ[k] = v

    def test_real_http_round_trip(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["key"] = self.headers.get("X-Api-Key")
                seen["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                out = json.dumps({"status": "failed", "status_code": 404, "data": {"error": "Deposit not found"}}).encode()
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            y = Yativo(KEY, SECRET, base_url=f"http://localhost:{server.server_port}/api/v1", max_retries=0)
            with self.assertRaises(NotFoundError):
                y.request("POST", "/x", body={"a": 1})
        finally:
            server.shutdown()
        self.assertEqual(seen["key"], KEY)
        self.assertEqual(json.loads(seen["body"]), {"a": 1})


WH_SECRET = "aZ3kP9mQw2Ry7Ln5Xj1Vb8Ct4Fh6Ds0G"
BODY = json.dumps({"event.type": "deposit.updated", "payload": {"id": "dep_1", "status": "success", "amount": 500}}).encode()
SIG = hmac.new(WH_SECRET.encode(), BODY, hashlib.sha256).hexdigest()


class WebhookTests(unittest.TestCase):
    def test_signature(self):
        self.assertTrue(verify_signature(BODY, SIG, WH_SECRET))
        self.assertTrue(verify_signature(BODY.decode(), SIG.upper(), WH_SECRET))
        self.assertFalse(verify_signature(BODY, SIG, "wrong"))
        self.assertFalse(verify_signature(BODY + b" ", SIG, WH_SECRET))
        self.assertFalse(verify_signature(BODY, None, WH_SECRET))

    def test_construct_event(self):
        event = construct_event(BODY, SIG, WH_SECRET)
        self.assertEqual(event.type, "deposit.updated")
        self.assertEqual(event.payload["id"], "dep_1")
        self.assertEqual(event.key, "deposit.updated:dep_1:success")
        with self.assertRaises(SignatureVerificationError):
            construct_event(BODY.replace(b"500", b"5000"), SIG, WH_SECRET)
        with self.assertRaises(YativoError):
            construct_event(json.loads(BODY), SIG, WH_SECRET)

    def test_routing(self):
        seen = []
        handler = WebhookHandler(WH_SECRET)
        handler.on("deposit.updated", lambda e: seen.append("exact"))

        @handler.on("deposit.*")
        def prefix(e):
            seen.append("prefix")

        handler.on("*", lambda e: seen.append("all"))
        handler.on("payout.updated", lambda e: seen.append("wrong"))
        handler.handle(BODY, {"signature": SIG})
        self.assertEqual(seen, ["exact", "prefix", "all"])

    def test_respond_and_django_style_headers(self):
        handler = WebhookHandler(WH_SECRET)
        self.assertEqual(handler.respond(BODY, {"HTTP_SIGNATURE": SIG}), 200)
        self.assertEqual(handler.respond(BODY, {"Signature": "bad"}), 401)

    def test_failing_listener_answers_500(self):
        handler = WebhookHandler(WH_SECRET)

        def boom(event):
            raise RuntimeError("db down")

        handler.on("*", boom)
        with self.assertLogs("yativo_fiat", level="ERROR"):
            self.assertEqual(handler.respond(BODY, {"Signature": SIG}), 500)


if __name__ == "__main__":
    unittest.main()
