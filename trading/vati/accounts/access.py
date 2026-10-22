"""Registry ceilings and an entry fence shared with account mutation writers."""
from contextlib import contextmanager

from vati.accounts.registry import Account, AccountRegistry, AccountRegistryError
from vati.core.file_lock import exclusive_state_lock

SENDING_MODES = frozenset({"DEMO_TRADER", "LIMITED_LIVE", "AUTONOMOUS_LIVE"})


def validate_mode(account: Account, mandate_mode: str) -> None:
    """A signed mandate cannot widen the configured account's authority."""
    if mandate_mode not in SENDING_MODES:
        return
    if (mandate_mode == "DEMO_TRADER") != account.demo:
        raise RuntimeError("mandate and account have mismatched demo/live safety identity")
    allowed = {
        "DEMO_TRADER": {"DEMO_TRADER"},
        "LIMITED_LIVE": {"LIMITED_LIVE"},
        "AUTONOMOUS_LIVE": {"LIMITED_LIVE", "AUTONOMOUS_LIVE"},
    }.get(account.mode, set())
    if mandate_mode not in allowed:
        raise RuntimeError("mandate exceeds the configured account mode")


def native_binding(account: Account) -> tuple:
    return (account.alias, account.broker, account.login, account.server,
            account.currency, account.demo, account.router_venue,
            account.bridge_url, account.credential_ref)


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
