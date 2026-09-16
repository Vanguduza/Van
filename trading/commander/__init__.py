"""Van trading commander (Rev 5 Part H): the Hermes subordinate on van-trading-core.

A typed command surface — status, ledger, services, bounded log tail, bounded
backtest, VEKL resolve, owner-signed halt, doctor — behind HMAC-signed requests.
It is deliberately not a shell: every command is named, its arguments are
validated, its subprocesses are allowlisted, and its output is redacted."""

from commander.auth import sign_headers, verify_request
from commander.app import CommanderSettings, create_app

__all__ = ["CommanderSettings", "create_app", "sign_headers", "verify_request"]
