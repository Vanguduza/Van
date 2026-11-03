"""Initial account policy, applied by production creators, never registry test seeding."""
INITIAL_ACCOUNT_MODE = "OBSERVE"


class InitialAccountModeError(ValueError):
    code = "NEW_ACCOUNT_OBSERVE_REQUIRED"


def require_initial_account_mode(mode=INITIAL_ACCOUNT_MODE):
    """A provider environment or trading scope is not account-mode authority."""
    if type(mode) is not str or mode != INITIAL_ACCOUNT_MODE:
        raise InitialAccountModeError("New accounts must start OBSERVE; use the existing mode and mandate controls after registration")
    return INITIAL_ACCOUNT_MODE
