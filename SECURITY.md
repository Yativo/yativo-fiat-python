# Security policy

## Reporting a vulnerability

Please report security issues **privately** to **security@yativo.com**, not in a public issue or pull request.

Include:

- the package and version
- what the issue is and how to reproduce it
- the impact you expect

We'll confirm receipt within 3 business days and keep you updated until it's fixed.

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |

## Keeping your integration safe

- Keep your API key, API secret and webhook secret in environment variables or a secrets manager. Never commit them.
- Call Yativo from your server only, never from a browser or mobile app.
- Add only your servers' IP addresses to your API key in the Yativo dashboard.
- Verify every webhook signature (the SDK does this for you) and confirm payments with the API before fulfilling orders.
