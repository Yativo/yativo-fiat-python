# Test results

Latest local run before the 1.0.0 release. CI runs the same checks on every push and pull request: see the **Actions** tab for the current status.

| | |
|---|---|
| Date | 2026-10-22 |
| Version | 1.0.0 |
| Environment | Python 3.10.12, pytest 9.1.1 on Zorin OS 17.3 |
| Command | `python -m pytest -v tests` |
| Result | **22 tests, 22 passed, 0 failed** |

## What the tests cover

- Authentication headers on every request, and no `Authorization` header
- Production and sandbox URLs, and refusal of plain `http` (except localhost)
- Idempotency keys on writes (generated or your own), never on reads
- URL-encoding of path parameters and query strings
- Authentication headers can't be overridden
- Lists and the pagination helper
- Retries on `503` with the same idempotency key, and no retries on `4xx`
- Error types, codes, messages and field errors (including a failed response sent with HTTP 200)
- Network failures and timeouts
- Credentials never appear in logs, debug output, serialization or errors
- Webhook signatures (valid, uppercase, wrong secret, tampered body, missing), event decoding and dedup keys
- Webhook routing (exact type, `prefix.*` and `*`) and HTTP answers `200` / `401` / `500`

## Output

```text
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.1.1, pluggy-1.7.0 -- <venv>/bin/python
rootdir: .
configfile: pyproject.toml
collecting ... collected 22 items

tests/test_sdk.py::ClientTests::test_200_failed_is_error PASSED          [  4%]
tests/test_sdk.py::ClientTests::test_auth_headers_and_url PASSED         [  9%]
tests/test_sdk.py::ClientTests::test_body_kwargs_and_idempotency PASSED  [ 13%]
tests/test_sdk.py::ClientTests::test_connection_error PASSED             [ 18%]
tests/test_sdk.py::ClientTests::test_feature_code PASSED                 [ 22%]
tests/test_sdk.py::ClientTests::test_list_returns_page PASSED            [ 27%]
tests/test_sdk.py::ClientTests::test_no_retry_on_404 PASSED              [ 31%]
tests/test_sdk.py::ClientTests::test_pages_and_paginate PASSED           [ 36%]
tests/test_sdk.py::ClientTests::test_path_params_encoded PASSED          [ 40%]
tests/test_sdk.py::ClientTests::test_protected_headers PASSED            [ 45%]
tests/test_sdk.py::ClientTests::test_query_encoding PASSED               [ 50%]
tests/test_sdk.py::ClientTests::test_real_http_round_trip PASSED         [ 54%]
tests/test_sdk.py::ClientTests::test_refuses_http_and_missing_credentials PASSED [ 59%]
tests/test_sdk.py::ClientTests::test_retry_same_key PASSED               [ 63%]
tests/test_sdk.py::ClientTests::test_sandbox PASSED                      [ 68%]
tests/test_sdk.py::ClientTests::test_secrets_never_exposed PASSED        [ 72%]
tests/test_sdk.py::ClientTests::test_validation_error PASSED             [ 77%]
tests/test_sdk.py::WebhookTests::test_construct_event PASSED             [ 81%]
tests/test_sdk.py::WebhookTests::test_failing_listener_answers_500 PASSED [ 86%]
tests/test_sdk.py::WebhookTests::test_respond_and_django_style_headers PASSED [ 90%]
tests/test_sdk.py::WebhookTests::test_routing PASSED                     [ 95%]
tests/test_sdk.py::WebhookTests::test_signature PASSED                   [100%]

============================== 22 passed in 1.97s ==============================
```

## Example smoke tests

The examples were run against a local mock of the Yativo API (`YATIVO_BASE_URL=http://localhost:8799/api/v1`).

### Quick start

```text
Key check: pass
Balances: [{'currency': 'USD', 'balance': '1250.00'}]
Payment methods for CHL/CLP:
  #22  Bank Transfer  (credits: USD)
  #23  Card  (credits: USD,EUR)
```

### Checkout server: payment, forged webhook, signed webhook, confirmation

```text
[python] /pay redirects to: https://checkout.example/process-payin/dep-2/paynow
[python] before payment: Order ord3102: pending
[python] forged webhook -> HTTP 401
[python] signed webhook while API still says pending -> HTTP 200
[python] after webhook, API pending: Order ord3102: pending
[python] signed webhook after API says success -> HTTP 200
[python] final: Order ord3102: paid
```

The order is only marked paid after the API reports the deposit as `success`. A forged webhook is rejected, and a genuine webhook alone doesn't mark it paid.
