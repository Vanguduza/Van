"""Real session/lease/ledger effects, replay and changed-state refusal."""
import base64
from dataclasses import replace
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from test_single_session_lease import config
from test_backtest_runner_cli import synthetic_bars
from vati.app.service import SessionService
from vati.app.runtime_control_actor import recovery_review, outstanding_owner_halts
from vati.app.runtime_control_journal import RuntimeControlJournal
from vati.app.runtime_control_protocol import RecoveryIntent, RecoveryProof, approval_statement
from vati.core import EventKind, make_event
from vati.risk.contracts import KillSwitchTrigger


@pytest.fixture
def runtime(tmp_path, eurusd):
    cfg = config(tmp_path, eurusd)
    now = {'ms': synthetic_bars()[100].end_ms}
    cfg.owner_authority_keys = str(tmp_path / 'control-owner.json')
    private = ec.generate_private_key(ec.SECP256R1())
    pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    keys = {'source-owner': pem}
    with open(cfg.owner_authority_keys, 'w') as out: json.dump({'keys': keys}, out)
    service = SessionService(cfg, lambda now: [], clock=lambda: now['ms']).build()
    service.start()
    def request(action='clear_kill_switch', args=None, **overrides):
        body = {'schema': 'vati.runtime-recovery/1', 'device_id': 'source-owner-device',
            'account_alias': cfg.account_alias, 'session_id': service.runner.cycle.cfg.session_id,
            'action': action, 'state_ref': recovery_review(service)['state_ref'],
            'issued_at_unix': now['ms']//1000, 'args': args if args is not None else {'trigger': 'OWNER_HALT'}, **overrides}
        intent = RecoveryIntent.from_mapping(body)
        import secrets
        op = secrets.token_urlsafe(24); expiry = now['ms']//1000+60
        sig = private.sign(approval_statement(intent, op, expiry).encode(), ec.ECDSA(hashes.SHA256()))
        proof = RecoveryProof(op, expiry, 'source-owner', base64.b64encode(sig).decode())
        journal = RuntimeControlJournal(service._ledger, clock=lambda: now['ms']//1000)
        return journal, journal.enqueue(intent, proof, keys)
    yield service, now, request
    service.close(); service._ledger.close()


def halt(service, *, alias=None):
    now = service.clock()
    p = {'trigger': 'OWNER_HALT'}
    if alias: p['account_alias'] = alias
    event = make_event(EventKind.KILL_SWITCH, 'van-commander', p, event_time_ms=now,
                       received_time_ms=now, correlation_id='owner')
    service._ledger.append(event); service._observe_owner_halt(now)
    return event


def test_owner_clear_applies_once_without_an_order_or_blanket_entry_grant(runtime):
    service, now, request = runtime
    source = halt(service)
    service.runner.cycle.kill.trip(KillSwitchTrigger.STALE_DATA, now['ms'])
    journal, original = request()
    service.step_once()
    done = journal.status(original.proof.operation_id, original.intent.device_id)
    assert done.phase == 'APPLIED' and len(done.result['effect_refs']) == 1
    assert done.result['entry_authority_granted'] is False
    assert service.runner.cycle.kill.active == {KillSwitchTrigger.STALE_DATA}
    assert not outstanding_owner_halts(service._ledger, service.cfg.account_alias)
    assert outstanding_owner_halts(service._ledger, 'another_account') == (source,)
    count = service._ledger.count(EventKind.KILL_SWITCH)
    service.step_once()
    assert journal.enqueue(original.intent, original.proof, {}).phase == 'APPLIED'
    assert service._ledger.count(EventKind.KILL_SWITCH) == count
    assert service._ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.parametrize('change,reason', [('new-halt','STATE_CHANGED'), ('expired','APPROVAL_EXPIRED'),
    ('revoked','OWNER_KEY_UNREGISTERED'), ('new-session','SESSION_CHANGED'), ('lost-lease','ACTOR_LEASE_LOST')])
def test_changed_authority_or_target_refuses_without_clearing(runtime, change, reason):
    from vati.app.runtime_control_actor import process_recovery_requests
    service, now, request = runtime; halt(service)
    journal, original = request(session_id='old-session') if change=='new-session' else request()
    if change=='new-halt':
        now['ms'] += 1; halt(service)
    elif change=='expired': now['ms'] += 61000
    elif change=='revoked':
        with open(service.cfg.owner_authority_keys, 'w') as out: json.dump({'keys': {}}, out)
    elif change=='lost-lease': service.lease.release(now_ms=now['ms'])
    if change=='lost-lease': process_recovery_requests(service)
    else: service.step_once()
    done = journal.status(original.proof.operation_id, original.intent.device_id)
    assert done.phase == 'REFUSED' and done.result['reason_code'] == reason
    assert done.result['effect_refs'] == []
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active


def test_applied_loss_reset_does_not_reset_a_later_loss_on_replay(runtime):
    service, now, request = runtime; c = service.runner.cycle
    def loss(i):
        e = make_event(EventKind.TRADE_REVIEW, 'vati-cycle', {'strategy_id':'FX-TREND-PULLBACK-01',
            'account_alias': service.cfg.account_alias, 'pnl':'-1'}, event_time_ms=now['ms'],
            received_time_ms=now['ms'], correlation_id='source-trade-'+str(i))
        service._ledger.append(e)
        c.streaks.on_close('FX-TREND-PULLBACK-01', -1, now['ms'])
    loss(1)
    journal, original = request('reset_loss_streak', {'scope':'*ACCOUNT*'})
    service.step_once()
    assert journal.status(original.proof.operation_id, original.intent.device_id).phase == 'APPLIED'
    assert c.streaks._scopes['*ACCOUNT*'].losses == 0
    loss(2); service.step_once()
    assert journal.enqueue(original.intent, original.proof, {}).phase == 'APPLIED'
    assert c.streaks._scopes['*ACCOUNT*'].losses == 1


def test_drawdown_resume_records_actual_verified_equity_and_survives_cold_restart(runtime):
    service, now, request = runtime; c = service.runner.cycle
    from decimal import Decimal
    c.peak_equity = Decimal('12000')
    journal, original = request('resume_drawdown', {})
    service.step_once()
    assert journal.status(original.proof.operation_id, original.intent.device_id).phase == 'APPLIED'
    assert c.peak_equity == c.adapter.sync_account().equity
    adapter = service.adapter
    service.close(); service._ledger.close()
    second = SessionService(service.cfg, lambda now: [], clock=service.clock, adapter=adapter).build()
    try:
        second.start()
        assert second.runner.cycle.peak_equity == c.peak_equity
        assert not RuntimeControlJournal(second._ledger).pending_account(service.cfg.account_alias)
    finally: second.close(); second._ledger.close()


def test_unresolved_entry_prevents_owner_clear_without_losing_existing_latch(runtime):
    service, now, request = runtime; halt(service)
    service.runner.cycle.unresolved_entry_attempts.add('native-unknown')
    journal, original = request()
    from vati.app.runtime_control_actor import process_recovery_requests
    process_recovery_requests(service)
    done = journal.status(original.proof.operation_id, original.intent.device_id)
    assert done.phase == 'REFUSED' and done.result['reason_code'] == 'PRECONDITION_UNMET'
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active


@pytest.mark.parametrize('ack_lost', [False, True])
def test_domain_effect_and_outcome_commit_together_even_when_commit_reply_is_lost(runtime, monkeypatch, ack_lost):
    from contextlib import contextmanager
    from vati.app.runtime_control_actor import process_recovery_requests
    service, now, request = runtime; halt(service)
    journal, original = request(); ledger = service._ledger
    if ack_lost:
        atomic = ledger.atomic
        fired = []
        @contextmanager
        def lose_committed_reply():
            outer = not ledger._conn.in_transaction
            with atomic(): yield ledger
            if outer and not fired and any(e.payload.get('phase')=='APPLIED'
                    for e in ledger.iter(EventKind.SESSION) if e.producer=='vati-runtime-recovery-control'):
                fired.append(True)
                raise OSError('fixture actual outer commit succeeded but ACK was lost')
        monkeypatch.setattr(ledger, 'atomic', lose_committed_reply)
        process_recovery_requests(service)
        assert fired
    else:
        append = ledger.append
        def fail_before_commit(event):
            result = append(event)
            if event.producer=='vati-runtime-recovery-control' and event.payload['phase']=='APPLIED':
                raise OSError('fixture failed after effect append before outer commit')
            return result
        with monkeypatch.context() as scoped:
            scoped.setattr(ledger, 'append', fail_before_commit)
            with pytest.raises(OSError, match='before outer commit'): process_recovery_requests(service)
        assert journal.status(original.proof.operation_id, original.intent.device_id).phase=='REQUESTED'
        assert not any(e.payload.get('cleared') for e in ledger.iter(EventKind.KILL_SWITCH))
        assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active
        process_recovery_requests(service)
    assert journal.status(original.proof.operation_id, original.intent.device_id).phase=='APPLIED'
    assert not service.runner.cycle.kill.halted
    assert len([e for e in ledger.iter(EventKind.KILL_SWITCH) if e.payload.get('cleared')])==1


def test_a_clear_shaped_event_without_native_approval_cannot_release_an_owner_halt(runtime):
    service, now, _ = runtime; source = halt(service)
    forged = make_event(EventKind.KILL_SWITCH, 'vati-cycle', {'account_alias':service.cfg.account_alias,
        'trigger':'OWNER_HALT', 'cleared':True, 'source_halt_refs':[source.hash], 'owner_signature_ref':'looks-approved'},
        event_time_ms=now['ms'], received_time_ms=now['ms'], correlation_id=service.runner.cycle.cfg.session_id)
    service._ledger.append(forged)
    assert outstanding_owner_halts(service._ledger, service.cfg.account_alias)==(source,)


@pytest.mark.parametrize('fact', ['verified-string','connected-string','equity-nonfinite','equity-float'])
def test_ambiguous_native_account_facts_never_clear_risk(runtime, monkeypatch, fact):
    from vati.app.runtime_control_actor import process_recovery_requests
    from decimal import Decimal
    service, now, request = runtime; halt(service)
    journal, original = request()
    c = service.runner.cycle
    if fact.startswith('equity') or fact.startswith('verified'):
        account = c.adapter.sync_account()
        value = {'verified-string':{'verified':'true'}, 'equity-nonfinite':{'equity':Decimal('NaN')},
                 'equity-float':{'equity':10000.0}}[fact]
        monkeypatch.setattr(c.adapter, 'sync_account', lambda: replace(account, **value))
    else:
        hb = c.adapter.heartbeat(now_ms=now['ms'])
        monkeypatch.setattr(c.adapter, 'heartbeat', lambda **kw: replace(hb, connected='true'))
    process_recovery_requests(service)
    done = journal.status(original.proof.operation_id, original.intent.device_id)
    assert done.phase=='REFUSED' and done.result['reason_code']=='PRECONDITION_UNMET'
    assert KillSwitchTrigger.OWNER_HALT in c.kill.active


def test_lease_expiry_while_waiting_for_chain_writer_cannot_apply_a_clear(runtime, monkeypatch):
    from contextlib import contextmanager
    from vati.app.runtime_control_actor import process_recovery_requests
    service, now, request = runtime; halt(service)
    journal, original = request(); guard = service.lease.submission_guard
    @contextmanager
    def waited(epoch, **kw):
        with guard(epoch, **kw) as valid:
            assert valid
            now['ms'] = service.lease.held.expires_at_ms
            yield valid
    monkeypatch.setattr(service.lease, 'submission_guard', waited)
    process_recovery_requests(service)
    done = journal.status(original.proof.operation_id, original.intent.device_id)
    assert done.phase=='REFUSED' and done.result['reason_code']=='ACTOR_LEASE_LOST'
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active
