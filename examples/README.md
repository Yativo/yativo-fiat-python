# Examples

Install the SDK from the repository root, then run any example:

```bash
pip install -e .
export YATIVO_API_KEY=yativo_pk_...
export YATIVO_API_SECRET=yativo_sk_...
export YATIVO_ENVIRONMENT=sandbox
```

| File | What it shows | Run |
|---|---|---|
| `quickstart.py` | Check your key, balances, payment methods | `python examples/quickstart.py BRA BRL` |
| `checkout_server.py` | Full payin flow with webhooks, standard library only | `python examples/checkout_server.py` |
| `flask_app.py` | The same flow in Flask | `pip install flask && flask --app examples/flask_app run` |
| `card_checkout.py` | Create a card payment link | `SELLER_CUSTOMER_ID=... python examples/card_checkout.py 49.99` |

Use sandbox keys while you try things: no real money moves.
