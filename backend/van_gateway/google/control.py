from __future__ import annotations

import hmac


class GoogleControlAuthError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def verify_internal_control(expected: str, supplied: str | None) -> None:
    """Authenticate privileged Hermes→gateway Google control-plane calls.

    The shared secret is runtime-only and never belongs in prompts or artifacts.
    Empty configuration fails closed.
    """
    if not expected:
        raise GoogleControlAuthError("internal_control_token_unconfigured")
    if supplied is None or not hmac.compare_digest(expected, supplied):
        raise GoogleControlAuthError("internal_control_unauthorized")
