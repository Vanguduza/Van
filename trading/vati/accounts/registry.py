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
from contextlib import contextmanager, ExitStack
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
        self._resource_revisions = {}
        self._schema_version = 1
        self._lifecycles = {}
        self._lifecycle_history = {}
        self.accounts = self._read_accounts()
        self._loaded_accounts = dict(self.accounts)
        self._loaded_revisions = dict(self._resource_revisions)

    def _read_accounts(self) -> dict[str, Account]:
        if not self.path.exists():
            self._resource_revisions = {}
            self._schema_version = 1
            self._lifecycles = {}
            self._lifecycle_history = {}
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
                raise AccountRegistryError("account registry schema is invalid")
            version=data.get("schema_version",1)
            if type(version) is not int or version not in (1,2,3):
                raise AccountRegistryError("account registry schema is unsupported")
            if version==1 and data.get("account_lifecycles") or version>=2 and not data.get("account_lifecycles"):
                raise AccountRegistryError("lifecycle registry version or persistent detachment is unavailable; HOLD")
            if (version<3 and 'account_lifecycle_history' in data
                or version==3 and not data.get('account_lifecycle_history')):
                raise AccountRegistryError('lifecycle history schema or persistent incarnation evidence unavailable; HOLD')
            revisions = data.get("resource_revisions", {})
            if (not isinstance(revisions, dict) or any(
                not isinstance(alias, str) or not re.fullmatch(r"[a-z0-9_]{3,32}", alias)
                or type(epoch) is not int or not 0 < epoch < 2**63
                for alias, epoch in revisions.items())):
                raise AccountRegistryError("account resource revisions are invalid")
            records = {}
            for rec in data["accounts"]:
                account = Account(**{**rec, "credential_ref": CredentialRef(**rec.get("credential_ref", {}))})
                account.validate()
                if account.alias in records:
                    raise AccountRegistryError("account registry contains duplicate identities")
                records[account.alias] = account
            from vati.accounts.lifecycle import validate_records,validate_history
            self._lifecycles = validate_records(data.get("account_lifecycles", {}))
            self._lifecycle_history=validate_history(self._lifecycles,data.get("account_lifecycle_history", {}))
            self._schema_version = version
            self._resource_revisions = dict(revisions)
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

    def operation_lock(self, alias: str):
        from vati.core.file_lock import exclusive_state_lock
        if not re.fullmatch(r"[a-z0-9_]{3,32}", alias):
            raise AccountRegistryError("account alias is invalid")
        return exclusive_state_lock(self.path.with_name(self.path.name + ".operation." + alias))

    def _mutate(self, operation: str, alias: str, account: Account | None = None, *, before_replace=None, after_replace=None):
        if account is not None:
            account.validate()
        with self.operation_lock(alias), self._mutation_lock():
            current = self._read_accounts()
            if operation == "add":
                if alias in current:
                    raise AccountRegistryError(f"alias {alias} already registered; reload before changing it")
            else:
                if alias not in self.accounts:
                    raise AccountRegistryError(f"unknown account alias {alias}")
                if current.get(alias) != self.accounts[alias]:
                    raise AccountRegistryError(f"account {alias} changed since read; reload before mutation")
            if self._resource_revisions.get(alias, 0) != self._loaded_revisions.get(alias, 0):
                raise AccountRegistryError(f"account {alias} changed since read; reload before mutation")
            before = self.accounts
            previous_revisions = dict(self._resource_revisions)
            self.accounts = current
            if operation == "remove":
                del self.accounts[alias]
            else:
                self.accounts[alias] = account
            self._resource_revisions[alias] = self._resource_revisions.get(alias, 0) + 1
            try:
                if after_replace is not None:
                    self._save_unlocked(before_replace=before_replace,after_replace=after_replace)
                else:
                    self._save_unlocked(before_replace=before_replace) if before_replace is not None else self._save_unlocked()
            except BaseException:
                self.accounts = before
                self._resource_revisions = previous_revisions
                raise
            self._loaded_accounts = dict(self.accounts)
            self._loaded_revisions = dict(self._resource_revisions)
        return account

    def add(self, a: Account, *, before_replace=None) -> Account:
        """Add against current persisted records without dropping other writers' edits."""
        return self._mutate("add", a.alias, a, before_replace=before_replace)

    def replace(self, a: Account, *, before_replace=None) -> Account:
        """Replace one unchanged local record; stale exact-account edits refuse."""
        return self._mutate("replace", a.alias, a, before_replace=before_replace)

    def remove(self, alias: str, *, before_replace=None, after_replace=None) -> None:
        """Unlink an unchanged local record; broker/exposure authority belongs to its caller."""
        self._mutate("remove", alias, before_replace=before_replace,after_replace=after_replace)

    def lifecycle_update(self, alias, transform, *, before_replace=None, after_replace=None, advance_resource=True):
        """One native registry writer; lifecycle data and record share a replacement.

        transform receives a freshly loaded registry under the same alias/global
        locks as entry/removal. It never grants account/strategy authority.
        """
        with self.operation_lock(alias), self._mutation_lock():
            current = AccountRegistry(self.path)
            import copy
            original_lifecycles=copy.deepcopy(current._lifecycles)
            original_history=copy.deepcopy(current._lifecycle_history)
            original_accounts=dict(current.accounts)
            result = transform(current)
            from vati.accounts.lifecycle import validate_records,validate_history
            validate_records(current._lifecycles)
            validate_history(current._lifecycles,current._lifecycle_history)
            # A metadata prune/rollback is not account reassignment authority.
            if not original_lifecycles.keys()<=current._lifecycles.keys():
                raise AccountRegistryError("persistent account detachment cannot be erased")
            if set(current._lifecycles)-set(original_lifecycles)-{alias}:
                raise AccountRegistryError("lifecycle writer cannot widen its account scope")
            immutable={'schema','alias','operation_id','device_id','account_control_domain','incarnation',
                'created_at_unix','archive_at_unix','grace_seconds','strategies','history_ref',
                'credential_disposition','unlink_ref','oauth_discard_ref','detached','link_intent',
                'remote_account_closed','original_request'}
            for subject,old in original_lifecycles.items():
                now=current._lifecycles[subject]
                rotation=(subject==alias and now['operation_id']!=old['operation_id']
                    and now['incarnation']!=old['incarnation'] and alias in original_accounts
                    and current._lifecycle_history.get(old['operation_id'])==old)
                if not rotation and (subject!=alias and now!=old or any(now[k]!=old[k] for k in immutable)):
                    raise AccountRegistryError("original account lifecycle binding is immutable")
            if not original_history.keys()<=current._lifecycle_history.keys():
                raise AccountRegistryError('original lifecycle history cannot be erased')
            for operation,old in original_history.items():
                now=current._lifecycle_history[operation]
                if now==old:continue
                allowed={('DELETING','PENDING_ARCHIVE'),('DISCONNECTING','DISCONNECTED'),('PENDING_ARCHIVE','ARCHIVED')}
                if (old['alias']!=alias or not callable(before_replace)
                    or (old['phase'],now['phase']) not in allowed or now['revision']!=old['revision']+1
                    or any(now[k]!=old[k] for k in immutable)
                    or now['phase'] in {'DISCONNECTED','ARCHIVED'} and now['restore'] is not None
                    or now['phase']=='ARCHIVED' and now['session_sources']!=[]
                    or now['phase']!='ARCHIVED' and now['session_sources']!=old['session_sources']
                    or now['phase']=='PENDING_ARCHIVE' and now['restore']!=old['restore']):
                    raise AccountRegistryError('historical lifecycle binding is immutable')
            for operation in current._lifecycle_history.keys()-original_history.keys():
                old=original_lifecycles.get(alias)
                if (old is None or operation!=old['operation_id'] or current._lifecycle_history[operation]!=old
                    or current._lifecycles[alias]['operation_id']==operation):
                    raise AccountRegistryError('history can only retain the exact replaced incarnation')
            if any(current.accounts.get(subject)!=account for subject,account in original_accounts.items() if subject!=alias) or set(current.accounts)-set(original_accounts)-{alias}:
                raise AccountRegistryError("lifecycle writer cannot mutate another account")
            if advance_resource:
                current._resource_revisions[alias] = current._resource_revisions.get(alias, 0) + 1
            current._save_unlocked(before_replace=before_replace,after_replace=after_replace or (lambda:None))
            self.accounts, self._lifecycles = current.accounts, current._lifecycles
            self._lifecycle_history=current._lifecycle_history
            self._resource_revisions = current._resource_revisions
            self._schema_version = current._schema_version
            self._loaded_accounts = dict(self.accounts)
            self._loaded_revisions = dict(self._resource_revisions)
            return result

    def touch(self, alias: str) -> None:
        """Advance a native credential/resource generation without changing metadata."""
        self._mutate("touch", alias, self.get(alias))

    def get(self, alias: str) -> Account:
        try:
            return self.accounts[alias]
        except KeyError:
            raise AccountRegistryError(f"unknown account alias {alias}") from None

    def save(self) -> None:
        """Explicit whole-registry save refuses a stale baseline rather than overwriting it."""
        with ExitStack() as locks:
            for alias in sorted(set(self.accounts) | set(self._loaded_accounts)):
                locks.enter_context(self.operation_lock(alias))
            locks.enter_context(self._mutation_lock())
            current = self._read_accounts()
            if current != self._loaded_accounts or self._resource_revisions != self._loaded_revisions:
                raise AccountRegistryError("account registry changed since read; reload before save")
            for alias, account in self.accounts.items():
                account.validate()
                if alias != account.alias:
                    raise AccountRegistryError("registry key disagrees with account identity")
            previous_revisions = dict(self._resource_revisions)
            for alias in set(current) | set(self.accounts):
                if current.get(alias) != self.accounts.get(alias):
                    self._resource_revisions[alias] = self._resource_revisions.get(alias, 0) + 1
            try:
                self._save_unlocked()
            except BaseException:
                self._resource_revisions = previous_revisions
                raise
            self._loaded_accounts = dict(self.accounts)
            self._loaded_revisions = dict(self._resource_revisions)

    def _save_unlocked(self, *, before_replace=None, after_replace=None) -> None:
        """Write the complete registry through same-directory atomic replacement.

        Direct write_text could truncate the only valid record on interruption.
        Existing permission bits are preserved; new files default to owner-only.
        """
        if any(type(epoch) is not int or not 0 < epoch < 2**63 for epoch in self._resource_revisions.values()):
            raise AccountRegistryError("account resource revision exhausted or invalid; reconcile before mutation")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Version2 detachment and version3 incarnation history are sticky.
        # Older readers refuse the new schema instead of silently dropping
        # persistent evidence. Source migration is not runtime qualification.
        self._schema_version = 3 if self._schema_version>=3 or self._lifecycle_history else 2 if self._schema_version>=2 or self._lifecycles else 1
        if self._schema_version==3 and not self._lifecycle_history:
            raise AccountRegistryError('persistent lifecycle history cannot be pruned or downgraded')
        if self._schema_version>=2 and not self._lifecycles:
            raise AccountRegistryError("persistent lifecycle state cannot be pruned or downgraded")
        payload = json.dumps(
            {"schema_version": self._schema_version, "accounts": [asdict(a) for a in sorted(self.accounts.values(), key=lambda x: x.alias)],
             "resource_revisions": self._resource_revisions,
             **({"account_lifecycles": self._lifecycles} if self._lifecycles else {}),
             **({"account_lifecycle_history":self._lifecycle_history} if self._lifecycle_history else {})},
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
            if before_replace is not None:before_replace()
            os.replace(temp_name, self.path)
            if after_replace is not None:
                directory=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
                after_replace()
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

    def original_credential_read_view(self, *, alias, managed_root, target, expected_generation, qualify, validate_current):
        """Unshared transport-only read view, never a restored registry account.

        The native recovery owner supplies a genuine plan/current read guard.
        Every secret resolution rechecks it under short canonical file locks;
        no lock is retained across provider I/O. Ordinary methods stay unchanged.
        """
        from vati.core.canonical import canonical_hash
        registry=self
        target=Path(target);managed_root=Path(managed_root)
        if (not callable(qualify) or not callable(validate_current) or managed_root.is_symlink()
                or target.is_symlink() or target.resolve()!=(managed_root.resolve()/(alias+'.env'))):
            raise AccountRegistryError("Original credential read qualification is unavailable")
        def require_qualified():
            fact=qualify()
            if (not isinstance(fact,dict) or set(fact)!={'plan_ref','device_id','alias','managed_root_ref','file_generation'}
                    or not isinstance(fact['plan_ref'],str) or re.fullmatch(r'[0-9a-f]{64}',fact['plan_ref']) is None
                    or not isinstance(fact['device_id'],str) or not fact['device_id'] or fact['alias']!=alias
                    or fact['managed_root_ref']!=canonical_hash(str(managed_root.resolve()))
                    or fact['file_generation']!=list(expected_generation)):
                raise AccountRegistryError("Original credential read qualification is unavailable")
        require_qualified()
        def file_generation(info):
            return [info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns]
        class ReadView:
            path=registry.path
            def get(self,selected):return AccountRegistry(registry.path).get(selected)
            def _mutation_lock(self):return registry._mutation_lock()
            def operation_lock(self,selected):return registry.operation_lock(selected)
            def cleanup_disposition(self):
                from vati.core.file_lock import exclusive_state_lock
                with registry._mutation_lock(),exclusive_state_lock(target):
                    validate_current(AccountRegistry(registry.path));require_qualified()
                return 'DELETE_MANAGED'
            def credentials(self,selected):
                if selected!=alias:raise AccountRegistryError("Original credential read scope differs")
                require_qualified()
                from vati.core.file_lock import exclusive_state_lock
                with registry._mutation_lock(),exclusive_state_lock(target):
                    current=AccountRegistry(registry.path)
                    validate_current(current)
                    require_qualified()
                    if (target.is_symlink() or not target.is_file()
                            or file_generation(target.stat())!=list(expected_generation)
                            or target.stat().st_uid!=os.getuid() or target.stat().st_nlink!=1):
                        raise AccountRegistryError("Original managed credential is unavailable or changed")
                    if any(a.alias!=alias and a.credential_ref.secrets_file
                            and Path(a.credential_ref.secrets_file).resolve()==target.resolve() for a in current.accounts.values()):
                        raise AccountRegistryError("Original credential is now shared; read scope unavailable")
                    values=load_secret_file(str(target))
                    if target.is_symlink() or file_generation(target.stat())!=list(expected_generation):
                        raise AccountRegistryError("Original managed credential changed during observation")
                    require_qualified()  # Locks/file reads may wait; no carried authority clock.
                    return values
        return ReadView()

    def public(self) -> list[dict[str, Any]]:
        return [a.public() for a in sorted(self.accounts.values(), key=lambda x: x.alias)]
