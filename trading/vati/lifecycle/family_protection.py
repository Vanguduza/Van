"""Existing mandatory full-close authority, independent of optional allocation.

The current preservation owner selects a mandatory full exit. This orchestrates
its original native legs through the same router/journal and runtime fence.
No partial-policy admission or new risk permission is inferred from this path.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family_actions import FamilyPolicy, FamilyActionError, EXPLICIT_LEGS_V1, plan_mandatory_full_close
from vati.lifecycle.family_action_journal import FamilyActionJournal
from vati.lifecycle.family_execution import execute_original_action
from vati.lifecycle.family_membership import original_native_snapshot
from vati.lifecycle.family_runtime import runtime_fence_ref
from vati.lifecycle.preservation import PRODUCER, PRESERVATION_VERSION
from vati.risk.mandate_source import validate_mandate_source
from vati.risk.serde import mandate_binding_hash


def mandatory_family_close(lifecycle, decision, *, now_ms):
    if (decision.kind.value!='FULL_CLOSE' or lifecycle.runtime_lease is None
            or lifecycle.mandate is None or not lifecycle.mandate.authority_matches_policy()
            or lifecycle.mandate.account_alias!=lifecycle.adapter.account_alias
            or lifecycle.mandate.venue!=lifecycle.adapter.venue):
        raise FamilyActionError('existing mandatory family protection owner/scope is unavailable')
    source=next((e for e in lifecycle.ledger.iter(EventKind.PRESERVATION_ACTION,
        correlation_id=decision.family_id) if e.producer==PRODUCER
        and e.hash==canonical_hash(e.body()) and e.payload==decision.body()),None)
    if source is None:
        raise FamilyActionError('mandatory family close lacks its original preservation decision')
    family=lifecycle.families.get(decision.family_id)
    history=NativePositionHistory(lifecycle.ledger,account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
    root=family.members[0].trade_intent_id
    command=history.commands.get(root)
    original_risk=next((e for e in history.rows if e.kind is EventKind.RISK_DECISION
        and e.producer in {'vati-account-coordinator','vati-cycle','vati-account-lifecycle'}
        and e.correlation_id==root and e.payload.get('decision',{}).get('decision_hash')==command[0]['decision_hash']),None) if command else None
    if original_risk is None:
        raise FamilyActionError('mandatory family protection lacks original managed command/mandate evidence')
    validate_mandate_source(original_risk.payload['inputs'].get('original_mandate_source'),
        decision_time_ms=original_risk.event_time_ms,expected_hash=original_risk.payload['decision']['mandate_hash'])
    snapshot=original_native_snapshot(history,family,lifecycle.adapter)
    journal=FamilyActionJournal(lifecycle.ledger);key='existing-preservation:'+source.hash
    original=journal.find(family.family_id,key)
    epoch=lifecycle.runtime_lease.epoch;fence=runtime_fence_ref(lifecycle.runtime_lease)
    if original is None:
        plan=plan_mandatory_full_close(snapshot,policy=FamilyPolicy(policy_id='original-managed-family-full-close',
            version=EXPLICIT_LEGS_V1),authority_refs=dict(
                original_mandate_ref=original_risk.hash,current_mandate_ref=mandate_binding_hash(lifecycle.mandate),
                grant_ref=lifecycle.mandate.owner_signature_ref,lease_ref=str(epoch),fence_ref=fence,
                preservation_ref=source.hash,preservation_policy_version=PRESERVATION_VERSION,
                preservation_source_hash=hashlib.sha256(Path(__file__).with_name('preservation.py').read_bytes()).hexdigest()))
        original=journal.prepare(plan,action_key=key,now_ms=now_ms)
    clock=(lifecycle.operational_grants.clock if lifecycle.operational_grants is not None else lifecycle.router.clock)
    if not callable(clock):raise FamilyActionError('current protective runtime clock is unavailable')
    @contextmanager
    def guard(plan,target,_history,_action):
        with lifecycle.mandate.owner_authority_submission_guard() as current_owner:
            if current_owner is not True:raise FamilyActionError('mandatory family current owner refused effect')
            with lifecycle.runtime_lease.submission_guard(epoch,now_ms=clock()) as held:
                if held is not True:raise FamilyActionError('mandatory family runtime lease refused effect')
                with lifecycle.ledger.atomic():
                    binding=dict(plan.authority_refs)
                    if (binding['preservation_ref']!=source.hash
                            or binding['preservation_source_hash']!=hashlib.sha256(Path(__file__).with_name('preservation.py').read_bytes()).hexdigest()
                            or binding['fence_ref']!=runtime_fence_ref(lifecycle.runtime_lease)
                            or binding['lease_ref']!=str(lifecycle.runtime_lease.epoch)
                            or binding['current_mandate_ref']!=mandate_binding_hash(lifecycle.mandate)):
                        raise FamilyActionError('mandatory family original/current authority binding differs')
                    current_history=NativePositionHistory(lifecycle.ledger,
                        account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
                    current=original_native_snapshot(current_history,lifecycle.families.get(plan.snapshot.family_id),
                        lifecycle.adapter,prepared_action=_action,prepared_target=target)
                    leg=next((x for x in current.legs if x.position_id==target.position_id),None)
                    old=next(x for x in plan.snapshot.legs if x.position_id==target.position_id)
                    if (leg is None or leg.trade_intent_id!=target.trade_intent_id or leg.remaining!=target.quantity
                            or leg.close_rules is None or not leg.close_rules.full_close_allowed
                            or leg.close_rules.contract_ref!=old.close_rules.contract_ref
                            or leg.close_rules.evidence_ref!=old.close_rules.evidence_ref
                            or not lifecycle.runtime_lease.fence(epoch,now_ms=clock())):
                        raise FamilyActionError('current original native full target/capability/fence differs')
                    yield
    return execute_original_action(lifecycle,original,grants=None,mandate=lifecycle.mandate,
        authority=lifecycle.authority,lease_epoch=epoch,fence_ref=fence,lease_fence=None,
        mandatory_guard=guard,now_ms=now_ms)
