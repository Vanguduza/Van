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
import tempfile
from contextlib import contextmanager
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
        if type(self.demo) is not bool or type(self.enabled) is not bool:
            raise AccountRegistryError("demo and enabled must be JSON booleans")
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
        # All aliases of one existing file share its mutation lock.
        self.path = Path(path).resolve()
        self.accounts = self._read_accounts()
        self._loaded_accounts = dict(self.accounts)

    def _read_accounts(self) -> dict[str, Account]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version", 1) != 1 or not isinstance(data.get("accounts"), list):
                raise AccountRegistryError("account registry schema is invalid")
            records = {}
            for rec in data["accounts"]:
                account = Account(**{**rec, "credential_ref": CredentialRef(**rec.get("credential_ref", {}))})
                account.validate()
                if account.alias in records:
                    raise AccountRegistryError("account registry contains duplicate identities")
                records[account.alias] = account
            return records
        except (OSError, ValueError, TypeError) as exc:
            raise AccountRegistryError("account registry cannot be read safely; reload or reconcile before mutation") from exc

    @contextmanager
    def _mutation_lock(self):
        from vati.core.file_lock import exclusive_state_lock, StateFileLockError
        try:
            with exclusive_state_lock(self.path):
                yield
        except StateFileLockError as exc:
            raise AccountRegistryError(str(exc)) from exc

    def _mutate(self, operation: str, alias: str, account: Account | None = None):
        if account is not None:
            account.validate()
        with self._mutation_lock():
            current = self._read_accounts()
            if operation == "add":
                if alias in current:
                    raise AccountRegistryError(f"alias {alias} already registered; reload before changing it")
            else:
                if alias not in self.accounts:
                    raise AccountRegistryError(f"unknown account alias {alias}")
                if current.get(alias) != self.accounts[alias]:
                    raise AccountRegistryError(f"account {alias} changed since read; reload before mutation")
            before = self.accounts
            self.accounts = current
            if operation == "remove":
                del self.accounts[alias]
            else:
                self.accounts[alias] = account
            try:
                self._save_unlocked()
            except BaseException:
                self.accounts = before
                raise
            self._loaded_accounts = dict(self.accounts)
        return account

    def add(self, a: Account) -> Account:
        """Add against current persisted records without dropping other writers' edits."""
        return self._mutate("add", a.alias, a)

    def replace(self, a: Account) -> Account:
        """Replace one unchanged local record; stale exact-account edits refuse."""
        return self._mutate("replace", a.alias, a)

    def remove(self, alias: str) -> None:
        """Unlink an unchanged local record; broker/exposure authority belongs to its caller."""
        self._mutate("remove", alias)

    def get(self, alias: str) -> Account:
        try:
            return self.accounts[alias]
        except KeyError:
            raise AccountRegistryError(f"unknown account alias {alias}") from None

    def save(self) -> None:
        """Explicit whole-registry save refuses a stale baseline rather than overwriting it."""
        with self._mutation_lock():
            if self._read_accounts() != self._loaded_accounts:
                raise AccountRegistryError("account registry changed since read; reload before save")
            for alias, account in self.accounts.items():
                account.validate()
                if alias != account.alias:
                    raise AccountRegistryError("registry key disagrees with account identity")
            self._save_unlocked()
            self._loaded_accounts = dict(self.accounts)

    def _save_unlocked(self) -> None:
        """Write the complete registry through same-directory atomic replacement.

        Direct write_text could truncate the only valid record on interruption.
        Existing permission bits are preserved; new files default to owner-only.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"schema_version": 1, "accounts": [asdict(a) for a in sorted(self.accounts.values(), key=lambda x: x.alias)]},
            indent=2,
        ) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            mode = stat.S_IMODE(self.path.stat().st_mode) if self.path.exists() else 0o600
            os.chmod(temp_name, mode)
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

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
