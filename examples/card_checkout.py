"""Create a Card Checkout order and print the link to pay it.
Needs Card Checkout access and a customer with an approved card_checkout endorsement.

    SELLER_CUSTOMER_ID=... python examples/card_checkout.py 49.99
"""
import os
import sys
import time

from yativo_fiat import Yativo

yativo = Yativo()
reference = f"demo-{int(time.time())}"
order = yativo.card_checkout.create_order(
    customer_id=os.environ["SELLER_CUSTOMER_ID"],
    amount=sys.argv[1] if len(sys.argv) > 1 else "49.99",  # a decimal string
    currency="USD",
    description="Demo order",
    reference=reference,
    success_url="https://example.com/thanks",
    cancel_url="https://example.com/cart",
    idempotency_key=reference,
)
print(f"Order {order['id']} ({order['status']}). Pay here within 60 minutes:\n{order['checkout_url']}")
print("Sandbox test card: 4242 4242 4242 4242, any future expiry, any CVC.")
