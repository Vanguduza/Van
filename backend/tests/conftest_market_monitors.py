"""Scoped owner HTTP tests: real startup/auth/storage, unrelated native actors idle.

The periodic scheduler is disabled through its supported setting; the actual registered
market-monitor job is invoked explicitly. This fixture grants no device/trading authority
and does not stand in for native dispatcher or production scheduler qualification.
"""
import asyncio
import pytest


@pytest.fixture(autouse=True)
def isolate_native_backgrounds(monkeypatch):
    from van_gateway.trading.runtime_recovery_dispatch import RuntimeRecoveryDispatcher
    from van_gateway.auth.native_revocation import NativeOwnerRevocations

    async def idle(self):
        await asyncio.Event().wait()

    monkeypatch.setenv('VAN_SCHEDULER_ENABLED', 'false')
    monkeypatch.setattr(RuntimeRecoveryDispatcher, 'run', idle)
    monkeypatch.setattr(NativeOwnerRevocations, 'run', idle)
