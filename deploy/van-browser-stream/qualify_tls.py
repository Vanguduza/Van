#!/usr/bin/env python3
"""Distinguish a peer certificate denial from missing/broken transport.

Only explicit TLS certificate alerts from a verified server establish denial.
A connection error, timeout, local certificate error or EOF cannot establish it.
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl


CERTIFICATE_ALERTS = frozenset({
    "TLSV13_ALERT_CERTIFICATE_REQUIRED", "TLSV1_ALERT_CERTIFICATE_REQUIRED",
    "TLSV1_ALERT_UNKNOWN_CA", "SSLV3_ALERT_BAD_CERTIFICATE",
    "TLSV1_ALERT_ACCESS_DENIED", "SSLV3_ALERT_CERTIFICATE_EXPIRED",
    "SSLV3_ALERT_CERTIFICATE_UNKNOWN", "SSLV3_ALERT_UNSUPPORTED_CERTIFICATE",
})


def probe_tls(host: str, port: int, ca_file: str, *, cert_file: str | None = None, key_file: str | None = None, timeout: float = 3.0) -> dict[str, str]:
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_verify_locations(cafile=ca_file)
        if cert_file:
            context.load_cert_chain(cert_file, key_file)
    except (OSError, ssl.SSLError, ValueError):
        return {"result": "CONFIGURATION_ERROR", "reason": "certificate_configuration_invalid"}
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as connection:
                # TLS 1.3 may deliver a certificate alert only on the first read.
                # Read the peer's final handshake/alert before sending application
                # bytes: a rejecting peer may reset on unread client data, hiding
                # its certificate alert and making the result indeterminate.
                connection.settimeout(min(timeout, 0.25))
                try:
                    response = connection.recv(1)
                except socket.timeout:
                    response = None
                if response is not None:
                    if response or cert_file:
                        return {"result": "ADMITTED", "reason": "verified_tls_handshake_completed" if cert_file else "application_data_without_client_certificate"}
                    return {"result": "INDETERMINATE", "reason": "no_certificate_denial_observed"}
                connection.settimeout(timeout)
                # This is an empty wire frame, not a control operation or grant.
                connection.sendall(b"\x00\x00\x00\x00")
                try:
                    response = connection.recv(1)
                except socket.timeout:
                    if cert_file:
                        return {"result": "ADMITTED", "reason": "verified_tls_handshake_completed"}
                    return {"result": "INDETERMINATE", "reason": "no_certificate_denial_observed"}
                if cert_file:
                    return {"result": "ADMITTED", "reason": "verified_tls_handshake_completed"}
                if response:
                    return {"result": "ADMITTED", "reason": "application_data_without_client_certificate"}
                return {"result": "INDETERMINATE", "reason": "no_certificate_denial_observed"}
    except ssl.SSLError as exc:
        reason = getattr(exc, "reason", "")
        if reason in CERTIFICATE_ALERTS:
            return {"result": "DENIED", "reason": "peer_certificate_alert"}
        return {"result": "TLS_ERROR", "reason": "tls_failure_without_certificate_denial"}
    except (socket.timeout, OSError):
        return {"result": "UNREACHABLE", "reason": "transport_unavailable"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()
    print(json.dumps(probe_tls(args.host, args.port, args.ca, cert_file=args.cert, key_file=args.key)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
