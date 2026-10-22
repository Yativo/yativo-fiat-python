"""Quick start: check your API key, show your balances and list payment methods.

    export YATIVO_API_KEY=yativo_pk_...  YATIVO_API_SECRET=yativo_sk_...  YATIVO_ENVIRONMENT=sandbox
    python examples/quickstart.py BRA BRL
"""
import sys

from yativo_fiat import Yativo, YativoError

country = sys.argv[1] if len(sys.argv) > 1 else "BRA"
currency = sys.argv[2] if len(sys.argv) > 2 else "BRL"
yativo = Yativo()  # reads YATIVO_API_KEY, YATIVO_API_SECRET and YATIVO_ENVIRONMENT

try:
    # 1. Is the key working from this computer?
    check = yativo.ip_whitelist.check()
    print("Key check:", check["result"])
    if check["result"] != "pass":
        print(check.get("summary"))
        sys.exit(1)

    # 2. Your balances
    print("Balances:", yativo.wallets.balance())

    # 3. Ways your customers can pay you in this country and currency
    print(f"Payment methods for {country}/{currency}:")
    for m in yativo.payment_methods.payin(country=country, currency=currency):
        print(f"  #{m['id']}  {m['method_name']}  (credits: {m.get('base_currency')})")
except YativoError as err:
    print(f"Yativo said no ({err.status} {err.code or ''}): {err.message}")
    sys.exit(1)
