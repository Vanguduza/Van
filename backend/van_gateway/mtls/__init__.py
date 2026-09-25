"""Mutual TLS between the VAN Android app and this gateway.

The phone connects straight to the Hermes host: one TLS 1.3 listener, a private device CA that
signs both the server certificate (pinned by the app) and one client certificate per enrolled
device. Nothing sits between the phone and this process.

- `pki`        the device CA: server certificate, client issuance from a CSR, revocation.
- `transport`  the TLS context and the uvicorn protocol shims that hand the verified client
               certificate to the ASGI app; the gate that enforces it per route.
- `serve`      the process entry point: the existing loopback listener plus the public
               mutual-TLS listener, one process, one app instance.
"""
