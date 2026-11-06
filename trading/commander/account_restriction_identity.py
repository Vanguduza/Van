"""Bounded native identity observations for restriction recovery.

These observations are DATA, never an owner approval, mode or mandate. The
caller must run the live predicate after its other potentially blocking guards
and before the writer's final time/effect boundary, then close this owner.
"""
from dataclasses import replace
import time

from fastapi import HTTPException
from vati.core.canonical import canonical_hash

MAX_AGE_MS = 30_000


def _hold(code):
    raise HTTPException(409, {'code': code, 'execution_authority': False})


def expected_identity_scope(account):
    """Expected scope is configuration DATA, not a native observation."""
    try:
        if type(account.demo) is not bool:
            raise ValueError('invalid environment')
        if account.broker in {'MT5', 'MT5_EA'}:
            from vati.execution.mt5_identity import Mt5Identity
            return {'broker': account.broker, **Mt5Identity.from_account(account).as_dict()}
        if account.broker == 'DERIV':
            from vati.execution.deriv_identity import DerivIdentity
            identity = DerivIdentity(account.login, account.currency, account.demo, False)
            if not identity.login or not identity.currency:
                raise ValueError('incomplete scope')
            return {'broker': 'DERIV', 'login': identity.login, 'currency': identity.currency, 'demo': identity.demo}
        if account.broker == 'CTRADER':
            from vati.accounts.physical_scope import ctrader_host
            from vati.funding.native import native_int
            return {'broker': 'CTRADER', 'native_account_id': native_int(int(account.login), minimum=1),
                    'host': ctrader_host(account), 'currency': account.currency, 'demo': account.demo}
        if account.broker == 'PAPER':
            if not account.alias or not account.currency:
                raise ValueError('incomplete paper scope')
            return {'broker': 'PAPER', 'account_alias': account.alias, 'currency': account.currency, 'demo': account.demo}
    except (AttributeError, TypeError, ValueError, ArithmeticError, RuntimeError):
        _hold('RESTRICTION_NATIVE_IDENTITY_SCOPE_INVALID')
    _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_UNAVAILABLE')


def _observation(account, adapter, state, *, started_ms, now_ms):
    if type(started_ms) is not int or type(now_ms) is not int or not 0 <= now_ms-started_ms <= MAX_AGE_MS:
        _hold('RESTRICTION_NATIVE_IDENTITY_STALE')
    scope = expected_identity_scope(account)
    if state.account_alias != account.alias or state.currency != account.currency:
        _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
    nonce_ref = None
    binding = None
    received = now_ms
    if account.broker in {'MT5', 'MT5_EA'}:
        from vati.execution.mt5_observation import Mt5AccountObservation
        from vati.execution.mt5_identity import Mt5Identity
        observed = state.native_observation
        kind = 'MT5_SIGNED_EA_POLL' if account.broker == 'MT5_EA' else 'MT5_SIGNED_MTLS_READ'
        if (type(observed) is not Mt5AccountObservation or observed.account_alias != account.alias
                or observed.identity != Mt5Identity.from_account(account) or observed.source_kind != kind
                or not isinstance(observed.source_nonce, str) or not observed.source_nonce
                or Mt5AccountObservation.from_body(observed.body()) != observed):
            _hold('RESTRICTION_NATIVE_IDENTITY_UNPROVEN')
        if not 0 <= observed.source_received_at_ms <= observed.observed_at_ms <= now_ms or now_ms-observed.source_received_at_ms > MAX_AGE_MS:
            _hold('RESTRICTION_NATIVE_IDENTITY_STALE')
        received = observed.source_received_at_ms
        nonce_ref = canonical_hash(observed.source_nonce)
    elif account.broker == 'DERIV':
        from vati.execution.deriv_identity import DerivIdentity
        expected = DerivIdentity(account.login, account.currency, account.demo, False)
        if adapter.identity != expected or state.verified is not True:
            _hold('RESTRICTION_NATIVE_IDENTITY_UNPROVEN')
        transport = adapter.transport
        if not transport._lock.acquire(blocking=False):
            _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_BUSY')
        try:
            expected.validate(transport.authorized_profile)
            if transport.authorized_loginid != account.login or transport._ws is None:
                _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
            binding = (transport._ws, transport._token_fingerprint)
        finally:
            transport._lock.release()
        kind = 'DERIV_NATIVE_AUTHORIZE_READ'
    elif account.broker == 'CTRADER':
        from vati.funding.native import NativeAccountMark
        mark = state.funding_mark
        if (type(mark) is not NativeAccountMark or state.verified is not True
                or mark.provider != 'CTRADER' or mark.account_alias != account.alias
                or mark.native_account_id != scope['native_account_id'] or mark.currency != account.currency
                or mark.environment != ('DEMO' if account.demo else 'LIVE')
                or getattr(adapter.transport, 'host', None) != scope['host'] or not adapter._auth_is_current()):
            _hold('RESTRICTION_NATIVE_IDENTITY_UNPROVEN')
        if NativeAccountMark.from_body(mark.body()) != mark:
            _hold('RESTRICTION_NATIVE_IDENTITY_UNPROVEN')
        if not started_ms <= mark.observed_at_ms <= now_ms:
            _hold('RESTRICTION_NATIVE_IDENTITY_STALE')
        transport = adapter.transport
        if not transport._state_lock.acquire(blocking=False):
            _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_BUSY')
        try:
            if (not transport._alive or transport._sock is None or not adapter._authed
                    or adapter._auth_connection != transport._connection_counter):
                _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
            binding = transport._connection_counter
        finally:
            transport._state_lock.release()
        received = mark.observed_at_ms
        kind = 'CTRADER_AUTHENTICATED_NATIVE_ACCOUNT_READ'
    elif account.broker == 'PAPER':
        if state.verified is not True:
            _hold('RESTRICTION_NATIVE_IDENTITY_UNPROVEN')
        kind = 'INTERNAL_PAPER_SIMULATION'
    else:
        _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_UNAVAILABLE')
    body = {'schema': 'vati.account-restriction-identity-observation/1', 'account_alias': account.alias,
            'broker': account.broker, 'identity_scope_ref': canonical_hash(scope), 'source_kind': kind,
            'source_nonce_ref': nonce_ref, 'source_received_at_ms': received, 'observed_at_ms': now_ms,
            'execution_authority': False, 'mode_or_mandate_granted': False}
    return {**body, 'observation_ref': canonical_hash(body)}, binding


def _close_adapter(adapter):
    failed = False
    for resource in (getattr(adapter, 'transport', None), getattr(adapter, 'queue', None)):
        close = getattr(resource, 'close', None)
        if callable(close):
            try:
                close()
            except Exception:
                failed = True
    if failed:
        _hold('RESTRICTION_NATIVE_IDENTITY_CLOSE_UNAVAILABLE')


class IdentityObservation:
    """Owner of one temporary read-only adapter and its live predicate."""
    def __init__(self, account, adapter, clock_ms):
        self._account, self._adapter, self._clock = account, adapter, clock_ms
        self._closed = False
        self._scope_ref = canonical_hash(expected_identity_scope(account))
        self._facts = None
        self.refresh()

    @property
    def facts(self):
        return None if self._facts is None else dict(self._facts)

    def _read(self):
        if self._closed:
            _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_CLOSED')
        try:
            started = self._clock()
            state = self._adapter.sync_account()
            value, binding = _observation(self._account, self._adapter, state, started_ms=started, now_ms=self._clock())
            if value['identity_scope_ref'] != self._scope_ref:
                _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
            return value, binding
        except HTTPException:
            raise
        except Exception:
            _hold('RESTRICTION_NATIVE_IDENTITY_UNAVAILABLE')

    def refresh(self):
        """Read native source before blocking authority guards; captures owner state."""
        self._facts = None
        self._binding = None
        value, self._binding = self._read()
        if self._account.broker == 'MT5':
            self._binding = (value['source_nonce_ref'], self._adapter.client, self._adapter.client._transport)
        self._facts = dict(value)
        return self.facts

    def require_current(self):
        """Check captured owner state without a provider network read.

        EA checks the actual SQLite-backed queue; it may perform local I/O.
        This predicate does not promise continuous remote revocation.
        """
        if self._closed:
            _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_CLOSED')
        try:
            fields = {'schema', 'account_alias', 'broker', 'identity_scope_ref', 'source_kind',
                      'source_nonce_ref', 'source_received_at_ms', 'observed_at_ms',
                      'execution_authority', 'mode_or_mandate_granted', 'observation_ref'}
            facts = self._facts
            if (type(facts) is not dict or set(facts) != fields
                    or facts['schema'] != 'vati.account-restriction-identity-observation/1'
                    or facts['execution_authority'] is not False or facts['mode_or_mandate_granted'] is not False
                    or facts['observation_ref'] != canonical_hash({k:v for k,v in facts.items() if k != 'observation_ref'})):
                _hold('RESTRICTION_NATIVE_IDENTITY_UNPROVEN')
            now = self._clock()
            if (type(now) is not int or not 0 <= now-facts['source_received_at_ms'] <= MAX_AGE_MS
                    or canonical_hash(expected_identity_scope(self._account)) != self._scope_ref):
                _hold('RESTRICTION_NATIVE_IDENTITY_STALE')
            adapter = self._adapter
            broker = self._account.broker
            if broker == 'MT5_EA':
                from vati.execution.mt5_identity import Mt5Identity
                if adapter.identity != Mt5Identity.from_account(self._account):
                    _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
                current = adapter._state()
                if (canonical_hash(current['source_nonce']) != facts['source_nonce_ref']
                        or current['updated_ms'] != facts['source_received_at_ms']):
                    _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
                after = self._clock()
                if type(after) is not int or not 0 <= after-current['updated_ms'] <= MAX_AGE_MS:
                    _hold('RESTRICTION_NATIVE_IDENTITY_STALE')
            elif broker == 'MT5':
                client = adapter.client
                if not client._nonce_lock.acquire(blocking=False):
                    _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_BUSY')
                try:
                    if (client is not self._binding[1] or client._transport is not self._binding[2]
                            or not client.sent or canonical_hash(str(client.sent[-1].nonce)) != self._binding[0]
                            or client.sent[-1].nonce != client._nonce
                            or adapter.identity.as_dict() != {k:v for k,v in expected_identity_scope(self._account).items() if k != 'broker'}):
                        _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
                finally:
                    client._nonce_lock.release()
            elif broker == 'DERIV':
                from vati.execution.deriv_identity import DerivIdentity
                transport = adapter.transport
                if not transport._lock.acquire(blocking=False):
                    _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_BUSY')
                try:
                    if (adapter.identity != DerivIdentity(self._account.login, self._account.currency, self._account.demo, False)
                            or transport._ws is None or transport._ws is not self._binding[0]
                            or transport._token_fingerprint != self._binding[1]
                            or transport.authorized_loginid != self._account.login):
                        _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
                    adapter.identity.validate(transport.authorized_profile)
                finally:
                    transport._lock.release()
            elif broker == 'CTRADER':
                transport = adapter.transport
                if not transport._state_lock.acquire(blocking=False):
                    _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_BUSY')
                try:
                    if (not transport._alive or transport._sock is None or self._binding is None
                            or transport._connection_counter != self._binding
                            or not adapter._authed or adapter._auth_connection != self._binding
                            or transport.host != expected_identity_scope(self._account)['host']
                            or adapter.ctid_trader_account_id != expected_identity_scope(self._account)['native_account_id']):
                        _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
                finally:
                    transport._state_lock.release()
            elif broker == 'PAPER':
                if adapter.account_alias != self._account.alias or adapter.currency != self._account.currency:
                    _hold('RESTRICTION_NATIVE_IDENTITY_CHANGED')
            else:
                _hold('RESTRICTION_NATIVE_IDENTITY_OWNER_UNAVAILABLE')
            final_time = self._clock()
            if type(final_time) is not int or not 0 <= final_time-facts['source_received_at_ms'] <= MAX_AGE_MS:
                _hold('RESTRICTION_NATIVE_IDENTITY_STALE')
            return dict(facts)
        except HTTPException:
            raise
        except Exception:
            _hold('RESTRICTION_NATIVE_IDENTITY_UNAVAILABLE')

    def close(self):
        if self._closed:
            return
        self._closed = True
        _close_adapter(self._adapter)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def observe_readonly_identity(account, registry, settings, *, clock_ms=None):
    """Factory-owned read-only native observation with explicit close lifetime."""
    from vati.app.service import build_adapter
    clock_ms = clock_ms or (lambda: int(time.time()*1000))
    expected_identity_scope(account)
    adapter = None
    try:
        adapter = build_adapter(replace(account, mode='OBSERVE'), registry, deriv_connector=settings.deriv_connector)
        if account.broker == 'CTRADER' and settings.ctrader_transport_factory:
            adapter.transport = settings.ctrader_transport_factory(not account.demo)
        return IdentityObservation(account, adapter, clock_ms)
    except HTTPException:
        if adapter is not None:
            _close_adapter(adapter)
        raise
    except Exception:
        if adapter is not None:
            _close_adapter(adapter)
        _hold('RESTRICTION_NATIVE_IDENTITY_UNAVAILABLE')
