"""The same flow with Flask (pip install flask).

    flask --app examples/flask_app run --port 3000
"""
import os

from flask import Flask, redirect, request

from yativo_fiat import Yativo, WebhookHandler

app = Flask(__name__)
yativo = Yativo()
webhooks = WebhookHandler(os.environ.get("YATIVO_WEBHOOK_SECRET", ""))


@webhooks.on("deposit.updated")
def deposit_updated(event):
    deposit = yativo.deposits.retrieve(event.payload["id"])  # confirm with the API
    if deposit["status"] == "success":
        print("paid:", deposit["id"])  # fulfil the order here


@app.get("/pay")
def pay():
    created = yativo.deposits.create(
        gateway=int(os.environ.get("GATEWAY_ID", "22")),
        amount=float(request.args.get("amount", "100")),
        currency="USD",
        redirect_url=request.host_url + "thanks",
        idempotency_key="order-" + request.args.get("order", "demo"),
    )
    return redirect(created["deposit_url"], code=303)


app.add_url_rule("/webhooks/yativo", view_func=webhooks.flask_view(), methods=["POST"])
