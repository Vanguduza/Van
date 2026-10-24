"""Actual persisted account controls must agree with the running session gate."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from conftest_owner_authority import OwnerAuthorityHarness
from test_single_session_recovery import opened_service
from vati.accounts import AccountRegistry


@pytest.mark.parametrize('change',['disabled','read-only','binding','removed','corrupt'])
def test_current_native_profile_refuses_stale_session_permission_without_losing_protection(tmp_path,eurusd,change):
    service,cfg,clock=opened_service(tmp_path,eurusd)
    try:
        position=service.adapter.positions()[0];stop=service.runner.cycle.protection.stop_of(position.position_id)
        assert service.runner.cycle.router.lease_fence(service.lease.epoch) is True
        registry=AccountRegistry(cfg.registry_path);account=registry.get(cfg.account_alias)
        if change=='disabled':registry.replace(replace(account,enabled=False))
        elif change=='read-only':registry.replace(replace(account,mode='OBSERVE'))
        elif change=='binding':registry.replace(replace(account,server='replacement-native-binding'))
        elif change=='removed':registry.remove(account.alias)
        else:Path(cfg.registry_path).write_text('{invalid account registry')
        clock['now']+=1;service.step_once()
        heartbeat=json.loads(Path(cfg.heartbeat_path).read_text())
        assert heartbeat['permit_new_orders'] is False
        assert service.runner.cycle.router.lease_fence(service.lease.epoch) is False
        assert service.runner.cycle.protection.stop_of(position.position_id)==stop
        assert service.adapter.positions()[0].position_id==position.position_id
    finally:service.close();service._ledger.close()


def test_non_authority_account_labels_do_not_disable_a_live_session(tmp_path,eurusd):
    service,cfg,clock=opened_service(tmp_path,eurusd)
    try:
        registry=AccountRegistry(cfg.registry_path);account=registry.get(cfg.account_alias)
        registry.replace(replace(account,label='Owner display name',notes='Owner note'))
        clock['now']+=1;service.step_once()
        assert json.loads(Path(cfg.heartbeat_path).read_text())['permit_new_orders'] is True
        assert service.runner.cycle.router.lease_fence(service.lease.epoch) is True
    finally:service.close();service._ledger.close()


def test_profile_reenable_does_not_clear_an_actual_signed_owner_halt(tmp_path,eurusd):
    service,cfg,clock=opened_service(tmp_path,eurusd)
    try:
        registry=AccountRegistry(cfg.registry_path);account=registry.get(cfg.account_alias)
        registry.replace(replace(account,enabled=False))
        clock['now']+=1;service.step_once()
        assert json.loads(Path(cfg.heartbeat_path).read_text())['permit_new_orders'] is False
        authority=OwnerAuthorityHarness();service.runner.authority=authority.verifier
        service.runner.owner_halt(now_ms=clock['now'],owner_signature_ref=authority.token(act='owner-halt',
            subject=service.runner.cycle.cfg.session_id,issued_at_unix=clock['now']//1000))
        registry=AccountRegistry(cfg.registry_path);registry.replace(replace(registry.get(cfg.account_alias),enabled=True))
        clock['now']+=1;service.step_once()
        assert json.loads(Path(cfg.heartbeat_path).read_text())['permit_new_orders'] is False
        assert service.runner.cycle.router.lease_fence(service.lease.epoch) is False
    finally:service.close();service._ledger.close()


def limited_profile(tmp_path,contract):
    from conftest import historical_mandate_dict
    from test_single_session_lease import config
    from vati.app.service import SessionService
    cfg=config(tmp_path,contract);registry=AccountRegistry(cfg.registry_path)
    account=registry.get(cfg.account_alias)
    registry.replace(replace(account,mode='AUTONOMOUS_LIVE',demo=False,mandate_ref='source-fixture-policy'))
    cfg.mandate=historical_mandate_dict(account_alias=account.alias,venue='paper',mode='AUTONOMOUS_LIVE',
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    from test_backtest_runner_cli import synthetic_bars
    clock={'now':synthetic_bars()[100].end_ms}
    # Paper transport only: verify authority denial without any live broker/funds.
    service=SessionService(cfg,lambda now:[],clock=lambda:clock['now']).build()
    service.start()
    registry=AccountRegistry(cfg.registry_path)
    registry.replace(replace(registry.get(cfg.account_alias),mode='LIMITED_LIVE'))
    return service,cfg,clock


def test_current_sending_mode_reduction_is_a_readable_refusal(tmp_path,eurusd):
    service,cfg,clock=limited_profile(tmp_path,eurusd)
    try:
        service.step_once()
        assert json.loads(Path(cfg.heartbeat_path).read_text())['permit_new_orders'] is False
        assert service.runner.cycle.router.lease_fence(service.lease.epoch) is False
    finally:service.close();service._ledger.close()


def test_bound_sender_reports_mode_reduction_as_native_zero_effect(tmp_path,eurusd):
    from test_mt5_original_entry_claim import command
    service,cfg,clock=limited_profile(tmp_path,eurusd)
    try:
        request=replace(command(cfg.account_alias),venue='paper').sealed()
        result=service.adapter.submit(request,now_ms=clock['now'])
        assert result.status=='REJECTED' and result.filled_qty==0
        assert service.adapter.positions()==[]
    finally:service.close();service._ledger.close()
