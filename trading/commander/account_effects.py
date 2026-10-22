"""Native account-effect identities in the existing VATI authority ledger.

No network exactly-once assumption: a committed attempt is never reopened by
timeout/restart. Callers supply native-authorized identity and public outcomes;
this journal does not create owner authority or store credential values.
"""
from dataclasses import asdict, dataclass
from contextvars import ContextVar
import json
import re
import time

from fastapi import HTTPException

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

PRODUCER = "vati-native-account-control"
SCHEMA = "vati.native-account-operation/1"
JOURNALED_COMMANDS = frozenset({"account_upsert", "account_credentials", "account_remove", "mt5_ea_issue_key"})
_effect_started = ContextVar("native_account_effect_started", default=None)


def mark_account_effect():
    """Called immediately before native registry/credential effects, never after."""
    marker = _effect_started.get()
    if marker is not None:
        marker[0] = True


def operation_intent(command, args):
    raw = args.get("_native_operation")
    if not isinstance(raw, dict):
        raise AccountEffectError("verified native account operation is required")
    values = {key: value for key, value in args.items() if not key.startswith("_")}
    alias = str(values.get("alias", "")).strip().lower()
    intent = AccountEffectIntent(
        operation_id=raw.get("operation_id"), device_id=raw.get("device_id"),
        authority_ref=raw.get("authority_ref"), command=command,
        targets=("account:" + alias,), request_digest=canonical_hash(values),
        resource_version=args.get("_expected_resource_version"),
        expires_at_unix=raw.get("expires_at_unix"))
    intent.validate()
    if raw.get("request_digest") != intent.request_digest:
        raise AccountEffectConflict("native operation request differs from its verified dispatch")
    return intent


def public_account_result(command, result):
    # Signing material remains in its existing native vault. Readback confirms
    # the ORIGINAL issue; it never issues a second key or retains an export.
    if command == "mt5_ea_issue_key":
        return {"account": result["account"], "credential_export_available": False,
                "note": "Original key issue is confirmed; credential values are not retained in operation history"}
    return result


class AccountEffectError(ValueError):
    pass


class AccountEffectUnknown(AccountEffectError):
    pass


class AccountEffectConflict(AccountEffectError):
    pass


class AccountEffectAuthorityExpired(AccountEffectError):
    pass


class AccountOperationUnconfirmed(HTTPException):
    effect_state = "UNKNOWN"
    reconciliation_required = True

    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__(409, {"code": "account_operation_unconfirmed", "operation_id": operation_id,
                              "message": "Read the original native operation; do not repeat its effects"})


class AccountOperationBlocked(HTTPException):
    reconciliation_required = True

    def __init__(self):
        super().__init__(409, "Account target has an unconfirmed original native operation; reconciliation required")


def readback(state):
    return {"operation_id": state.intent.operation_id, "action": state.intent.command,
            "effect_state": state.phase if state.phase in {"APPLIED", "REFUSED"} else "UNKNOWN",
            "native_phase": state.phase, "reconciliation_required": state.phase in {"IN_FLIGHT", "UNKNOWN"},
            "result": state.result, "native_event_ref": state.event_ref}


def invoke_account_effect(journal, intent, handler):
    """Caller holds the alias fence; no ledger transaction spans the handler."""
    try:
        claim = journal.claim(intent)
    except AccountEffectConflict:
        raise AccountOperationBlocked() from None
    except AccountEffectUnknown:
        raise AccountOperationUnconfirmed(intent.operation_id) from None
    except AccountEffectAuthorityExpired:
        raise HTTPException(403, "Original owner authority expired before native dispatch; no effect started") from None
    if claim.phase == "APPLIED":
        return claim.result
    if claim.phase == "REFUSED":
        raise HTTPException(claim.result["status_code"], claim.result["detail"])
    marker = [False]
    context = _effect_started.set(marker)
    try:
        result = handler()
        journal.complete(claim, public_account_result(intent.command, result))
        return result
    except BaseException as exc:
        try:
            # A failed reply/commit acknowledgement cannot override a durable
            # completion, and a failed completion cannot reopen an attempt.
            current = journal.status(intent.operation_id, intent.device_id)
            if current and current.phase == "APPLIED":
                return current.result
            if not marker[0] and isinstance(exc, HTTPException) and 400 <= exc.status_code < 500:
                journal.refuse(claim, exc.status_code)
                raise exc
            journal.uncertain(claim)
        except HTTPException:
            raise
        except Exception:
            pass  # IN_FLIGHT itself is a persistent fence when UNKNOWN cannot be recorded.
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise AccountOperationUnconfirmed(intent.operation_id) from None
    finally:
        _effect_started.reset(context)


@dataclass(frozen=True)
class AccountEffectIntent:
    operation_id: str
    device_id: str
    authority_ref: str
    command: str
    targets: tuple[str, ...]
    request_digest: str
    resource_version: str
    expires_at_unix: int

    def validate(self):
        if not isinstance(self.operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", self.operation_id):
            raise AccountEffectError("native operation identity is invalid")
        if not all(isinstance(v, str) and v for v in (self.device_id, self.authority_ref, self.command)):
            raise AccountEffectError("native operation authority and actor are required")
        if not self.targets or not isinstance(self.targets, tuple) or len(self.targets) > 64 or any(
            not isinstance(v, str) or not v or len(v) > 256 for v in self.targets
        ) or len(set(self.targets)) != len(self.targets):
            raise AccountEffectError("native operation target scope is invalid")
        if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in (self.request_digest, self.resource_version)):
            raise AccountEffectError("native operation input binding is invalid")
        if type(self.expires_at_unix) is not int:
            raise AccountEffectError("native operation authority expiry is required")


@dataclass(frozen=True)
class AccountEffectState:
    intent: AccountEffectIntent
    phase: str
    event_ref: str
    result: dict | None = None


class AccountEffectJournal:
    def __init__(self, ledger):
        self.ledger = ledger

    def _states(self):
        if not self.ledger.verify_chain()[0]:
            raise AccountEffectUnknown("native account operation history failed integrity verification")
        states = {}
        for event in self.ledger.iter(EventKind.ACCOUNT_OPERATION):
            try:
                p = event.payload
                if event.producer != PRODUCER or p.get("schema") != SCHEMA:
                    raise ValueError
                raw = p["intent"]
                intent = AccountEffectIntent(**{**raw, "targets": tuple(raw["targets"])})
                intent.validate()
                if p["intent_hash"] != canonical_hash(asdict(intent)) or event.correlation_id != intent.operation_id:
                    raise ValueError
                previous = states.get(intent.operation_id)
                if previous is None:
                    if p["phase"] != "IN_FLIGHT" or p.get("previous_ref") != "" or p.get("result") is not None:
                        raise ValueError
                else:
                    if previous.phase != "IN_FLIGHT" or previous.intent != intent or p.get("previous_ref") != previous.event_ref:
                        raise ValueError
                    if p["phase"] not in {"APPLIED", "UNKNOWN", "REFUSED"}:
                        raise ValueError
                result = p.get("result")
                if p["phase"] in {"APPLIED", "REFUSED"}:
                    self._public_result(result)
                    if p["phase"] == "REFUSED" and (set(result) != {"status_code", "detail"}
                        or type(result["status_code"]) is not int or not 400 <= result["status_code"] < 500
                        or not isinstance(result["detail"], str)):
                        raise ValueError
                elif result is not None:
                    raise ValueError
                states[intent.operation_id] = AccountEffectState(intent, p["phase"], event.hash, result)
            except (KeyError, TypeError, ValueError):
                raise AccountEffectUnknown("native account operation history is ambiguous; reconcile original effects") from None
        return states

    @staticmethod
    def _public_result(result):
        if not isinstance(result, dict):
            raise AccountEffectError("native outcome must be structured public metadata")
        def inspect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise AccountEffectError("native outcome keys must be text")
                    if re.search(r"token|password|signing.?key|client.?secret", key, re.I):
                        raise AccountEffectError("credential material needs a native vault reference, not journal storage")
                    inspect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    inspect(child)
        inspect(result)
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError):
            raise AccountEffectError("native outcome must contain finite JSON values") from None

    def _append(self, intent, phase, previous_ref, result=None, *, now):
        event = make_event(EventKind.ACCOUNT_OPERATION, PRODUCER,
            {"schema": SCHEMA, "intent": asdict(intent), "intent_hash": canonical_hash(asdict(intent)),
             "phase": phase, "previous_ref": previous_ref, "result": result},
            event_time_ms=now * 1000, received_time_ms=now * 1000,
            correlation_id=intent.operation_id)
        self.ledger.append(event)
        return AccountEffectState(intent, phase, event.hash, result)

    def claim(self, intent, *, now_unix=None):
        intent.validate()
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            states = self._states()
            previous = states.get(intent.operation_id)
            if previous is not None:
                if previous.intent != intent:
                    raise AccountEffectConflict("native operation conflicts with its original actor, request or resource")
                if previous.phase not in {"APPLIED", "REFUSED"}:
                    raise AccountEffectUnknown("native operation outcome is unconfirmed; never repeat its effect")
                return previous
            if now >= intent.expires_at_unix:
                raise AccountEffectAuthorityExpired("native operation authority expired before dispatch")
            for state in states.values():
                if state.phase in {"IN_FLIGHT", "UNKNOWN"} and set(intent.targets).intersection(state.intent.targets):
                    raise AccountEffectConflict("native target has an original effect requiring reconciliation")
            return self._append(intent, "IN_FLIGHT", "", now=now)

    def require_clear_targets(self, targets):
        with self.ledger.atomic():
            for state in self._states().values():
                if state.phase in {"IN_FLIGHT", "UNKNOWN"} and set(targets).intersection(state.intent.targets):
                    raise AccountEffectConflict("native target has an original effect requiring reconciliation")

    def refuse(self, claim, status_code, *, now_unix=None):
        """Only for a handler refusal BEFORE the first native effect marker."""
        if type(status_code) is not int or not 400 <= status_code < 500:
            raise AccountEffectError("native pre-effect refusal status is invalid")
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            current = self._states().get(claim.intent.operation_id)
            if current != claim or current.phase != "IN_FLIGHT":
                raise AccountEffectUnknown("native refusal does not match its original attempt")
            return self._append(claim.intent, "REFUSED", claim.event_ref,
                {"status_code": status_code, "detail": "Original request was refused before any account effect"}, now=now)

    def complete(self, claim, public_result, *, now_unix=None):
        self._public_result(public_result)
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            current = self._states().get(claim.intent.operation_id)
            if current is None or current.intent != claim.intent:
                raise AccountEffectUnknown("native operation claim is unavailable")
            if current.phase == "APPLIED" and current.result == public_result:
                return current
            if current.phase != "IN_FLIGHT" or current.event_ref != claim.event_ref:
                raise AccountEffectUnknown("native operation completion does not match its original attempt")
            return self._append(claim.intent, "APPLIED", claim.event_ref, public_result, now=now)

    def uncertain(self, claim, *, now_unix=None):
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            current = self._states().get(claim.intent.operation_id)
            if current is None or current.intent != claim.intent:
                raise AccountEffectUnknown("native operation claim is unavailable")
            if current.phase in {"UNKNOWN", "APPLIED"}:
                return current
            if current.event_ref != claim.event_ref:
                raise AccountEffectUnknown("native operation attempt changed")
            return self._append(claim.intent, "UNKNOWN", claim.event_ref, now=now)

    def status(self, operation_id, device_id):
        with self.ledger.atomic():
            state = self._states().get(operation_id)
            if state is not None and state.intent.device_id != device_id:
                raise AccountEffectConflict("native operation belongs to another device")
            return state
