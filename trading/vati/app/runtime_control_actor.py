"""Lease-fenced owner recovery. Effects and original outcomes commit together.

The runtime publishes a review of risk state, never an entry authorization.
Broker observations are collected before the ledger transaction; no venue IO
is performed while holding the event-chain writer lock.
"""
from dataclasses import asdict
from decimal import Decimal
from cryptography.exceptions import UnsupportedAlgorithm

from vati.app.runtime_control_journal import RuntimeControlJournal
from vati.app.runtime_control_protocol import RuntimeControlError, recovery_profile_ref
from vati.authority import load_owner_keys
from vati.authority_registry import owner_key_id,owner_registry_path
from vati.core import EventKind, make_event
from vati.core.file_lock import exclusive_state_lock
from vati.core.canonical import canonical_hash
from vati.risk.contracts import KillSwitchTrigger
from vati.risk.lockouts import LossStreakGovernor, RESET_EVENT, DRAWDOWN_RESUME_EVENT
from vati.risk.mandate import mandate_subject


def _recovery_cycle(service):
    runner=getattr(service,'runner',None)
    if runner is not None:return runner.cycle
    from vati.app.account_recovery import AccountRecoveryView
    return AccountRecoveryView(service)


def outstanding_owner_halts(ledger, account_alias):
    """A scoped clear releases its cited causes, never another account/new halt."""
    outstanding = {}
    rows = tuple(ledger.iter(EventKind.KILL_SWITCH))
    authorized = set()
    if any(e.payload.get('trigger') == 'OWNER_HALT' and e.payload.get('cleared') is True for e in rows):
        # A name/boolean is not a persisted owner approval. Only a matching
        # final journal record with its real archived P256 proof releases a cause.
        for control in RuntimeControlJournal(ledger)._states().values():
            if (control.phase == 'APPLIED' and control.intent.account_alias == account_alias
                and control.intent.action == 'clear_kill_switch'
                and dict(control.intent.arguments)['trigger'] == 'OWNER_HALT'):
                authorized.update(control.result['effect_refs'])
    for event in rows:
        p = event.payload
        if p.get('trigger') != 'OWNER_HALT':
            continue
        alias = p.get('account_alias')
        # Legacy runner halts used a session correlation rather than an alias.
        if not alias and event.producer == 'vati-runner':
            alias = event.correlation_id.split(':', 1)[0]
        if alias and alias != account_alias:
            continue
        if p.get('cleared') is True:
            # New effects name the original halt(s). An unscoped legacy clear
            # cannot release a global halt for all current/future accounts.
            if alias == account_alias and event.hash in authorized:
                for ref in p.get('source_halt_refs', []):
                    outstanding.pop(ref, None)
        else:
            outstanding[event.hash] = event
    return tuple(outstanding.values())


def recovery_review(service):
    """Stable over polls; changes with authority, risk, or process/lease identity."""
    c = _recovery_cycle(service)
    from vati.accounts import AccountRegistry
    try:
        account = AccountRegistry(service.cfg.registry_path).get(service.cfg.account_alias)
        profile = recovery_profile_ref(account,service.cfg.owner_authority_keys)
    except (OSError, ValueError):
        profile = 'UNAVAILABLE'
    state = {
        'schema': 'vati.runtime-recovery-state/1', 'account_alias': c.cfg.account_alias,
        'session_id': c.cfg.session_id, 'lease_epoch': service.lease.epoch,
        'holder_instance_id': service.lease.instance_id, 'profile_ref': profile,
        'mandate_ref': canonical_hash(service.cfg.mandate),
        'effective_mandate_ref': mandate_subject(c.mandate),
        'kill_switch': sorted(t.value for t in c.kill.active),
        'kill_history_ref': canonical_hash(c.kill.history),
        'owner_halt_refs': [e.hash for e in outstanding_owner_halts(c.ledger, c.cfg.account_alias)],
        'loss_scopes': {k: asdict(v) for k, v in sorted(c.streaks._scopes.items())},
        'peak_equity': str(c.peak_equity), 'risk_history_issue': c.streaks.recovery_issue,
        'risk_control_refs': [e.hash for e in c.ledger.iter(EventKind.SESSION)
            if e.producer == 'vati-cycle' and e.payload.get('account_alias') == c.cfg.account_alias
            and e.payload.get('event') in {RESET_EVENT, DRAWDOWN_RESUME_EVENT}],
        'unresolved_entry_ids': sorted(c.unresolved_entry_attempts),
    }
    return {'state': state, 'state_ref': canonical_hash(state), 'observed_ms': service.clock()}


def _reconciled(c, positions):
    from vati.execution.reconciliation import reconcile, LedgerPosition
    rows = c.ledger_positions() if callable(getattr(c,'ledger_positions',None)) else [LedgerPosition(iid, c.cfg.symbol, entry.get('quantity', Decimal(0)), entry.get('stop'),
                           bool(c.cfg.software_stops))
            for iid, entry in c._entries.items() if entry.get('open', True)]
    return not c.recovery_unresolved and reconcile(rows, positions, account_verified=True).permit_new_orders


def _eligible(c, state, account, heartbeat, positions, now_ms):
    if (c.unresolved_entry_attempts or c.streaks.recovery_issue or account.verified is not True
        or account.account_alias != c.cfg.account_alias or account.currency != c.cfg.contract.account_currency
        or not isinstance(account.equity, Decimal) or not account.equity.is_finite()
        or account.equity <= 0 or heartbeat.connected is not True
        or not _reconciled(c, positions)):
        return False
    action = state.intent.action
    args = dict(state.intent.arguments)
    if action == 'reset_loss_streak':
        scope = c.streaks._scopes.get(args['scope'])
        return scope is not None and (scope.suspended or scope.probation or scope.losses > 0 or scope.cooldown_until_ms > now_ms)
    if action == 'resume_drawdown':
        return c.peak_equity.is_finite() and account.equity < c.peak_equity
    trigger = KillSwitchTrigger(args['trigger'])
    if trigger not in c.kill.active:
        return False
    # A clear cannot stand in for fixing unresolved native account/position state.
    return True


def _same_owner_key(pem,expected):
    try:return owner_key_id(pem)==owner_key_id(expected)
    except (ValueError,TypeError,AttributeError,UnsupportedAlgorithm):return False


def process_recovery_requests(service):
    """Run only on the current actor; original requests never dispatch orders."""
    c = _recovery_cycle(service)
    journal = RuntimeControlJournal(c.ledger, clock=lambda: service.clock() // 1000)
    for request in journal.pending_account(c.cfg.account_alias):
        # Venue reads stay outside the transaction and do not claim a fill or
        # resolve an unknown order. A failed read leaves the request pending.
        account = c.adapter.sync_account()
        heartbeat = c.adapter.heartbeat(now_ms=service.clock())
        positions = tuple(c.adapter.positions())
        committed = None
        try:
            with service.lease.submission_guard(service.lease.epoch, now_ms=service.clock()) as valid:
                # Same lease -> issuer -> ledger order as entry submission.
                # Revocation must not acknowledge between checking the key and
                # committing its owner-approved recovery effect.
                with exclusive_state_lock(owner_registry_path(service.cfg.owner_authority_keys or None)), c.ledger.atomic():
                    current = journal.status(request.proof.operation_id, request.intent.device_id)
                    if current.phase != 'REQUESTED':
                        continue
                    before = recovery_review(service)
                    reason = 'APPLIED'
                    if not valid:
                        reason = 'ACTOR_LEASE_LOST'
                    elif request.intent.session_id != c.cfg.session_id:
                        reason = 'SESSION_CHANGED'
                    elif request.intent.state_ref != before['state_ref']:
                        reason = 'STATE_CHANGED'
                    else:
                        try:
                            keys = load_owner_keys(service.cfg.owner_authority_keys or None)
                        except (OSError, ValueError, TypeError):
                            keys = {}
                        if (request.proof.key_id not in keys
                            or not _same_owner_key(keys[request.proof.key_id],request.public_key_pem)):
                            reason = 'OWNER_KEY_UNREGISTERED'
                        else:
                            try:
                                request.proof.verify(request.intent, keys, now_unix=service.clock() // 1000)
                            except RuntimeControlError:
                                reason = 'APPROVAL_EXPIRED'
                    now = service.clock()
                    held = service.lease.held
                    if reason == 'APPLIED' and (held is None or not held.live_at(now)):
                        reason = 'ACTOR_LEASE_LOST'
                    if reason == 'APPLIED' and now // 1000 >= request.proof.expires_at_unix:
                        reason = 'APPROVAL_EXPIRED'
                    if reason == 'APPLIED' and not _eligible(c, request, account, heartbeat, positions, now):
                        reason = 'PRECONDITION_UNMET'
                    effects = []
                    if reason == 'APPLIED':
                        action = request.intent.action
                        args = dict(request.intent.arguments)
                        payload = {'account_alias': c.cfg.account_alias, 'owner_signature_ref': request.authority_ref,
                                   'operation_id': request.proof.operation_id}
                        kind = EventKind.SESSION
                        if action == 'clear_kill_switch':
                            kind = EventKind.KILL_SWITCH
                            payload.update(trigger=args['trigger'], cleared=True,
                                           source_halt_refs=before['state']['owner_halt_refs'] if args['trigger'] == 'OWNER_HALT' else [])
                        elif action == 'reset_loss_streak':
                            payload.update(event=RESET_EVENT, scope=args['scope'])
                        else:
                            payload.update(event=DRAWDOWN_RESUME_EVENT, old_peak_equity=str(c.peak_equity),
                                           new_peak_equity=str(account.equity))
                        event = make_event(kind, 'vati-cycle', payload, event_time_ms=now,
                                           received_time_ms=now, correlation_id=c.cfg.session_id)
                        c.ledger.append(event)
                        effects.append(event.hash)
                    remaining = sorted(t.value for t in c.kill.active if not (
                        reason == 'APPLIED' and request.intent.action == 'clear_kill_switch'
                        and t.value == dict(request.intent.arguments)['trigger']))
                    committed = journal.finish(request, 'APPLIED' if reason == 'APPLIED' else 'REFUSED', {
                        'reason_code': reason, 'effect_refs': effects, 'entry_authority_granted': False,
                        'remaining_kill': remaining, 'state_ref': before['state_ref']})
        except BaseException:
            # Commit ACK loss is reconciled using this original operation. An
            # unavailable readback fences entries; it never replays the reset.
            try:
                committed = journal.status(request.proof.operation_id, request.intent.device_id)
            except Exception:
                if callable(getattr(c,'hold_entries',None)):
                    c.hold_entries()
                else:
                    service._lease_allows_entry = False
                    service.runner.permit_new_orders = False
                raise
            if committed is None or committed.phase == 'REQUESTED':
                raise
        if committed is not None and committed.phase == 'APPLIED':
            if request.intent.action == 'clear_kill_switch':
                c.kill.active.discard(KillSwitchTrigger(dict(request.intent.arguments)['trigger']))
                c.kill.history.append((service.clock(), 'CLEAR:' + request.authority_ref,
                                       KillSwitchTrigger(dict(request.intent.arguments)['trigger'])))
            elif request.intent.action == 'reset_loss_streak':
                # Fold the complete committed history, including any later loss.
                c.streaks = LossStreakGovernor.rebuild(c.streaks.policy, c.ledger.iter(), account_alias=c.cfg.account_alias)
            else:
                from vati.risk.lockouts import restore_peak_equity
                c.peak_equity = restore_peak_equity(c.ledger.iter(), account_alias=c.cfg.account_alias)
            # Clearing a cause is not blanket authority. Native reconciliation,
            # all other latches, profile, mode and final lease fences still apply.
            if getattr(service,'runner',None) is not None:
                service.runner.permit_new_orders = bool(_reconciled(c, positions)
                    and not c.kill.halted and not c.unresolved_entry_attempts)
