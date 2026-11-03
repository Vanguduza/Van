"""Account onboarding commands for the commander (Rev 5 Part B, owner-directed: accounts are
configured from the Van app, not the CLI).

Every command here writes only two places on van-trading-core: the non-secret account
registry and the alias' 0600 secrets file. Secrets arrive over the commander's signed
channel, are written with `os.open(..., 0o600)`, and are never echoed back, logged or
audited by value. Broker network calls (Deriv account opening, cTrader discovery,
connectivity verification) run here on the VM because the VM is the host with venue
egress; they are injectable for tests."""

from __future__ import annotations

import json
import os
import re
import secrets as pysecrets
import time
import tempfile
import hashlib
from dataclasses import dataclass, field, replace
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException
from commander.account_config import resolve_account_config,validate_deriv_endpoint,require_initial_observe
from commander.account_effects import (AccountEffectError, AccountEffectJournal, AccountOperationUnconfirmed,
    AccountOperationBlocked, JOURNALED_COMMANDS, invoke_account_effect, mark_account_effect, operation_intent, readback,
    require_current_account_effect)

ALIAS_RE = re.compile(r"^[a-z0-9_]{3,32}$")
BROKER_SECRET_KEYS = {
    "DERIV": {"DERIV_API_TOKEN", "DERIV_APP_ID"},
    "CTRADER": {"CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN", "CTRADER_REFRESH_TOKEN"},
    "MT5_EA": {"BRIDGE_SIGNING_KEY"},
    "MT5": {"BRIDGE_SIGNING_KEY", "BRIDGE_CA_FILE", "BRIDGE_CLIENT_CERT", "BRIDGE_CLIENT_KEY"},
    "PAPER": set(), "ZSE_OWNER_TICKET": set(),
}
ACCOUNT_MUTATIONS = frozenset({"account_restrict", "account_upsert", "account_credentials", "account_remove",
    "deriv_create_demo", "deriv_oauth_link", "ctrader_link", "mt5_ea_issue_key"})
ACCOUNT_COMMANDS = ("account_restrict", "account_upsert", "account_credentials", "account_remove", "account_verify", "account_revision", "account_review", "account_operation", "deriv_verify_email", "deriv_create_demo", "deriv_oauth_link", "ctrader_discover", "ctrader_oauth_exchange", "ctrader_link", "mt5_ea_issue_key")
ACCOUNT_TOOL_SCHEMAS = {
    "account_restrict": {"description":"Existing enrolled-device A4 and Store admission required; recovery also requires distinct fresh purpose-bound reauthentication. Metadata never grants mode, mandate or entry authority.",
        "properties":{"alias":{"type":"string","pattern":"^[a-z0-9_]{3,32}$"},
            "variant":{"enum":["RESTRICT","BEGIN_REAUTH","COMPLETE_REAUTH","RECONCILE_DATA"]},
            "reason_code":{"enum":["OWNER_REQUEST","CREDENTIALS_EXPIRED","BROKER_DISABLED","KILL_SWITCH","VERIFICATION_FAILED"]},
            "restriction_id":{"type":"string","pattern":"^[A-Za-z0-9_-]{20,128}$"},
            "expected_revision":{"type":"integer","minimum":0},"expected_digest":{"type":"string","pattern":"^[0-9a-f]{64}$"},
            "parent_operation_id":{"type":"string","pattern":"^[A-Za-z0-9_-]{20,128}$"},
            "reauth_fact_id":{"type":"string","pattern":"^[A-Za-z0-9_-]{20,128}$"},
            "reauth_fact_digest":{"type":"string","pattern":"^[0-9a-f]{64}$"}},"required":["alias","variant"],"additionalProperties":False},
    "account_review": {"description": "Resolve exact public before/after settings or local-unlink safety facts without broker effects. Native readonly checks may use host credentials; credential values and locators are never exported.", "properties": {"action": {"type": "string"}, "args": {"type": "object"}}, "required": ["action", "args"]},
    "account_operation": {"description": "Read the original native account-operation outcome for its gateway-authenticated owner device and selected native control domain. No effect or credential export; domain data confers no authority.", "properties": {"operation_id": {"type": "string"}, "device_id": {"type": "string"}, "account_control_domain": {"type":"string","pattern":"^[0-9a-f]{64}$"}}, "required": ["operation_id", "device_id"]},
    "account_revision": {"description": "Read the authenticated native account-control state namespace and, when alias is supplied, its exact configuration version. Namespace data confers no authority.", "properties": {"alias": {"type": "string"}}},
    "account_upsert": {"description": "Register a new account or edit specified public settings. Existing omitted settings and credentials are preserved. New accounts require broker and start OBSERVE; explicit other initial modes are refused. Existing mode controls and native identity migration remain separate.", "properties": {"alias": {"type": "string"}, "broker": {"type": "string"}, "mode": {"type": "string", "description": "New accounts require OBSERVE; omitted existing mode is retained."}, "currency": {"type": "string"}, "label": {"type": "string"}, "server": {"type": "string"}, "login": {"type": "string"}, "bridge_url": {"type": "string"}, "demo": {"type": "boolean"}, "enabled": {"type": "boolean"}, "notes": {"type": "string"}, "venue": {"type": "string"}, "mandate_ref": {"type": "string"}}, "required": ["alias"]},
    "account_credentials": {"description": "Store credential values for an alias in its 0600 secrets file (allowlisted keys per broker). Values are never echoed.", "properties": {"alias": {"type": "string"}, "secrets": {"type": "object"}}, "required": ["alias", "secrets"]},
    "account_remove": {"description": "IMMEDIATE_DISCONNECT requires fresh purpose-bound reauthentication plus separate substantive A4 approval and fresh native safety facts; alias-only removal is refused. PENDING_CLEANUP is a separately reauthenticated and A4-approved original-device child bound to its genuine private plan; it never replays or completes the UNKNOWN parent. History/remote accounts/funds remain; no provider closure or money movement. DELETE_GRACE and CANCEL_DELETE use distinct purpose-bound reauthentication DATA plus separate substantive permission, explicit owner-selected grace, and per-incarnation metadata/detachment; cancellation never restores credentials or strategy eligibility.", "properties": {"alias": {"type": "string"},
        "variant":{"enum":["PENDING_CLEANUP","DELETE_GRACE","CANCEL_DELETE","IMMEDIATE_DISCONNECT"]},"grace_seconds":{"type":"integer","minimum":1},"lifecycle_id":{"type":"string"},"expected_revision":{"type":"integer"},"expected_digest":{"type":"string"},"parent_operation_id":{"type":"string","pattern":"^[A-Za-z0-9_-]{20,128}$"},
        "plan_ref":{"type":"string","pattern":"^[0-9a-f]{64}$"},"retire_parent_safety_obligation":{"type":"boolean"},
        "reauth_fact_id":{"type":"string","pattern":"^[A-Za-z0-9_-]{20,128}$"},
        "reauth_fact_digest":{"type":"string","pattern":"^[0-9a-f]{64}$"}}, "required": ["alias"]},
    "account_verify": {"description": "Connect to the venue with the stored credentials and report equity/currency/connectivity. No order is placed.", "properties": {"alias": {"type": "string"}}, "required": ["alias"]},
    "deriv_verify_email": {"description": "Start Deriv account opening: send the verification email.", "properties": {"email": {"type": "string"}, "app_id": {"type": "string"}}, "required": ["email"]},
    "deriv_create_demo": {"description": "Create a Deriv virtual (demo) account from the emailed code and register it in OBSERVE; trading mode needs the existing separate controls.", "properties": {"alias": {"type": "string"}, "mode": {"type": "string", "enum": ["OBSERVE"], "default": "OBSERVE"}, "email": {"type": "string"}, "verification_code": {"type": "string"}, "client_password": {"type": "string"}, "residence": {"type": "string"}, "app_id": {"type": "string"}}, "required": ["alias", "verification_code", "client_password", "residence"]},
    "deriv_oauth_link": {"description": "Register a Deriv account in OBSERVE from OAuth redirect tokens; token trade scope does not activate trading.", "properties": {"alias": {"type": "string"}, "mode": {"type": "string", "enum": ["OBSERVE"], "default": "OBSERVE"}, "loginid": {"type": "string"}, "token": {"type": "string"}, "currency": {"type": "string"}, "app_id": {"type": "string"}, "label": {"type": "string"}}, "required": ["alias", "loginid", "token"]},
    "ctrader_discover": {"description": "List cTrader accounts reachable with an access token (demo and live).", "properties": {"client_id": {"type": "string"}, "client_secret": {"type": "string"}, "access_token": {"type": "string"}}, "required": ["client_id", "client_secret", "access_token"]},
    "ctrader_oauth_exchange": {"description": "Exchange a cTrader OAuth code for tokens.", "properties": {"client_id": {"type": "string"}, "client_secret": {"type": "string"}, "code": {"type": "string"}, "redirect_uri": {"type": "string"}}, "required": ["client_id", "client_secret", "code", "redirect_uri"]},
    "ctrader_link": {"description": "Register a cTrader account (ctid) in OBSERVE with its application credentials and tokens.", "properties": {"alias": {"type": "string"}, "mode": {"type": "string", "enum": ["OBSERVE"], "default": "OBSERVE"}, "client_id": {"type": "string"}, "client_secret": {"type": "string"}, "access_token": {"type": "string"}, "refresh_token": {"type": "string"}, "ctid_trader_account_id": {"type": "integer"}, "is_live": {"type": "boolean"}, "label": {"type": "string"}, "currency": {"type": "string"}}, "required": ["alias", "client_id", "client_secret", "access_token", "ctid_trader_account_id"]},
    "mt5_ea_issue_key": {"description": "Register a new MT5 account in OBSERVE or rotate an existing bridge key without changing its omitted mode, mandate or native identity. New registration requires login and server; existing key rotation may omit them. Signing key is returned once for the EA inputs.", "properties": {"alias": {"type": "string"}, "mode": {"type": "string", "description": "New initial mode must be OBSERVE; an existing mode may only be confirmed, never changed by key rotation."}, "login": {"type": "string"}, "server": {"type": "string"}, "label": {"type": "string"}, "currency": {"type": "string"}, "demo": {"type": "boolean"}}, "required": ["alias"]},
}


@dataclass
class AccountControlSettings:
    registry_path: str
    secrets_dir: str
    deriv_connector: Optional[Callable[[str], Any]] = None                          # url → socket-like (tests); None = real websockets
    ctrader_transport_factory: Optional[Callable[[bool], Any]] = None               # is_live → CtraderTransport
    ctrader_http: Optional[Callable[[str, dict], dict]] = None
    verify_timeout_s: float = 20.0
    operation_ledger: str = ""  # Actual constructors bind the existing native VATI ledger.
    lifecycle_session_sources: tuple | None = None  # Exact native configured (path,SHA256) scope; missing HOLD.
    lifecycle_remote_state_reader: Optional[Callable] = None  # Independent original-incarnation observation; no credential restoration.

    lifecycle_admission_verifier: Optional[Callable] = None  # Trusted local Gateway bootstrap; never command DATA.
    lifecycle_transport_binding: Any = None  # Unique Commander ingress identity; no direct-handler default.
    restriction_admission_verifier: Optional[Callable] = None  # Actual Store-bound local owner.
    restriction_read_verifier: Optional[Callable] = None
    restriction_transport_binding: Any = None  # Authenticated ingress marker only; no issuer.

    def __post_init__(self):
        if self.lifecycle_session_sources is None:
            from commander.account_lifecycle import configured_session_scope
            self.lifecycle_session_sources=configured_session_scope(
                os.environ.get('VAN_ACCOUNT_LIFECYCLE_SESSION_SCOPE_FILE',''),self.registry_path)


def _secrets_path(st: AccountControlSettings, alias: str) -> Path:
    return Path(st.secrets_dir) / f"{alias}.env"


def _write_secrets(path: Path, values: dict[str, str], *, merge: bool = True, before_replace=None, before_effect=None) -> None:
    from vati.core.file_lock import exclusive_state_lock
    from vati.accounts.registry import load_secret_file

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k)
           or not isinstance(v, str) or "\n" in v or "\r" in v for k, v in values.items()):
        raise ValueError("credential file requires valid keys and single-line text values")
    with exclusive_state_lock(path):
        if before_replace is not None:before_replace()
        if path.is_symlink():
            raise ValueError("credential destination must not be a symbolic link")
        # Validate old ownership/permissions even when replacing, before reading or changing it.
        old = load_secret_file(str(path)) if path.exists() else {}
        existing = old if merge else {}
        existing.update(values)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                for key, value in existing.items():
                    stream.write(f"{key}={value}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            if before_replace is not None:before_replace()
            if before_effect is not None:before_effect()
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _file_generation(stat):
    return (stat.st_dev,stat.st_ino,stat.st_mode,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


def _shred(path: Path, *, before_write=None, before_unlink=None, expected_generation=None, before_effect=None, after_write=None, after_unlink=None) -> None:
    from vati.core.file_lock import exclusive_state_lock
    with exclusive_state_lock(path):
        if path.is_symlink():
            raise ValueError("credential destination must not be a symbolic link")
        if expected_generation is not None and not path.is_file():
            raise HTTPException(409,'Original managed credential is missing; cleanup unconfirmed')
        if path.is_file():
            with open(path, "r+b") as stream:
                before=_file_generation(os.fstat(stream.fileno()))
                if (expected_generation is not None and before!=expected_generation
                    or _file_generation(path.stat())!=before):
                    raise HTTPException(409,'Managed credential generation changed before destruction')
                if before_write is not None:before_write()
                if path.is_symlink() or _file_generation(path.stat())!=before:
                    raise HTTPException(409,'Managed credential changed at original overwrite boundary')
                if before_effect is not None:before_effect()
                stream.write(os.urandom(before[3]))
                stream.flush()
                os.fsync(stream.fileno())
                own_overwrite=_file_generation(os.fstat(stream.fileno()))
                if after_write is not None:after_write(own_overwrite)
            if path.is_symlink() or _file_generation(path.stat())!=own_overwrite:
                raise HTTPException(409,'Managed credential changed after original overwrite; cleanup unconfirmed')
            if before_unlink is not None:before_unlink()
            if path.is_symlink() or _file_generation(path.stat())!=own_overwrite:
                raise HTTPException(409,'Managed credential changed at original unlink boundary')
            if before_effect is not None:before_effect()
            path.unlink()
            if after_unlink is not None:
                directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
                after_unlink()



def _alias(a: dict) -> str:
    alias = str(a.get("alias", "")).strip().lower()
    if not ALIAS_RE.match(alias):
        raise HTTPException(422, "alias must match [a-z0-9_]{3,32}")
    return alias


def require_resource_version(command: str, args: dict, *, server_owned_demo=False) -> None:
    """Required on actual gateway/Commander ingress; direct handlers are native code."""
    if command not in ACCOUNT_MUTATIONS:
        return
    _alias(args)
    expected = args.get("_expected_resource_version")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise HTTPException(409, "native account resource version is required before mutation")
    if command in JOURNALED_COMMANDS and not (
        command=='deriv_create_demo' and server_owned_demo and '_native_operation' not in args):
        try:
            operation_intent(command, args)
        except AccountEffectError as exc:
            raise HTTPException(409, str(exc)) from None
    if command in {'account_upsert','account_remove','account_restrict'}:
        review=args.get("_expected_review_digest")
        authority=args.get("_native_operation",{}).get("authority_ref","")
        if not isinstance(review,str) or not re.fullmatch(r"[0-9a-f]{64}",review) or not authority.endswith("::review:"+review):
            raise HTTPException(409,"Resolved native owner review is required before an account edit")


def _boolean(args: dict, name: str, default: bool) -> bool:
    value = args.get(name, default)
    if type(value) is not bool:
        raise HTTPException(422, f"{name} must be a JSON boolean")
    return value


def build_account_handlers(st: AccountControlSettings, *, retained_jobs=None) -> dict[str, Callable[[dict], dict]]:
    from vati.accounts import Account, AccountRegistry, AccountRegistryError, CredentialRef
    if retained_jobs is None:
        from vati.funding.retained_history import RetainedHistoryJobs
        retained_jobs = RetainedHistoryJobs()

    def reg() -> AccountRegistry:
        return AccountRegistry(st.registry_path)

    def upsert_record(alias: str, broker: str, *, mode: str | None = None, currency: str = "USD", label: str = "", server: str = "", login: str = "", bridge_url: str = "", demo: bool = True, mandate_ref: str | None = None, before_write=None, after_write=None) -> dict:
        r = reg()
        current = r.accounts.get(alias)
        require_initial_observe({} if mode is None else {'mode':mode},current=current)
        mode = mode if mode is not None else (current.mode if current is not None else 'OBSERVE')
        mandate_ref = mandate_ref if mandate_ref is not None else (current.mandate_ref if current is not None else '')
        sec = _secrets_path(st, alias)
        if broker in ("DERIV", "CTRADER", "MT5_EA", "MT5"):
            if not sec.is_file():
                _write_secrets(sec, {},before_replace=before_write,before_effect=mark_account_effect)
            cref = CredentialRef(secrets_file=str(sec))
        else:
            cref = CredentialRef()
        try:
            values={'broker':broker,'mode':mode,'currency':currency,'label':label if current is not None else label or alias,
                'server':server,'login':login,'bridge_url':bridge_url,'demo':demo,'mandate_ref':mandate_ref}
            candidate=(replace(current,**values) if current is not None else Account(alias=alias,credential_ref=cref,**values))
            candidate.validate()
            def before_registry_replace():
                if before_write is not None:before_write()
                mark_account_effect()
            with r._mutation_lock():
                acc = r.replace(candidate,before_replace=before_registry_replace) if alias in r.accounts else r.add(candidate,before_replace=before_registry_replace)
                if after_write is not None:after_write(current_resource_version(alias))
        except AccountRegistryError as exc:
            raise HTTPException(422, str(exc))
        return acc.public()

    def clean_secrets(broker: str, values: dict[str, Any]) -> dict[str, str]:
        allowed = BROKER_SECRET_KEYS.get(broker, set())
        bad = [k for k in values if k not in allowed]
        if bad:
            raise HTTPException(422, f"keys not allowed for {broker}: {sorted(bad)}")
        clean = {k: str(v).strip() for k, v in values.items() if str(v).strip()}
        if any("\n" in v or "\r" in v for v in clean.values()):
            raise HTTPException(422, "secret values must be single-line")
        return clean

    def store_secrets(alias: str, broker: str, values: dict[str, Any], *, before_write=None, expected_version=None) -> list[str]:
        clean = clean_secrets(broker, values)
        mark_account_effect()
        if before_write is None:
            reg().touch(alias)
            _write_secrets(_secrets_path(st, alias), clean)
        else:
            with reg()._mutation_lock():
                before_write()
                if expected_version is not None and current_resource_version(alias)!=expected_version:
                    raise HTTPException(409,'Account changed after original link registration; credentials were not replaced')
                reg().touch(alias)
                _write_secrets(_secrets_path(st, alias), clean,before_replace=before_write)
        return sorted(clean)

    def verify_deriv_material(*, app_id: str, token: str, login: str, currency: str,
                              demo: bool | None, require_trade: bool, endpoint: str = "") -> dict:
        validate_deriv_endpoint(endpoint)
        from vati.execution.deriv_identity import DerivIdentity, DerivIdentityError
        from vati.execution.transports.deriv_ws import DerivWebSocketTransport
        transport = DerivWebSocketTransport(app_id=app_id, token_provider=lambda: token,
            endpoint=endpoint or "wss://ws.derivws.com/websockets/v3",
            timeout_s=st.verify_timeout_s, connector=st.deriv_connector)
        try:
            response = transport({"authorize": "<token-from-vault-never-in-prompt>"})
            profile = response.get("authorize", {})
            virtual = profile.get("is_virtual")
            if type(virtual) is not int or virtual not in (0, 1):
                raise DerivIdentityError("Deriv native demo/live identity is unavailable")
            identity = DerivIdentity(login or profile.get("loginid", ""), currency,
                                     bool(virtual) if demo is None else demo, require_trade)
            identity.validate(profile)
            return profile
        except Exception:
            # An authorization read has no money effect. Do not include a raw
            # broker exception or echo_req: either can contain credential data.
            raise HTTPException(409, "Deriv credential or native account identity could not be verified; previous connection retained") from None
        finally:
            transport.close()

    def require_new_alias(alias: str) -> None:
        if alias in reg().accounts:
            raise HTTPException(409, "account alias already exists; use the approved account update flow")

    # ------------------------------------------------------------ generic
    def control_domain(native_ledger=None):
        """Current protected state correlation; never retrospective authority."""
        from vati.accounts.registry import load_secret_file
        from vati.core.file_lock import exclusive_state_lock
        from commander.account_effects import PRODUCER,SCHEMA
        from vati.core.events import EventKind,make_event
        path=Path(st.secrets_dir)/'.account-control-domain.env'
        led=native_ledger if native_ledger is not None else open_operation_ledger()
        try:
            with exclusive_state_lock(path):
                with led.atomic():
                    states=AccountEffectJournal(led,cleanup_secrets_root=st.secrets_dir)._states()
                    hints={target.split(':',1)[1] for state in states.values() for target in state.intent.targets
                        if target.startswith('account-control-domain:')}
                    hints.update(event.payload['account_control_domain'] for event in led.iter(EventKind.ACCOUNT_OPERATION)
                        if AccountEffectJournal.internal_namespace_metadata(event))
                    if len(hints)>1 or any(not re.fullmatch(r'[0-9a-f]{64}',hint) for hint in hints):
                        raise AccountOperationBlocked('Native account-control namespace conflicts; reconcile original state')
                    if path.is_symlink():raise AccountOperationBlocked('Native account-control namespace vault is unsafe')
                    missing=not path.exists()
                    if not missing and not hints:
                        raise AccountOperationBlocked('Immutable native account-control namespace hint is unavailable')
                    domain=(next(iter(hints)) if hints else pysecrets.token_hex(32)) if missing else load_secret_file(str(path)).get('ACCOUNT_CONTROL_DOMAIN','')
                    if not re.fullmatch(r'[0-9a-f]{64}',domain) or hints and hints!={domain}:
                        raise AccountOperationBlocked('Native account-control namespace continuity is unknown')
                    if not hints:
                        # Controlled one-time CURRENT-state metadata migration.
                        # The explicit INTERNAL row has no business intent,
                        # APPLIED phase, account revision or issuer principal.
                        # Legacy originals remain unbound and all their native
                        # uncertainty/provider fences continue to apply.
                        stamp=int(time.time())
                        led.append(make_event(EventKind.ACCOUNT_OPERATION,PRODUCER,
                            {'schema':SCHEMA,'record_type':'INTERNAL_NAMESPACE_METADATA',
                             'account_control_domain':domain,'legacy_originals_bound':False,'authority_issued':False},
                            event_time_ms=stamp*1000,received_time_ms=stamp*1000,
                            correlation_id='internal-account-control-namespace'))
                # Commit the immutable hint BEFORE attempting vault persistence.
                # A lost commit acknowledgement/write failure restores the same
                # unique hint on retry, rather than minting an independent ID.
                if missing:_write_secrets(path,{'ACCOUNT_CONTROL_DOMAIN':domain},merge=False)
                return domain
        except HTTPException:raise
        except Exception:
            raise AccountOperationBlocked('Native account-control namespace cannot be verified; reconciliation required') from None
        finally:
            if native_ledger is None:led.close()

    def current_resource_version(alias):
        from vati.accounts.resource_version import resource_snapshot
        return resource_snapshot(reg(),alias)['resource_version']

    def cmd_account_revision(a: dict) -> dict:
        from vati.accounts.resource_version import resource_snapshot
        domain=control_domain()
        if 'alias' not in a:return {'account_control_domain':domain}
        snapshot=resource_snapshot(reg(), _alias(a))
        return {**snapshot,'account_control_domain':domain}

    def retirement_review(values,*,inside_removal=False,native_ledger=None,readback_guards=None):
        from commander.account_retirement import inspect_retirement,require_idle_runtime,authority_path
        from vati.core.ledger_pg import open_ledger
        from vati.core.canonical import canonical_hash
        alias=_alias(values)
        # Never wait for the runtime lease while holding the alias lock: the
        # router holds its lease before entering the account submission fence.
        if not inside_removal:require_idle_runtime(st,alias)
        # Initialize authority storage before alias/lease locks. Reopening a PG
        # ledger under its lease guard could wait on DDL held by this same call.
        ledger=native_ledger if native_ledger is not None else open_ledger(authority_path(st))
        try:
            with reg().operation_lock(alias):
                registry=reg()
                try:current=registry.get(alias)
                except Exception:raise HTTPException(404,'Unknown native account alias') from None
                facts=inspect_retirement(st,registry,current,inside_removal=True,native_ledger=ledger,
                    operation_id=(values.get('_native_operation') or {}).get('operation_id'),
                    **({'readback_guards':readback_guards} if readback_guards is not None else {}))
                body={'schema':'vati.account-review/1','action':'account_remove','alias':alias,
                    'request_digest':canonical_hash({k:v for k,v in values.items() if not k.startswith('_')}),
                    'resource_version':current_resource_version(alias),
                    'before':current.public(),'after':None,'changed_fields':['local_link'],'retirement':facts}
                return {**body,'review_digest':canonical_hash(body)}
        finally:
            if native_ledger is None:ledger.close()

    def lifecycle_call(method, args, device=None, guard=None):
        from commander.account_lifecycle import NativeLifecycle
        if method=="archive_due" and not reg()._lifecycles:return {"archived":0}
        ledger=open_operation_ledger()
        try:
            service=NativeLifecycle(st,ledger,control_domain,retirement_review,current_resource_version)
            service.retained_jobs=retained_jobs
            if method=='review':return service.review(args,device,guard)
            if method=='read':
                if 'view' in args:return service.financial_history(args,device,guard)
                return service.read(args['alias'],device,guard,args.get('lifecycle_id'))
            if method=='archive_due':
                # Only previously admitted local metadata; no credential or
                # provider effect, filesystem scan, new permission or history.
                current=reg();rows=list(current._lifecycles.values())+list(current._lifecycle_history.values())
                return {'archived':sum(service.archive_due(row['alias'],row['operation_id']) for row in rows)}
            return service.execute(args,guard)
        finally:ledger.close()

    def restriction_call(method, payload):
        from commander.account_restrictions import NativeRestriction, _GatewayRestrictionAdmission, _GatewayRestrictionRead
        # Refuse unbound direct ingress before opening any operation ledger.
        field='restriction_admission_verifier' if method=='execute' else 'restriction_read_verifier'
        marker=payload.get('_restriction_admission_guard' if method=='execute' else '_restriction_read_guard')
        marker_type=_GatewayRestrictionAdmission if method=='execute' else _GatewayRestrictionRead
        binding=st.restriction_transport_binding
        if not callable(getattr(st,field,None)) and (binding is None or type(marker) is not marker_type or marker.binding is not binding):
            raise HTTPException(403,{'code':'RESTRICTION_CURRENT_GATEWAY_OWNER_REQUIRED'})
        ledger=open_operation_ledger()
        try:
            service=NativeRestriction(st,ledger,control_domain,current_resource_version)
            return getattr(service,method)(payload)
        finally:ledger.close()

    def cmd_account_review(a: dict) -> dict:
        from vati.core.canonical import canonical_hash
        restriction_methods={'account_restriction_review':'review','account_restriction_read':'read',
            'account_restriction_pending':'pending','account_restriction_resolution':'resolution'}
        if a.get('action') in restriction_methods:return restriction_call(restriction_methods[a['action']],a)
        if a.get("action") in {"account_lifecycle_read","account_lifecycle_archive_due"}:
            return lifecycle_call("read" if a["action"]=="account_lifecycle_read" else "archive_due",a.get("args",{}),a.get("owner_device_id"),a.get("_account_dispatch_guard"))
        if a.get('action')=='account_remove' and isinstance(a.get('args'),dict):
            if 'variant' in a['args'] and (not isinstance(a['args']['variant'],str) or a['args']['variant'] not in {'PENDING_CLEANUP','DELETE_GRACE','CANCEL_DELETE','IMMEDIATE_DISCONNECT'}):
                raise HTTPException(422,'Unknown native account retirement variant')
            if a["args"].get("variant") in {"DELETE_GRACE","CANCEL_DELETE","IMMEDIATE_DISCONNECT"}:
                return lifecycle_call("review",a["args"],a.get("owner_device_id"),a.get("_account_dispatch_guard"))
            if a['args'].get('variant')=='PENDING_CLEANUP':
                from commander.account_cleanup import NativeCleanup
                ledger=open_operation_ledger()
                try:return NativeCleanup(st,ledger,reg,control_domain).review(a['args'],a.get('owner_device_id'),a.get('_account_dispatch_guard'))
                except AccountEffectError:
                    raise AccountOperationBlocked('Original local cleanup plan or current evidence is unavailable; HOLD') from None
                finally:ledger.close()
            return retirement_review(a['args'])
        if a.get('action')!='account_upsert' or not isinstance(a.get('args'),dict):
            raise HTTPException(422,'Unsupported native account review action')
        values=a['args']; alias=_alias(values)
        with reg().operation_lock(alias):
            registry=reg(); current=registry.accounts.get(alias)
            candidate=resolve_account_config({k:v for k,v in values.items() if k not in {'_expected_account_control_domain','_upsert_before_write','_account_dispatch_guard'}},alias=alias,current=current,secret_path=_secrets_path(st,alias))
            if alias in registry._restrictions and candidate.enabled:
                raise HTTPException(409,{'code':'RESTRICTION_ENTRY_ACTIVATION_REQUIRES_EXISTING_GOVERNED_CONTROL'})
            before=current.public() if current else None; after=candidate.public()
            public_args={key:value for key,value in values.items() if not key.startswith('_')}
            body={'schema':'vati.account-review/1','action':'account_upsert','alias':alias,
                'request_digest':canonical_hash(public_args),
                'resource_version':cmd_account_revision({'alias':alias})['resource_version'],
                'before':before,'after':after,
                'changed_fields':sorted(key for key,value in after.items() if before is None or before.get(key)!=value)}
            return {**body,'review_digest':canonical_hash(body)}

    def open_operation_ledger():
        from vati.core.ledger_pg import open_ledger
        if not st.operation_ledger:
            raise HTTPException(503, "native VATI operation ledger is not configured; no effect dispatched")
        return open_ledger(st.operation_ledger)

    def cmd_account_operation(a: dict) -> dict:
        led = open_operation_ledger()
        try:
            state = AccountEffectJournal(led,cleanup_secrets_root=st.secrets_dir).status(a.get("operation_id"), a.get("device_id"))
            if state is not None and state.intent.command=='account_remove':
                from commander.account_cleanup import UnlinkRecoveryBook,continuity,unknown
                parent=(state.result or {}).get('cleanup_parent_operation_id',state.intent.operation_id)
                original=UnlinkRecoveryBook(led,initialize=False,secrets_root=st.secrets_dir)._history(parent)['plan']
                if original is not None and continuity(st,reg())!=original.payload['data']['continuity']:raise unknown()
            current=control_domain(led)
            if a.get('account_control_domain') not in (None,current):
                raise AccountOperationBlocked('Original account-control namespace is not selected')
            if state is None:
                # Absence does not prove a lost request can never arrive.
                raise AccountOperationUnconfirmed(a.get("operation_id"))
            result=readback(state)
            if state.intent.command=='account_remove':
                from commander.account_cleanup import UnlinkRecoveryBook
                parent=(state.result or {}).get('cleanup_parent_operation_id',state.intent.operation_id)
                summary=UnlinkRecoveryBook(led,initialize=False,secrets_root=st.secrets_dir).summary(parent,state.intent.device_id)
                if summary['plan_ref'] is not None:result['cleanup_recovery']=summary
            return result
        except AccountEffectError:
            raise HTTPException(409, "native operation cannot be read for this owner device") from None
        finally:
            led.close()

    def cmd_account_upsert(a: dict) -> dict:
        if '_expected_review_digest' in a:
            review=cmd_account_review({'action':'account_upsert','args':a})
            if review['review_digest']!=a['_expected_review_digest']:
                raise HTTPException(409,'Resolved account settings changed since owner review; current connection retained')
        alias = _alias(a)
        registry=reg(); current=registry.accounts.get(alias)
        candidate=resolve_account_config({k:v for k,v in a.items() if k not in {'_expected_account_control_domain','_upsert_before_write','_account_dispatch_guard'}},alias=alias,current=current,secret_path=_secrets_path(st,alias))
        def check_upsert_current():
            guard=a.get('_upsert_before_write')
            if callable(guard):guard()
            if '_native_operation' in a:require_current_account_effect()
        def before_upsert_replace():
            check_upsert_current()
            mark_account_effect(require_current=True)
        if current is None and candidate.credential_ref.secrets_file:
            _write_secrets(Path(candidate.credential_ref.secrets_file),{},before_replace=check_upsert_current,before_effect=before_upsert_replace)
        account=registry.replace(candidate,before_replace=before_upsert_replace) if current else registry.add(candidate,before_replace=before_upsert_replace)
        return {"account":account.public(),"secrets_file":candidate.credential_ref.secrets_file}

    def cmd_account_credentials(a: dict) -> dict:
        alias = _alias(a)
        registry = reg()
        try:
            acc = registry.get(alias)
        except AccountRegistryError as exc:
            raise HTTPException(404, str(exc))
        values = a.get("secrets")
        if not isinstance(values, dict) or not values:
            raise HTTPException(422, "secrets must be a non-empty object")
        if acc.broker == "DERIV":
            from vati.accounts.access import SENDING_MODES
            clean = clean_secrets(acc.broker, values)
            expected_path = _secrets_path(st, alias).resolve()
            if not acc.credential_ref.secrets_file or Path(acc.credential_ref.secrets_file).resolve() != expected_path:
                raise HTTPException(409, "credential rotation must use the registered credential reference")
            candidate = {**registry.credentials(alias), **clean}
            app_id = acc.server or "1089"
            if candidate.get("DERIV_APP_ID", app_id) != app_id:
                raise HTTPException(409, "credential app ID differs from the registered connection")
            profile = verify_deriv_material(app_id=app_id, token=candidate.get("DERIV_API_TOKEN", ""),
                login=acc.login, currency=acc.currency, demo=acc.demo,
                require_trade=acc.mode in SENDING_MODES, endpoint=acc.bridge_url)
            # Pin an initially unbound account only after native readback. This
            # happens under the account-operation lock, before an entry can run.
            # A failed subsequent file swap leaves an identity whose old token
            # must still pass native verification; it cannot switch principals.
            if not acc.login:
                mark_account_effect()
                registry.replace(replace(acc, login=profile["loginid"]))
        keys = store_secrets(alias, acc.broker, values)
        return {"alias": alias, "stored_keys": keys}

    def cmd_account_remove(a: dict,*,native_ledger=None) -> dict:
        raise HTTPException(422,'Legacy alias-only removal has no two-proof lifecycle authority')

    def cmd_account_verify(a: dict) -> dict:
        alias = _alias(a)
        r = reg()
        try:
            acc = r.get(alias)
        except AccountRegistryError as exc:
            raise HTTPException(404, str(exc))
        if acc.broker == "MT5_EA":
            from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
            q = BridgeQueue(os.environ.get("VAN_MT5_PULL_QUEUE", ":memory:"))
            hb = Mt5PullAdapter(q, account_alias=alias).heartbeat(now_ms=int(time.time() * 1000))
            return {"alias": alias, "ok": hb.connected, "detail": "EA is polling" if hb.connected else "EA has not polled in the last 30 s; check BridgeUrl/Alias/SigningKey in the terminal", "safety_identity": acc.safety_identity}
        try:
            from vati.app.service import build_adapter
            adapter = build_adapter(acc, r, deriv_connector=st.deriv_connector)
            if st.ctrader_transport_factory and acc.broker == "CTRADER":
                adapter.transport = st.ctrader_transport_factory(not acc.demo)
            state = adapter.sync_account()
            hb = adapter.heartbeat(now_ms=int(time.time() * 1000))
            return {"alias": alias, "ok": bool(state.verified and hb.connected), "equity": str(state.equity), "balance": str(state.balance), "currency": state.currency, "verified": state.verified, "connected": hb.connected, "safety_identity": acc.safety_identity}
        except Exception as exc:  # noqa: BLE001 — verification must report, not crash
            return {"alias": alias, "ok": False, "detail": str(exc)[:300], "safety_identity": acc.safety_identity}

    # ------------------------------------------------------------ deriv
    def deriv_transport(app_id: str):
        from vati.execution.transports.deriv_ws import DerivWebSocketTransport
        return DerivWebSocketTransport(app_id=app_id, token_provider=lambda: "", connector=st.deriv_connector)

    def cmd_deriv_verify_email(a: dict) -> dict:
        email = str(a.get("email", "")).strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(422, "valid email required")
        t = deriv_transport(str(a.get("app_id") or "1089"))
        r = t({"verify_email": email, "type": "account_opening"})
        if r.get("error"):
            raise HTTPException(502, f"Deriv: {r['error']}")
        return {"sent": bool(r.get("verify_email")), "email": email}

    def cmd_deriv_create_demo(a: dict) -> dict:
        alias = _alias(a)
        require_initial_observe(a,current=reg().accounts.get(alias))
        require_new_alias(alias)
        app_id = str(a.get("app_id") or "1089")
        if (not str(a.get("verification_code", "")).strip()
            or not isinstance(a.get("client_password"), str) or not a["client_password"]
            or not re.fullmatch(r"[a-zA-Z]{2}", str(a.get("residence", "")))
            or not re.fullmatch(r"[0-9]+", app_id)):
            raise HTTPException(422, "Demo creation needs a verification code, password, residence and valid app ID")
        t = deriv_transport(app_id)
        def possible_send():
            require_current_account_effect()
            mark_account_effect()
        try:
            require_current_account_effect()
            r = t({"new_account_virtual": 1, "verification_code": str(a["verification_code"]).strip(), "client_password": a["client_password"], "residence": str(a["residence"]).lower(), "type": "trading"},before_send=possible_send)
        finally:
            t.close()
        if r.get("error"):
            raise HTTPException(502, f"Deriv: {r['error']}")
        nav = r.get("new_account_virtual")
        if (not isinstance(nav, dict) or any(not isinstance(nav.get(key), str) or not nav[key].strip()
            for key in ('client_id','currency','oauth_token'))):
            raise HTTPException(502, "Original demo creation returned incomplete native identity; reconciliation required")
        token = nav['oauth_token']
        verify_deriv_material(app_id=app_id, token=token, login=str(nav.get("client_id", "")),
            currency=str(nav.get("currency", "USD")), demo=True, require_trade=True)
        upsert_record(alias, "DERIV", currency=str(nav.get("currency", "USD")), label=str(a.get("label") or f"Deriv demo {nav.get('client_id', '')}"), server=app_id, login=str(nav.get("client_id", "")), demo=True)
        store_secrets(alias, "DERIV", {"DERIV_API_TOKEN": token, "DERIV_APP_ID": app_id})
        # Complete only from persisted material and independent native identity
        # readback. A failure after remote creation stays UNKNOWN, even if the
        # local record exists; an absent record never proves remote no-effect.
        saved = reg()
        account = saved.get(alias)
        material = saved.credentials(alias)
        verify_deriv_material(app_id=app_id, token=material.get("DERIV_API_TOKEN", ""),
            login=account.login, currency=account.currency, demo=True, require_trade=True)
        if (account.broker != "DERIV" or not account.demo or account.mode != "OBSERVE"
            or account.server != app_id or account.login != str(nav.get("client_id", ""))
            or material.get("DERIV_APP_ID") != app_id):
            raise HTTPException(409, "Original demo creation requires reconciliation of persisted native identity")
        return {"account": account.public(), "client_id": account.login, "currency": account.currency,
            "note": "virtual account created; native identity verified from stored credentials"}

    def cmd_deriv_oauth_link(a: dict) -> dict:
        alias = _alias(a)
        require_initial_observe(a,current=reg().accounts.get(alias))
        require_new_alias(alias)
        loginid = str(a.get("loginid", "")).strip().upper()
        token = str(a.get("token", "")).strip()
        if not loginid or not token:
            raise HTTPException(422, "loginid and token required")
        currency = str(a.get("currency") or "USD").upper()
        app_id = str(a.get("app_id") or "1089")
        profile = verify_deriv_material(app_id=app_id, token=token, login=loginid,
            currency=currency, demo=None, require_trade=False)
        demo = bool(profile["is_virtual"])
        mode = "OBSERVE"
        own_revision=[]
        pub = upsert_record(alias, "DERIV", currency=currency, label=str(a.get("label") or f"Deriv {loginid}"), server=app_id, login=loginid, demo=demo, mode=mode,before_write=a.get('_link_before_registry'),after_write=own_revision.append)
        store_secrets(alias, "DERIV", {"DERIV_API_TOKEN": token, "DERIV_APP_ID": str(a.get("app_id") or "1089")},before_write=a.get('_link_before_credentials'),expected_version=own_revision[0] if own_revision else None)
        return {"account": pub,**({'account_control_domain':control_domain()} if st.operation_ledger else {})}

    # ------------------------------------------------------------ ctrader
    def ctrader_transport(is_live: bool):
        if st.ctrader_transport_factory:
            return st.ctrader_transport_factory(is_live)
        from vati.execution.ctrader import DEMO_HOST, LIVE_HOST, CtraderTransport
        return CtraderTransport(host=LIVE_HOST if is_live else DEMO_HOST)

    def cmd_ctrader_discover(a: dict) -> dict:
        from vati.execution.ctrader import CtraderApiError, CtraderError, discover_accounts
        found = []
        errors = []
        for is_live in (False, True):
            t = ctrader_transport(is_live)
            try:
                for acc in discover_accounts(t, client_id=str(a["client_id"]), client_secret=str(a["client_secret"]), access_token=str(a["access_token"])):
                    found.append({**acc, "environment": "live" if is_live else "demo"})
            except (CtraderApiError, CtraderError) as exc:
                errors.append(f"{'live' if is_live else 'demo'}: {exc}")
            finally:
                try:
                    t.close()
                except Exception:  # noqa: BLE001
                    pass
        seen = {}
        for f in found:
            seen.setdefault(f["ctid_trader_account_id"], f)
        if not seen and errors:
            raise HTTPException(502, "; ".join(errors)[:300])
        return {"accounts": list(seen.values()), "errors": errors}

    def cmd_ctrader_oauth_exchange(a: dict) -> dict:
        from vati.execution.ctrader import exchange_code
        try:
            tok = exchange_code(str(a["client_id"]), str(a["client_secret"]), str(a["code"]), str(a["redirect_uri"]), http=st.ctrader_http)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"cTrader token exchange failed: {str(exc)[:200]}")
        return tok

    def cmd_ctrader_link(a: dict) -> dict:
        alias = _alias(a)
        require_initial_observe(a,current=reg().accounts.get(alias))
        require_new_alias(alias)
        ctid = int(a["ctid_trader_account_id"])
        is_live = _boolean(a, "is_live", False)
        own_revision=[]
        pub = upsert_record(alias, "CTRADER", currency=str(a.get("currency") or "USD").upper(), label=str(a.get("label") or f"cTrader {ctid}"), server="live" if is_live else "demo", login=str(ctid), demo=not is_live, mode="OBSERVE",before_write=a.get('_link_before_registry'),after_write=own_revision.append)
        store_secrets(alias, "CTRADER", {"CTRADER_CLIENT_ID": a["client_id"], "CTRADER_CLIENT_SECRET": a["client_secret"], "CTRADER_ACCESS_TOKEN": a["access_token"], **({"CTRADER_REFRESH_TOKEN": a["refresh_token"]} if a.get("refresh_token") else {})},before_write=a.get('_link_before_credentials'),expected_version=own_revision[0] if own_revision else None)
        return {"account": pub,**({'account_control_domain':control_domain()} if st.operation_ledger else {})}

    # ------------------------------------------------------------ mt5 ea
    def cmd_mt5_ea_issue_key(a: dict) -> dict:
        alias = _alias(a)
        current=reg().accounts.get(alias)
        require_initial_observe(a,current=current)
        if current is None and any(not isinstance(a.get(key),str) or not a[key].strip() for key in ('login','server')):
            raise HTTPException(422,'New MT5 account needs login and server')
        if current is not None and 'mode' in a and a['mode']!=current.mode:
            raise HTTPException(422,{'code':'ACCOUNT_MODE_REQUIRES_EXISTING_CONTROL',
                'message':'Bridge key rotation cannot change the admitted account mode'})
        if current is not None:
            identity={'broker':'MT5_EA','currency':str(a.get('currency',current.currency)).upper(),
                'server':str(a.get('server',current.server)),'login':str(a.get('login',current.login)),
                'demo':_boolean(a,'demo',current.demo),'bridge_url':a.get('bridge_url',current.bridge_url),
                'venue':a.get('venue',current.venue)}
            if any(value!=getattr(current,key) for key,value in identity.items()):
                raise HTTPException(409,'Native account identity changes require verified migration; current connection retained')
            # Retain the exact existing reference; this producer is not a vault
            # migration and must not issue a key for an unrelated binding.
            if (current.credential_ref.env_var or not current.credential_ref.secrets_file
                or Path(current.credential_ref.secrets_file).resolve()!=_secrets_path(st,alias).resolve()):
                raise HTTPException(409,'Existing bridge credential binding requires verified migration; key was not issued')
        def prior(name,default):
            return a[name] if name in a else getattr(current,name) if current is not None else default
        key = pysecrets.token_hex(32)
        pub = upsert_record(alias, "MT5_EA", currency=str(prior('currency','USD')).upper(),
            label=str(prior('label',f"MT5 {a.get('login')}")),server=str(prior('server','')),login=str(prior('login','')),
            bridge_url=current.bridge_url if current is not None else '',demo=_boolean(a,'demo',current.demo if current is not None else True))
        store_secrets(alias, "MT5_EA", {"BRIDGE_SIGNING_KEY": key})
        return {"account": pub, "signing_key": key, "ea_inputs": {"Alias": alias, "SigningKey": key, "BridgeUrl": os.environ.get("VAN_PUBLIC_HOST", "") and f"https://{os.environ['VAN_PUBLIC_HOST']}"}, "note": "shown once; paste into VanBridgeEA inputs"}

    handlers = {"account_restrict": lambda args:restriction_call("execute",args), "account_upsert": cmd_account_upsert, "account_credentials": cmd_account_credentials, "account_remove": cmd_account_remove, "account_verify": cmd_account_verify, "account_revision": cmd_account_revision, "account_review":cmd_account_review, "account_operation": cmd_account_operation,
            "deriv_verify_email": cmd_deriv_verify_email, "deriv_create_demo": cmd_deriv_create_demo, "deriv_oauth_link": cmd_deriv_oauth_link, "ctrader_discover": cmd_ctrader_discover,
            "ctrader_oauth_exchange": cmd_ctrader_oauth_exchange, "ctrader_link": cmd_ctrader_link, "mt5_ea_issue_key": cmd_mt5_ea_issue_key}

    def serialize_account_mutation(command, handler):
        @wraps(handler)
        def invoke(args):
            from vati.core.file_lock import exclusive_state_lock
            alias = _alias(args)
            path = Path(st.registry_path).resolve()
            with exclusive_state_lock(path.with_name(path.name + ".operation." + alias)):
                def check_current_scope():
                    guard = args.get('_account_dispatch_guard')
                    if callable(guard):
                        guard()
                    if '_expected_account_control_domain' in args and args['_expected_account_control_domain']!=control_domain():
                        raise AccountOperationBlocked('Account-control state namespace changed before native dispatch')
                    if command in {'deriv_oauth_link','ctrader_link'} and '_oauth_link_admission' in args:
                        admission=args['_oauth_link_admission']
                        if (not isinstance(admission,dict) or admission.get('account_control_domain')!=args.get('_expected_account_control_domain')
                            or admission.get('resource_version')!=args.get('_expected_resource_version')
                            or not isinstance(admission.get('device_id'),str) or not admission['device_id']
                            or not isinstance(admission.get('operation_id'),str)
                            or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}',admission['operation_id'])
                            or type(admission.get('expires_at_unix')) is not int
                            or admission['expires_at_unix']<=int(time.time())):
                            raise HTTPException(403,'Original OAuth link admission expired or changed before native write')
                    if callable(guard):guard()
                def check_version():
                    check_current_scope()
                    if "_expected_resource_version" in args:
                        expected = args["_expected_resource_version"]
                        actual = current_resource_version(alias)
                        if not isinstance(expected, str) or expected != actual:
                            raise HTTPException(409, "account changed since owner approval; review the current account and approve again")
                    check_current_scope()
                server_admitted = command=='deriv_create_demo' and '_native_operation' not in args and callable(args.get('_server_demo_admission'))
                if command=='account_upsert':
                    args={**args,'_upsert_before_write':check_version}
                if command in {'deriv_oauth_link','ctrader_link'}:
                    args={**args,'_link_before_registry':check_version,'_link_before_credentials':check_current_scope}
                if server_admitted:
                    # Only the already authenticated registered owner route
                    # can supply this closure. Labels/metadata confer nothing.
                    check_current_scope()
                    args={**args,'_native_operation':args['_server_demo_admission']()}
                if command not in JOURNALED_COMMANDS or "_native_operation" not in args:
                    # Internal native handler seams; real Local/HTTP ingress
                    # separately requires the verified operation context.
                    if st.operation_ledger:
                        led = open_operation_ledger()
                        try:
                            AccountEffectJournal(led,cleanup_secrets_root=st.secrets_dir).require_clear_targets(("account:"+alias,))
                        except AccountEffectError:
                            raise AccountOperationBlocked() from None
                        finally:
                            led.close()
                    check_version()
                    return handler(args)
                led = open_operation_ledger()
                try:
                    journal = AccountEffectJournal(led,cleanup_secrets_root=st.secrets_dir)
                    domain=control_domain()
                    if args.get('_expected_account_control_domain') not in (None,domain):
                        raise AccountOperationBlocked('Account-control state namespace changed before native dispatch')
                    args={**args,'_expected_account_control_domain':domain}
                    # Refuse invalid NEW modes before the existing demo digest
                    # vault can be read or initialized. Original journaled
                    # outcomes still use their original reader, including UNKNOWN.
                    if command in {'deriv_create_demo','mt5_ea_issue_key'}:
                        original=journal._states().get(args['_native_operation'].get('operation_id'))
                        if original is None:
                            require_initial_observe(args,current=reg().accounts.get(alias))
                    digest_key = None
                    if command == 'deriv_create_demo':
                        from vati.accounts.registry import load_secret_file
                        key_path = Path(st.secrets_dir) / '.demo-operation-digest.env'
                        # Same protected native vault as broker credentials,
                        # never an owner key or an authority grant. Do not
                        # regenerate a lost/replaced key over durable history.
                        with exclusive_state_lock(key_path):
                            states = journal._states()
                            previous = [state for state in states.values()
                                if state.intent.command == command]
                            if key_path.is_symlink():
                                raise AccountOperationBlocked('Original demo digest vault is unsafe; hold for reconciliation')
                            if not key_path.exists():
                                if previous:
                                    raise AccountOperationBlocked('Original demo digest vault is unavailable; hold for reconciliation')
                                _write_secrets(key_path, {'DEMO_DIGEST_KEY': pysecrets.token_hex(32)}, merge=False)
                            try:
                                raw_key = load_secret_file(str(key_path)).get('DEMO_DIGEST_KEY', '')
                            except (AccountRegistryError, OSError):
                                raise AccountOperationBlocked('Original demo digest vault cannot be read safely; hold for reconciliation') from None
                            if not re.fullmatch(r'[0-9a-f]{64}',raw_key):
                                raise AccountOperationBlocked('Original demo digest vault is invalid; hold for reconciliation')
                            digest_key = bytes.fromhex(raw_key)
                            pin = 'deriv-demo-key:' + hashlib.sha256(digest_key).hexdigest()
                            if any(pin not in state.intent.targets for state in previous):
                                raise AccountOperationBlocked('Original demo digest vault changed; hold for reconciliation')
                    intent = operation_intent(command, args, digest_key=digest_key)
                    def legacy_result(state):
                        if state.phase=='REFUSED':
                            raise HTTPException(state.result['status_code'],state.result['detail'])
                        return {**state.result,'operation_id':state.intent.operation_id,
                            'device_id':state.intent.device_id,'action':command,'effect_state':'APPLIED',
                            'reconciliation_required':False,'account_control_domain':readback(state)['account_control_domain']}
                    if server_admitted:
                        # A lost legacy acknowledgement cannot discard the
                        # server-owned original identity or reopen provisioning.
                        for state in journal._states().values():
                            if state.intent.command!=command:continue
                            if state.phase in {'IN_FLIGHT','UNKNOWN'}:
                                if state.intent.device_id==intent.device_id:
                                    raise AccountOperationUnconfirmed(state.intent.operation_id)
                                raise AccountOperationBlocked()
                            if (state.intent.device_id==intent.device_id
                                and state.intent.request_digest==intent.request_digest
                                and state.intent.resource_version==intent.resource_version
                                and state.intent.targets==intent.targets):
                                check_current_scope()
                                return legacy_result(state)
                    # Known-result reads retain the ORIGINAL version. Never
                    # rebase a completed request onto today's registry record.
                    existing = journal.status(intent.operation_id, intent.device_id)
                    if existing is None:
                        check_version()
                    result = invoke_account_effect(journal, intent, lambda: handler(args),
                        dispatch_guard=check_version if command=='deriv_create_demo' else check_current_scope if command=='account_upsert' else args.get('_account_dispatch_guard'))
                    return legacy_result(journal.status(intent.operation_id,intent.device_id)) if server_admitted else result
                except AccountEffectError:
                    raise AccountOperationUnconfirmed(args.get('_native_operation',{}).get('operation_id')) from None
                finally:
                    led.close()
        return invoke

    def serialize_retirement(handler):
        @wraps(handler)
        def invoke(args):
            _alias(args)
            if 'variant' not in args:
                raise HTTPException(422,'IMMEDIATE_DISCONNECT requires purpose-bound reauthentication and separate A4 admission')
            if 'variant' in args and (not isinstance(args['variant'],str) or args['variant'] not in {'PENDING_CLEANUP','DELETE_GRACE','CANCEL_DELETE','IMMEDIATE_DISCONNECT'}):
                raise HTTPException(422,'Unknown native account retirement variant')
            if args.get("variant") in {"DELETE_GRACE","CANCEL_DELETE","IMMEDIATE_DISCONNECT"}:
                return lifecycle_call("execute",args,guard=args.get("_account_dispatch_guard"))
            ledger=open_operation_ledger()
            try:
                if args.get('variant')=='PENDING_CLEANUP':
                    from commander.account_cleanup import UnlinkRecoveryBook,continuity,unknown
                    original=UnlinkRecoveryBook(ledger,initialize=False,secrets_root=st.secrets_dir)._history(args.get('parent_operation_id'))['plan']
                    if (original is None or original.hash!=args.get('plan_ref')
                            or continuity(st,reg())!=original.payload['data']['continuity']):raise unknown()
                domain=control_domain(ledger)
                if args.get('_expected_account_control_domain') not in (None,domain):
                    raise AccountOperationBlocked('Account-control namespace changed before local unlink')
            except BaseException:
                ledger.close()
                raise
            args={**args,'_expected_account_control_domain':domain}
            if args.get('variant')=='PENDING_CLEANUP':
                from commander.account_cleanup import NativeCleanup
                def current_cleanup_scope():
                    guard=args.get('_account_dispatch_guard')
                    if not callable(guard):raise HTTPException(403,'Current cleanup owner scope unavailable; HOLD')
                    guard()
                    if control_domain(ledger)!=domain:raise AccountOperationBlocked('Original cleanup namespace changed')
                    guard()
                try:return NativeCleanup(st,ledger,reg,control_domain).execute(args,operation_intent('account_remove',args),current_cleanup_scope)
                except AccountEffectError:raise AccountOperationUnconfirmed(args.get('_native_operation',{}).get('operation_id')) from None
                finally:ledger.close()
        return invoke

    # Serialize before the registry lookup as well as the file swap. Otherwise
    # a rotation can read an alias, wait for unlink, then recreate orphan secrets.
    for command in ACCOUNT_MUTATIONS:
        handlers[command] = (handlers[command] if command=='account_restrict' else serialize_retirement(handlers[command]) if command=='account_remove'
                             else serialize_account_mutation(command, handlers[command]))
    return handlers


SECRET_ARG_KEYS = {"secrets", "client_password", "token", "access_token", "refresh_token", "client_secret", "verification_code", "code"}


def redact_args(args: dict) -> dict:
    return {k: ("[REDACTED]" if k in SECRET_ARG_KEYS else
                {key: ('[REDACTED]' if key in {'request_digest','authority_ref'} else value) for key,value in v.items()}
                if k=='_native_operation' and isinstance(v,dict) else v) for k, v in args.items()}
