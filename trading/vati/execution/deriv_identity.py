"""Native authorize-response binding; registry labels never prove broker identity."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


class DerivIdentityError(ValueError):
    pass


def validate_deriv_endpoint(endpoint):
    """Production credentials go only to the official secure provider bases."""
    if not endpoint:
        return
    try:
        uri=urlsplit(endpoint)
        accepted=(uri.scheme=='wss' and uri.hostname in {'ws.derivws.com','ws.binaryws.com'}
            and uri.port in (None,443) and uri.path=='/websockets/v3'
            and uri.username is None and uri.password is None and not uri.query and not uri.fragment)
    except (TypeError,ValueError):
        accepted=False
    if not accepted:
        raise DerivIdentityError('Deriv credentials require an official secure provider endpoint')


@dataclass(frozen=True)
class DerivIdentity:
    login: str
    currency: str
    demo: bool
    require_trade: bool

    def validate(self, profile: dict) -> None:
        if not isinstance(profile, dict):
            raise DerivIdentityError("Deriv native account identity is unavailable")
        if not self.login or profile.get("loginid") != self.login:
            raise DerivIdentityError("Deriv native login does not match the registered account")
        virtual = profile.get("is_virtual")
        if type(virtual) is not int or virtual not in (0, 1) or bool(virtual) != self.demo:
            raise DerivIdentityError("Deriv native demo/live identity does not match the registered account")
        if not self.currency or profile.get("currency") != self.currency:
            raise DerivIdentityError("Deriv native currency does not match the registered account")
        scopes = profile.get("scopes")
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise DerivIdentityError("Deriv native token permissions are unavailable")
        if "read" not in scopes or (self.require_trade and "trade" not in scopes):
            raise DerivIdentityError("Deriv native token lacks the required permissions")
        try:
            balance = Decimal(str(profile["balance"]))
            if not balance.is_finite():
                raise ValueError
        except (KeyError, InvalidOperation, ValueError):
            raise DerivIdentityError("Deriv native balance is unavailable") from None
