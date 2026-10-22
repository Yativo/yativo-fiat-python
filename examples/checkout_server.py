"""A complete payin flow using only the standard library: create a deposit,
send the payer to Yativo, and mark the order paid when the API confirms it.

    export YATIVO_API_KEY=... YATIVO_API_SECRET=... YATIVO_WEBHOOK_SECRET=... YATIVO_ENVIRONMENT=sandbox
    export GATEWAY_ID=22 CREDIT_CURRENCY=USD PUBLIC_URL=https://your-tunnel.example
    python examples/checkout_server.py

Open http://localhost:3000/pay?order=1001&amount=250 to start a payment.
Register PUBLIC_URL + /webhooks/yativo as your webhook URL (yativo.webhook_endpoints.create).
"""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from yativo_fiat import Yativo, WebhookHandler

yativo = Yativo()
PORT = int(os.environ.get("PORT", "3000"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", f"http://localhost:{PORT}")

orders = {}        # a stand-in for your database: order_id -> {...}
processed = set()  # webhook deliveries already handled
webhooks = WebhookHandler(os.environ.get("YATIVO_WEBHOOK_SECRET", ""))


def confirm(deposit_id):
    deposit = yativo.deposits.retrieve(deposit_id)  # the API is the source of truth
    for order_id, order in orders.items():
        if order["deposit_id"] == deposit["id"] and deposit["status"] == "success" and order["status"] != "paid":
            order["status"] = "paid"
            print(f"Order {order_id} is paid")
    return deposit


@webhooks.on("deposit.*")
def on_deposit(event):
    if event.key in processed:  # the same event can arrive twice
        return
    deposit = confirm(event.payload["id"])
    # Only remember it once the deposit is final, so a later delivery is still checked.
    if deposit["status"] in ("success", "failed", "cancelled", "expired"):
        processed.add(event.key)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body="", headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        if self.path != "/webhooks/yativo":
            return self.send(404, "Not found\n")
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        # 200 when handled, 401 for a bad signature, 500 if a listener failed (Yativo retries)
        status = webhooks.respond(raw, dict(self.headers))
        self.send(status, "ok\n" if status == 200 else "error\n")

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == "/pay":
                order_id = query.get("order", [str(int(time.time()))])[0]
                amount = float(query.get("amount", ["100"])[0])
                created = yativo.deposits.create(
                    gateway=int(os.environ.get("GATEWAY_ID", "22")),
                    amount=amount,
                    currency=os.environ.get("CREDIT_CURRENCY", "USD"),
                    redirect_url=f"{PUBLIC_URL}/orders/{order_id}",
                    idempotency_key=f"order-{order_id}",  # retrying never creates a second deposit
                )
                orders[order_id] = {"amount": amount, "deposit_id": created["deposit_data"]["id"], "status": "pending"}
                return self.send(303, headers={"Location": created["deposit_url"]})
            if url.path.startswith("/orders/") and url.path[8:] in orders:
                order = orders[url.path[8:]]
                if order["status"] != "paid":
                    confirm(order["deposit_id"])  # never trust the redirect alone
                return self.send(200, f"Order {url.path[8:]}: {order['status']}\n")
            return self.send(404, "Not found\n")
        except Exception as exc:
            print("error:", exc)
            return self.send(500, "Something went wrong\n")


if __name__ == "__main__":
    print(f"Listening on http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
