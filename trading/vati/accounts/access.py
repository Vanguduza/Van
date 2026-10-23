"""Registry ceilings and an entry fence shared with account mutation writers."""
from contextlib import contextmanager
from functools import wraps
from decimal import Decimal

from vati.accounts.registry import Account, AccountRegistry, AccountRegistryError
from vati.core.file_lock import exclusive_state_lock
from vati.core.file_lock import StateFileLockError

class AccountModeAuthorityError(RuntimeError):
    """A current valid profile no longer permits the bound sending mode."""


SENDING_MODES = frozenset({"DEMO_TRADER", "LIMITED_LIVE", "AUTONOMOUS_LIVE"})


def validate_mode(account: Account, mandate_mode: str) -> None:
    """A signed mandate cannot widen the configured account's authority."""
    if mandate_mode not in SENDING_MODES:
        return
    if (mandate_mode == "DEMO_TRADER") != account.demo:
        raise AccountModeAuthorityError("mandate and account have mismatched demo/live safety identity")
    allowed = {
        "DEMO_TRADER": {"DEMO_TRADER"},
        "LIMITED_LIVE": {"LIMITED_LIVE"},
        "AUTONOMOUS_LIVE": {"LIMITED_LIVE", "AUTONOMOUS_LIVE"},
    }.get(account.mode, set())
    if mandate_mode not in allowed:
        raise AccountModeAuthorityError("mandate exceeds the configured account mode")


def native_binding(account: Account) -> tuple:
    return (account.alias, account.broker, account.login, account.server,
            account.currency, account.demo, account.router_venue,
            account.bridge_url, account.credential_ref, account.mandate_ref)


@contextmanager
def entry_fence(registry: AccountRegistry, bound: Account):
    """Hold the same account-operation and registry locks through native submission.

    A rotation/removal cannot overtake a checked entry. Lock order is the same as
    Commander: account operation, then registry. Protection uses identity binding
    separately and stays available after a mode reduction or disabled entry flag.
    """
    path = registry.path
    with exclusive_state_lock(path.with_name(path.name + ".operation." + bound.alias)):
        with registry._mutation_lock():
            current = AccountRegistry(path).get(bound.alias)
            if native_binding(current) != native_binding(bound):
                raise AccountRegistryError("registered native account binding changed; rebuild the connection")
            if not current.enabled or current.mode not in SENDING_MODES or bound.mode not in SENDING_MODES:
                raise AccountRegistryError("account currently refuses new entries")
            validate_mode(current, bound.mode)
            yield


def bind_entry_authority(adapter, registry: AccountRegistry, bound: Account):
    """Fence factory-created senders without replacing their native adapter type.

    Type identity matters to existing paper finality/replay. Only the entry
    method is bound: stop maintenance and protective closes retain their native
    implementation. A registry denial occurs before delegation and cannot turn
    a provider exception after send into a false rejection.
    """
    from vati.execution.base import ExecutionReceipt
    native_submit = adapter.submit

    @wraps(native_submit)
    def submit(command, *, now_ms, **options):
        def refused():
            return ExecutionReceipt(command.trade_intent_id, command.decision_hash,
                bound.router_venue, "REJECTED", Decimal("0"), None,
                command.entry_price, command.entry_price, command.entry_price,
                False, now_ms, now_ms,
                reject_reason="registered account entry authority changed or command binding differs").sealed()
        if command.account_alias != bound.alias or command.venue != bound.router_venue:
            return refused()
        scope = entry_fence(registry, bound)
        try:
            scope.__enter__()
        except (AccountRegistryError, AccountModeAuthorityError, StateFileLockError, OSError):
            return refused()
        try:
            return native_submit(command, now_ms=now_ms, **options)
        finally:
            scope.__exit__(None, None, None)

    adapter.submit = submit
    return adapter
