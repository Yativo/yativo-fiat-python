# Yativo Fiat SDK for Python

[![CI](https://github.com/Yativo/yativo-fiat-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Yativo/yativo-fiat-python/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

The official Python library for the [Yativo Fiat API](https://docs.yativo.com). Collect payments from customers, send money to people and businesses, give customers bank accounts and cards, and get notified when anything changes.

**You don't need to be a payments expert.** This page walks you through everything, step by step.

- Package: `yativo-fiat-sdk` (you import it as `yativo_fiat`)
- Works with: Python 3.8 or newer
- Guide for every language: [https://yativo.github.io/yativo-sdks/](https://yativo.github.io/yativo-sdks/)
- Every method: [docs/REFERENCE.md](docs/REFERENCE.md)

## Contents

1. [What you need](#what-you-need)
2. [Step 1: Install](#step-1-install)
3. [Step 2: Add your keys](#step-2-add-your-keys)
4. [Step 3: Your first request](#step-3-your-first-request)
5. [Step 4: Accept a payment](#step-4-accept-a-payment)
6. [Step 5: Get notified (webhooks)](#step-5-get-notified-webhooks)
7. [Card payments](#card-payments)
8. [Send money (payouts)](#send-money-payouts)
9. [Everyday tasks](#everyday-tasks)
10. [When something goes wrong](#when-something-goes-wrong)
11. [Lists with many pages](#lists-with-many-pages)
12. [Settings](#settings)
13. [Test safely in the sandbox](#test-safely-in-the-sandbox)
14. [Troubleshooting](#troubleshooting)
15. [FAQ](#faq)
16. [Examples, tests and contributing](#examples-tests-and-contributing)

## What you need

- [ ] **A Yativo account** with your business verification approved. Sign up at [app.yativo.com](https://app.yativo.com).
- [ ] **An API key.** In the dashboard, open **Developers → API Keys** and click **Generate key**. You get two values:
  - the **API key**, which starts with `yativo_pk_`
  - the **API secret**, which starts with `yativo_sk_`. It's shown **once**, so copy it somewhere safe straight away.
- [ ] **Your server's IP address** added to the key. Yativo refuses requests from anywhere else. Run `curl https://checkip.amazonaws.com` on the server to find it.
- [ ] **Python 3.8 or newer**. Check with `python3 --version`. Get it from [https://www.python.org/downloads/](https://www.python.org/downloads/).

> Start with the **sandbox**: it has its own keys and no real money moves. Switch to production when everything works.

## Step 1: Install

```bash
pip install yativo-fiat-sdk

# inside a virtual environment (recommended):
python3 -m venv .venv && . .venv/bin/activate && pip install yativo-fiat-sdk
```

## Step 2: Add your keys

Never put keys in your code. Put them in environment variables. The easiest way is a file called `.env` next to your code:

```dotenv
YATIVO_API_KEY=yativo_pk_your_key_here
YATIVO_API_SECRET=yativo_sk_your_secret_here
YATIVO_ENVIRONMENT=sandbox
```

Export the variables in your shell (`set -a; . ./.env; set +a`), or load the file with [python-dotenv](https://pypi.org/project/python-dotenv/) before creating the client.

> Add `.env` to your `.gitignore` so it's never committed. Anyone with your secret can use your account.

The SDK reads these variables automatically. You can also pass them yourself:

```python
yativo = Yativo(
    api_key=os.environ["YATIVO_API_KEY"],
    api_secret=os.environ["YATIVO_API_SECRET"],
    environment="sandbox",  # or "production"
)
```

## Step 3: Your first request

Create `first_request.py`:

```python
from yativo_fiat import Yativo

# Reads YATIVO_API_KEY, YATIVO_API_SECRET and YATIVO_ENVIRONMENT from the environment.
yativo = Yativo()

check = yativo.ip_whitelist.check()
print("Key check:", check["result"])  # "pass" means you're good to go

print("Balances:", yativo.wallets.balance())
```

Run it:

```bash
set -a; . ./.env; set +a
python3 first_request.py
```

You should see `Key check: pass` and your balances. If you see an error instead, look it up in [Troubleshooting](#troubleshooting).

## Step 4: Accept a payment

A **deposit** is a payment from your customer. Yativo gives you a payment page; you send the customer there, they pay with their bank or local method, and you get the money in your wallet.

```
 Your site               Yativo                    Your customer
    │  1. create deposit    │                            │
    │──────────────────────▶│                            │
    │  ◀── deposit_url ─────│                            │
    │  2. redirect ─────────────────────────────────────▶│
    │                       │◀──── 3. pays ──────────────│
    │◀── 4. webhook: deposit.updated                     │
    │  5. check the deposit │                            │
    │──────────────────────▶│  status: success → ship it │
```

**1. Find a payment method** for your customer's country (3-letter code) and currency:

```python
methods = yativo.payment_methods.payin(country="BRA", currency="BRL")
print(methods)  # [{"id": 22, "method_name": "Bank Transfer", "currency": "BRL", "base_currency": "USD"}, ...]
```

**2. Create the deposit** and send your customer to the payment page:

```python
created = yativo.deposits.create(
    gateway=22,             # the payment method id from step 1
    amount=250,             # how much the customer pays, in the method's currency (BRL here)
    currency="USD",         # which of your wallets gets the money (one of base_currency)
    redirect_url="https://your-shop.com/orders/1001",  # where the customer goes afterwards
    idempotency_key="order-1001",  # your order id: retrying never charges twice
)

# Save created["deposit_data"]["id"] with your order, then send the customer here:
print(created["deposit_url"])
```

**3. Confirm it.** When the customer comes back, or when you get a webhook (next step), ask Yativo for the deposit. Don't trust the customer's browser: a URL can be typed by hand.

```python
deposit = yativo.deposits.retrieve(saved_deposit_id)

if deposit["status"] == "success":
    ...  # the money arrived: ship the order
```

A deposit's `status` is `pending`, `processing`, `success`, `failed`, `cancelled` or `expired`.

## Step 5: Get notified (webhooks)

A **webhook** is a message Yativo sends to your server when something changes, for example when a payment succeeds. Each message is signed so you know it's really from Yativo. The SDK checks the signature for you.

**Register your URL once** (it must be public and use `https`):

```python
endpoint = yativo.webhook_endpoints.create(url="https://your-shop.com/webhooks/yativo")
print(endpoint["secret"])  # copy this into YATIVO_WEBHOOK_SECRET. Don't share it.
```

**Handle the messages:**

```python
import os
from flask import Flask
from yativo_fiat import Yativo, WebhookHandler

yativo = Yativo()
app = Flask(__name__)
webhooks = WebhookHandler(os.environ["YATIVO_WEBHOOK_SECRET"])

@webhooks.on("deposit.updated")
def deposit_updated(event):
    # Ask Yativo directly instead of trusting the message.
    deposit = yativo.deposits.retrieve(event.payload["id"])
    if deposit["status"] == "success":
        ...  # mark the order paid

@webhooks.on("payout.updated")
def payout_updated(event):
    print("Payout", event.payload["id"], "is now", event.payload["status"])

app.add_url_rule("/webhooks/yativo", view_func=webhooks.flask_view(), methods=["POST"])
```

Other setups:

```python
# Django (urls.py)
path("webhooks/yativo", webhooks.django_view())

# FastAPI / Starlette
app.post("/webhooks/yativo")(webhooks.fastapi_route())

# Anything else: give it the raw body bytes and the headers
status = webhooks.respond(raw_body, headers)  # 200, 401 (bad signature) or 500 (your code failed)
```

Good to know:

- Answer within **3 seconds**. Do slow work (emails, reports) in the background.
- The same message can arrive **more than once**. Skip ones you've already handled.
- If your code fails, the SDK answers `500` and Yativo **retries** later.
- Common events: `deposit.updated`, `payout.updated`, `virtual_account.deposit`, `customer.updated`, `endorsement.updated`, `card_checkout.order.paid`. The full list is in the [webhooks docs](https://docs.yativo.com/yativo-fiat/webhooks).

## Card payments

Card Checkout gives your buyer a secure page to pay by card, Apple Pay or Google Pay. Card numbers never touch your server. Your account needs Card Checkout access, and the selling customer needs an approved `card_checkout` endorsement.

```python
order = yativo.card_checkout.create_order(
    customer_id="your-selling-customer-id",  # must have an approved card_checkout endorsement
    amount="49.99",                          # a string with 2 decimals
    currency="USD",
    description="Pro plan, 1 month",
    reference="INV-10023",                   # your invoice number (must be unique)
    customer_email="buyer@example.com",
    success_url="https://your-shop.com/thanks",
    cancel_url="https://your-shop.com/cart",
    idempotency_key="INV-10023",
)

# Send the buyer to order["checkout_url"] exactly as it is (it's signed).
```

Only treat the order as paid after the `card_checkout.order.paid` webhook, confirmed with `cardCheckout.retrieveOrder`. The payment link works for 60 minutes.

## Send money (payouts)

```python
# 1. Which details does this payout method need? (account number, bank, ...)
form = yativo.payment_methods.payout_form(method_id)

# 2. Save the person you're paying
beneficiary = yativo.beneficiaries.create(
    gateway_id=method_id, currency="BRL", nickname="Supplier Ltda",
    payment_data={...},  # the fields from the form
)

# 3. Lock a rate
quote = yativo.rates.quote(from_currency="USD", to_currency="BRL", amount=500,
                           method_id=method_id, method_type="payout")

# 4. Send it
payout = yativo.payouts.create(
    debit_wallet="USD", payment_method_id=beneficiary["id"], quote_id=quote["quote_id"],
    idempotency_key="invoice-778",
)
```

You get `payout.updated` webhooks as it moves through `pending`, `processing` and `completed` (or `failed`).

## Everyday tasks

| I want to… | Code |
|---|---|
| See your balances | `yativo.wallets.balance()` |
| Create a customer | `yativo.customers.create(...)` |
| Look up a customer | `yativo.customers.retrieve(customer_id)` |
| Collect a payment | `yativo.deposits.create(gateway=..., amount=..., currency=...)` |
| Check a payment | `yativo.deposits.retrieve(deposit_id)` |
| List payments | `yativo.deposits.list(per_page=50)` |
| Give a customer a bank account | `yativo.virtual_accounts.create(customer_id=..., currency=...)` |
| Get an exchange rate | `yativo.rates.quote(from_currency=..., to_currency=..., amount=...)` |
| Pay someone | `yativo.payouts.create(debit_wallet=..., payment_method_id=..., amount=...)` |
| Card payment link | `yativo.card_checkout.create_order(...)` |
| Move money between your wallets | `yativo.swaps.create(...)` |
| See your transactions | `yativo.transactions.list()` |
| Resend a missed webhook | `yativo.events.resend(event_id)` |

Everything else in the API is covered too: see [docs/REFERENCE.md](docs/REFERENCE.md) for every method. For anything not wrapped yet:

```python
response = yativo.request("GET", "/some/new/endpoint", query={"page": 1})
```

## When something goes wrong

Every failure raises a clear error with the HTTP status, a short code, a readable message and, for form mistakes, the fields to fix.

```python
from yativo_fiat import ValidationError, YativoError

try:
    yativo.deposits.create(gateway=22, currency="USD")  # amount is missing
except ValidationError as err:
    print("Please fix:", err.fields)  # {"amount": ["The amount field is required."]}
except YativoError as err:
    print(err.status, err.code, err.message)  # e.g. 403 forbidden "This IP address is not allowed..." 
```

Error types: `BadRequestError` (400), `AuthenticationError` (401), `PermissionDeniedError` (403), `NotFoundError` (404), `ConflictError` (409), `ValidationError` (422), `RateLimitError` (429), `APIError` (5xx) and `APIConnectionError` (no answer). They all extend `YativoError` and have `status`, `code`, `message` and `fields`.

The SDK **automatically retries** network errors, `429` and `5xx` (twice, waiting a little longer each time), using the same idempotency key so nothing happens twice. It never retries other errors.

## Lists with many pages

```python
# One page
page = yativo.deposits.list(currency="BRL", per_page=50)
print(page.data, page.pagination, page.has_more)

# Every page, one item at a time
for deposit in yativo.paginate(yativo.deposits.list, per_page=100):
    print(deposit["id"], deposit["status"])
```

## Settings

| Option | Default | What it does |
|---|---|---|
| `api_key` | `YATIVO_API_KEY` | Your API key |
| `api_secret` | `YATIVO_API_SECRET` | Your API secret |
| `environment` | `YATIVO_ENVIRONMENT` or `production` | `production` or `sandbox` |
| `base_url` | `YATIVO_BASE_URL` | Use a different URL (must be `https`, except `localhost`) |
| `timeout` | `30` | Seconds to wait for each request |
| `max_retries` | `2` | Retries for network errors, 429 and 5xx |
| `webhook_secret` | `YATIVO_WEBHOOK_SECRET` | Used by `yativo.webhooks` |
| `transport` | urllib | Your own HTTP function, e.g. for a proxy |

## Test safely in the sandbox

1. Create a sandbox API key and set `YATIVO_ENVIRONMENT=sandbox`.
2. Use sandbox test cards for Card Checkout: `4242 4242 4242 4242` (succeeds), `4000 0000 0000 0002` (declined). Any future expiry and any CVC.
3. Send yourself sample webhooks:

```python
yativo = Yativo(environment="sandbox")
yativo.sandbox.simulate_webhook("payin")  # sends deposit.created and deposit.updated to your URL
```

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `401` *Both X-Api-Key and X-Api-Secret headers are required.* | The key or the secret is missing. | Set both `YATIVO_API_KEY` and `YATIVO_API_SECRET`. |
| `401` *Invalid or revoked API credentials.* | The key and secret don't match, the key was revoked, or you mixed sandbox and production. | Copy both values again from the same key. Sandbox keys only work with `environment: sandbox`. |
| `403` *This API key has no whitelisted IP addresses.* | The key has no server addresses yet. | Add your server's IP address to the key in **Developers → API Keys**. |
| `403` *This IP address is not allowed to use this API key.* | You're calling from a computer that isn't on the key's list. | Find the address with `curl https://checkip.amazonaws.com` and add it to the key. |
| `403` *This endpoint cannot be used with an API key.* | Some account settings can only be changed in the dashboard. | Do it at [app.yativo.com](https://app.yativo.com). |
| `409` *Idempotency key reuse detected with a different request payload.* | You reused an idempotency key for a different operation. | Use a new key for each new payment or payout. |
| `422` with `fields` | Something in your request is missing or wrong. | Read the error's fields: each one says what to fix. |
| `429` | Too many requests. | The SDK already waits and retries. Slow down if it keeps happening. |
| `500`-`504` | A temporary problem on Yativo's side. | The SDK already retried. Try again in a minute. |
| Connection error / timeout | Your server couldn't reach Yativo. | Check your internet connection, firewall and proxy. |
| Your webhook URL answers `401` | The signature didn't match. | Check `YATIVO_WEBHOOK_SECRET` is the secret from your *current* webhook, and that you pass the **raw** body to the SDK. |

## FAQ

**Do I need to log in or refresh a token?**
No. Your API key works until you revoke it. The SDK sends it with every request.

**Can I use this in a browser or a mobile app?**
No. Anyone could read your secret there. Call Yativo from your server, and have your app talk to your server.

**Is my money safe while I test?**
Yes, if you use the sandbox (`environment: sandbox`) and sandbox keys. Nothing real moves there.

**What if my server crashes in the middle of a payment?**
Send the same `idempotency key` again (for example your order number). Yativo returns the first result instead of creating a second payment.

**Why check the payment again after a webhook?**
A webhook is a notification. Asking the API (`deposits.retrieve`) is the proof. It also protects you if someone sends a fake request to your webhook URL.

**I got the same webhook twice.**
That's normal: Yativo retries when it isn't sure you received it. Remember what you've already handled and skip repeats.

**Where's the list of fields for each request?**
In the [Yativo API docs](https://docs.yativo.com). This SDK passes your fields through unchanged.

## Examples, tests and contributing

- **Examples** you can run: [`examples/`](examples). Start with `python examples/quickstart.py BRA BRL`.
- **Every method**: [docs/REFERENCE.md](docs/REFERENCE.md).
- **Tests**: run them yourself, or read the latest results in [TEST_RESULTS.md](TEST_RESULTS.md).

```bash
pip install -e . pytest
python -m pytest -v tests
```

- **Contributing**: see [CONTRIBUTING.md](CONTRIBUTING.md). Please read the [code of conduct](CODE_OF_CONDUCT.md).
- **Security**: report vulnerabilities privately, see [SECURITY.md](SECURITY.md).
- **Other languages**: [Node.js](https://github.com/Yativo/yativo-fiat-node) · [Python](https://github.com/Yativo/yativo-fiat-python) · [PHP](https://github.com/Yativo/yativo-fiat-php) · [Laravel](https://github.com/Yativo/yativo-fiat-laravel) · [Go](https://github.com/Yativo/yativo-fiat-go) · [WooCommerce](https://github.com/Yativo/yativo-fiat-woocommerce)

## License

[MIT](LICENSE) © Yativo
