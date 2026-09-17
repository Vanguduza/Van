"""Trading account registry (Rev 5 Part C). An account is a *non-secret* record:
alias, broker kind, mode, currency, server/login identifiers and a reference to
where its credentials live (an env var name or a 0600 secrets file). The
registry never holds a password, token or API key, never prints one, and
refuses a credential that has been pasted into the record itself. The owner
plugs an MT5 or Deriv account in by adding a record and a secrets file; the
session service resolves the adapter from the record."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

SECRET_SHAPED = re.compile(r"(?i)(password|passwd|token|api[_-]?key|secret)")
MODES = ("OBSERVE", "ADVISOR", "DEMO_TRADER", "SHADOW_TRADER", "LIMITED_LIVE", "AUTONOMOUS_LIVE")


class AccountRegistryError(ValueError):
    pass


class BrokerKind:
    MT5 = "MT5"                    # Windows bridge worker (push, mTLS)
    MT5_EA = "MT5_EA"              # MQL5 pull-bridge Expert Advisor on a MetaQuotes/broker VPS (Windows-free)
    DERIV = "DERIV"
    CTRADER = "CTRADER"            # cTrader Open API (Linux-native)
    PAPER = "PAPER"
    ZSE_OWNER_TICKET = "ZSE_OWNER_TICKET"
    ALL = (MT5, MT5_EA, DERIV, CTRADER, PAPER, ZSE_OWNER_TICKET)


@dataclass(frozen=True)
class CredentialRef:
    """Where the secret lives. Exactly one of env_var / secrets_file. Never the secret."""
    env_var: Optional[str] = None
    secrets_file: Optional[str] = None

    def validate(self) -> None:
        if bool(self.env_var) == bool(self.secrets_file):
            raise AccountRegistryError("credential_ref needs exactly one of env_var or secrets_file")


@dataclass(frozen=True)
class Account:
    alias: str
    broker: str
    mode: str
    currency: str
    label: str = ""
    server: str = ""            # MT5 server name / Deriv app_id — identifiers, not secrets
    login: str = ""             # MT5 login number / Deriv loginid — identifier, not a secret
    venue: str = ""             # router venue key; defaults from broker
    bridge_url: str = ""        # MT5: https://<windows-worker>:9443 ; Deriv: wss endpoint override
    credential_ref: CredentialRef = field(default_factory=CredentialRef)
    demo: bool = True
    enabled: bool = True
    mandate_ref: str = ""       # path to the owner-signed mandate JSON for this alias
    notes: str = ""

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]{3,32}", self.alias):
            raise AccountRegistryError(f"alias must be [a-z0-9_]{{3,32}}: {self.alias!r}")
        if self.broker not in BrokerKind.ALL:
            raise AccountRegistryError(f"unknown broker kind {self.broker}")
        if self.mode not in MODES:
            raise AccountRegistryError(f"unknown mode {self.mode}")
        if self.broker in (BrokerKind.MT5, BrokerKind.MT5_EA, BrokerKind.DERIV, BrokerKind.CTRADER):
            self.credential_ref.validate()
        for k, v in asdict(self).items():
            if k == "credential_ref":
                continue
            if isinstance(v, str) and SECRET_SHAPED.search(k):
                raise AccountRegistryError(f"field {k} looks like a credential; credentials live only behind credential_ref")
            if isinstance(v, str) and re.search(r"(?i)(password|token|api[_-]?key)\s*[:=]", v):
                raise AccountRegistryError(f"field {k} contains credential-shaped text; refusing to store it in the registry")
        if not self.demo and self.mode in ("LIMITED_LIVE", "AUTONOMOUS_LIVE") and not self.mandate_ref:
            raise AccountRegistryError("a live account needs an owner-signed mandate_ref")

    @property
    def router_venue(self) -> str:
        return self.venue or {BrokerKind.MT5: "mt5", BrokerKind.MT5_EA: "mt5", BrokerKind.DERIV: "deriv", BrokerKind.CTRADER: "ctrader", BrokerKind.PAPER: "paper", BrokerKind.ZSE_OWNER_TICKET: "zse"}[self.broker]

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d["credential_ref"] = {"kind": "env" if self.credential_ref.env_var else ("file" if self.credential_ref.secrets_file else "none")}
        d["safety_identity"] = self.safety_identity
        return d

    @property
    def safety_identity(self) -> str:
        if self.broker == BrokerKind.PAPER:
            return "PAPER"
        if self.mode in ("OBSERVE", "ADVISOR"):
            return "READ ONLY"
        return "DEMO" if self.demo else "LIVE"


def load_secret_file(path: str) -> dict[str, str]:
    """KEY=VALUE lines, file must be 0600 (or stricter) and owned by the caller. Values never logged."""
    p = Path(path)
    if not p.is_file():
        raise AccountRegistryError(f"secrets file missing: {path}")
    mode = stat.S_IMODE(p.stat().st_mode)
    if mode & 0o077:
        raise AccountRegistryError(f"secrets file {path} must be mode 0600 (is {oct(mode)})")
    if os.name != "nt" and p.stat().st_uid != os.getuid():
        raise AccountRegistryError(f"secrets file {path} must be owned by the service user")
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


class AccountRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.accounts: dict[str, Account] = {}
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for rec in data.get("accounts", []):
                self._put(Account(**{**rec, "credential_ref": CredentialRef(**rec.get("credential_ref", {}))}))

    def _put(self, a: Account) -> None:
        a.validate()
        self.accounts[a.alias] = a

    def add(self, a: Account) -> Account:
        if a.alias in self.accounts:
            raise AccountRegistryError(f"alias {a.alias} already registered; remove it first")
        self._put(a)
        self.save()
        return a

    def remove(self, alias: str) -> None:
        self.accounts.pop(alias)
        self.save()

    def get(self, alias: str) -> Account:
        try:
            return self.accounts[alias]
        except KeyError:
            raise AccountRegistryError(f"unknown account alias {alias}") from None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema_version": 1, "accounts": [asdict(a) for a in sorted(self.accounts.values(), key=lambda x: x.alias)]}, indent=2) + "\n", encoding="utf-8")

    def credentials(self, alias: str) -> dict[str, str]:
        """Resolve the secret for an account. Returned dict is for the transport only; never log it."""
        a = self.get(alias)
        ref = a.credential_ref
        if ref.env_var:
            v = os.environ.get(ref.env_var)
            if not v:
                raise AccountRegistryError(f"env var {ref.env_var} for {alias} is not set")
            return {"TOKEN": v}
        if ref.secrets_file:
            return load_secret_file(ref.secrets_file)
        return {}

    def public(self) -> list[dict[str, Any]]:
        return [a.public() for a in sorted(self.accounts.values(), key=lambda x: x.alias)]
