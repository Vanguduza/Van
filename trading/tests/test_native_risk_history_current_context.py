"""Fresh source can select old proven ownership without manufacturing history."""
from dataclasses import replace

import pytest

from conftest import NOW
from test_native_risk_history_inputs import native_facts, record
from test_native_risk_history_index import other_context
from vati.core import EventKind
from vati.core.ledger import LedgerError
from vati.risk.native_history import native_risk_history_for_context, NativeRiskSourceUnavailable


def test_a_new_alias_recovers_existing_physical_history_before_its_first_decision(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    original = record(ledger, facts)
    current = other_context(ledger, adapter, account, facts, alias='new_label')
    before = tuple(e.body() for e in ledger.iter())
    value = native_risk_history_for_context(ledger, current.native_account_context, available_at_ms=NOW*1000)
    assert value.anchor_event_ref is None
    assert [v.event_ref for v in value.original_inputs] == [original.hash]
    assert value.original_inputs[0].context.account_alias == 'native'
    assert current.native_account_context.account_alias == 'new_label'
    assert value.unresolved_refs == ()
    assert tuple(e.body() for e in ledger.iter()) == before
    assert ledger.count(EventKind.RISK_DECISION) == 1
    assert value.execution_authority is value.risk_capital_qualified is False


def test_a_truly_new_account_has_empty_history_without_a_synthetic_risk_record(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    before = ledger.count()
    value = native_risk_history_for_context(ledger, facts.native_account_context, available_at_ms=NOW*1000)
    assert value.original_inputs == value.unresolved_refs == ()
    assert ledger.count() == before and ledger.count(EventKind.RISK_DECISION) == 0


def test_current_identity_does_not_assign_an_old_unbound_risk_record(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    unbound = record(ledger, replace(facts, native_account_context=None))
    value = native_risk_history_for_context(ledger, facts.native_account_context, available_at_ms=NOW*1000)
    assert value.original_inputs == () and value.unresolved_refs == (unbound.hash,)


@pytest.mark.parametrize('damage', ['query', 'source', 'alias', 'authority', 'future'])
def test_current_metadata_cannot_substitute_for_original_available_source(tmp_path, eurusd, damage):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    context = facts.native_account_context
    values = {'query': {'source_query_ref':'0'*64}, 'source': {'observation_ref':'0'*64},
              'alias': {'account_alias':'another_label'}, 'authority': {'execution_authority':True}}
    if damage == 'future':
        context = facts.native_account_context
        cutoff = 9999
    else:
        context = replace(context, **values[damage])
        cutoff = NOW*1000
    with pytest.raises(NativeRiskSourceUnavailable):
        native_risk_history_for_context(ledger, context, available_at_ms=cutoff)


def test_current_source_cannot_read_a_writers_uncommitted_history(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path, eurusd)
    with pytest.raises(LedgerError, match='committed_source_read_requires'):
        with ledger.atomic():
            native_risk_history_for_context(ledger, facts.native_account_context, available_at_ms=NOW*1000)


def test_original_unavailable_source_refusal_does_not_poison_healthy_recovery(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    refused=record(ledger,replace(facts,native_account_context=None,account_verified=False,
        broker_connected=False,preservation_blocks_new_risk=True,
        preservation_reason='FUNDING_RISK_UNAVAILABLE:NATIVE_SOURCE_UNAVAILABLE'))
    assert refused.payload['decision']['decision']=='REJECTED'
    value=native_risk_history_for_context(ledger,facts.native_account_context,available_at_ms=NOW*1000)
    assert value.original_inputs==()
    assert value.unresolved_refs==(refused.hash,)
    assert value.nonfinancial_rejection_refs==(refused.hash,)
    assert refused.payload['inputs']['snapshot'].get('native_account_context') is None
    from vati.risk.physical_history import physical_financial_history
    financial=physical_financial_history(ledger,facts.native_account_context,available_at_ms=NOW*1000)
    assert not financial.issue and financial.unresolved_refs==()


def test_changing_an_approval_label_to_rejected_does_not_excuse_unbound_history(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    def damage(p):p['decision']['decision']='REJECTED'
    bad=record(ledger,replace(facts,native_account_context=None),damage=damage)
    value=native_risk_history_for_context(ledger,facts.native_account_context,available_at_ms=NOW*1000)
    assert bad.hash in value.unresolved_refs and value.nonfinancial_rejection_refs==()
