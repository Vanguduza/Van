"""Require the existing alias lease and an additional native-account lease.

This source protocol needs a coherently upgraded, independently qualified
runtime cohort. It neither fences an old binary nor reconciles shared financial
state across aliases. Provider identity, owner grants and uncertain effects keep
their existing owners; this class cannot supply any of those qualifications.
"""
from contextlib import contextmanager
import threading

from vati.accounts.access import SENDING_MODES
from vati.accounts.physical_scope import ExpectedPhysicalScope
from vati.accounts.registry import BrokerKind
from vati.app.account_lease import AccountRuntimeLease


class PhysicalAccountRuntimeLease(AccountRuntimeLease):
    def __init__(self, store, *, physical_scope, **kwargs):
        if not isinstance(physical_scope, ExpectedPhysicalScope):
            raise ValueError('typed expected native account scope required')
        super().__init__(store, **kwargs)
        self.physical_scope = physical_scope
        self._operation_lock = threading.RLock()
        self._physical = AccountRuntimeLease(store, **{**kwargs, 'account_alias': physical_scope.lease_key})

    def _drop(self, now):
        # Each original CAS refuses to release a different holder or epoch.
        super().release(now_ms=now)
        self._physical.release(now_ms=now)

    def acquire(self, *, now_ms=None):
        with self._operation_lock:
            now = self._now(now_ms)
            native = self._physical.acquire(now_ms=now)
            if not native.permits_orders:
                self._drop(now)
                return native
            logical = super().acquire(now_ms=now)
            if not logical.permits_orders:
                self._drop(now)
            return logical

    def renew(self, *, now_ms=None):
        with self._operation_lock:
            now = self._now(now_ms)
            if self.held is None or self._physical.held is None:
                return self.acquire(now_ms=now)
            native = self._physical.renew(now_ms=now)
            if not native.permits_orders:
                self._drop(now)
                return native
            logical = super().renew(now_ms=now)
            if not logical.permits_orders:
                self._drop(now)
            return logical

    def fence(self, epoch, *, now_ms=None, min_validity_ms=2000):
        with self._operation_lock:
            now = self._now(now_ms)
            native = self._physical.fence(self._physical.epoch, now_ms=now,
                                          min_validity_ms=min_validity_ms)
            logical = super().fence(epoch, now_ms=now, min_validity_ms=min_validity_ms)
            if self._physical.held is None or self.held is None:
                self._drop(now)
            return native and logical

    @contextmanager
    def submission_guard(self, epoch, *, now_ms=None):
        with self._operation_lock:
            lost = False
            try:
                # All native actors lock physical scope before logical alias.
                # The store's transaction owner retains both outer row locks.
                with self._physical.submission_guard(self._physical.epoch, now_ms=now_ms) as native:
                    if not native:
                        lost = True
                        yield False
                        return
                    with super().submission_guard(epoch, now_ms=now_ms) as logical:
                        lost = not logical
                        yield logical
            finally:
                if lost:
                    self._drop(self._now(now_ms))

    def release(self, *, now_ms=None):
        with self._operation_lock:
            self._drop(self._now(now_ms))


def build_runtime_lease(store, *, account, mode, **kwargs):
    logical = dict(kwargs, account_alias=account.alias)
    if (mode in SENDING_MODES and account.broker in
            {BrokerKind.CTRADER, BrokerKind.MT5, BrokerKind.MT5_EA, BrokerKind.DERIV}):
        return PhysicalAccountRuntimeLease(store,
            physical_scope=ExpectedPhysicalScope.from_account(account), **logical)
    # Paper, observation, shadow and owner-ticket workflows retain their source
    # contracts. No automated native-account identity is invented for a ticket.
    return AccountRuntimeLease(store, **logical)
