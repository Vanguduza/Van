"""Identity and valuation observations survive cash-history outages honestly."""
from decimal import Decimal as D
import pytest
from test_mt5_worker_funding import connection


def test_actual_signed_worker_keeps_physical_observation_without_cash_history(tmp_path):
    sdk, worker, adapter, now = connection(tmp_path)
    sdk.history_deals_get = lambda *a, **kw: None
    account = adapter.sync_account()
    assert account.funding_mark is None
    observed = getattr(account, 'native_observation', None)
    assert observed is not None, 'physical account facts were discarded with unrelated cash-query coverage'
    assert observed.identity == adapter.identity and observed.credit == D('250.5')
    assert observed.reported_equity == D('10250.5') and observed.risk_equity == account.equity == D('10000')
    assert observed.source_nonce == str(adapter.client.sent[-1].nonce)
    assert not sdk.sent


@pytest.mark.parametrize('credit', [None, 'missing', float('nan'), -10.0])
def test_unknown_or_liability_credit_is_not_a_measured_risk_valuation(tmp_path, credit):
    sdk, worker, adapter, now = connection(tmp_path)
    original = sdk.account_info
    def unavailable():
        a = original()
        if credit == 'missing': del a.credit
        else: a.credit = credit
        return a
    sdk.account_info = unavailable
    sdk.history_deals_get = lambda *a, **kw: None
    account = adapter.sync_account()
    observed = getattr(account, 'native_observation', None)
    assert observed is not None
    assert observed.risk_equity is None and observed.valuation_state != 'CREDIT_EXCLUDED'
    assert adapter.positions() == [] and not sdk.sent


def publish_native_snapshot(ledger, adapter, clock, producer='single'):
    from types import SimpleNamespace as N
    if producer == 'single':
        from vati.app.service import SessionService
        service = SessionService.__new__(SessionService)
        service.clock = clock
        service.runner = N(cycle=N(adapter=adapter, ledger=ledger, peak_equity=D('0'),
            day_start_equity=D('0'), week_start_equity=D('0'), kill=N(active=[]),
            cfg=N(session_id='native-observation-fixture'), streaks=N(recovery_issue=''),
            mandate=N(mode=N(value='DEMO_TRADER'))))
    else:
        from vati.app.account_service import AccountCoordinatorService
        service = AccountCoordinatorService(N(account_alias='native', max_quote_age_ms=5000), clock=clock)
        service.adapter = adapter; service._ledger = ledger; service.account = N(alias='native')
    service._account_snapshot(clock())
    from vati.core import EventKind
    return list(ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[-1]


def observed_owner(tmp_path, producer='single', credit='known'):
    from vati.core import Ledger
    sdk, worker, adapter, now = connection(tmp_path)
    original = sdk.account_info
    def facts():
        a = original(); a.margin=1000.0; a.margin_free=9250.5; a.margin_level=1025.05
        if credit != 'known': a.credit = credit
        return a
    sdk.account_info = facts; sdk.history_deals_get = lambda *a, **kw: None
    ledger = Ledger(tmp_path/'observed-owner.sqlite')
    event = publish_native_snapshot(ledger, adapter, lambda: now['ms'], producer)
    return sdk, adapter, ledger, event


@pytest.mark.parametrize('producer', ['single', 'account'])
def test_actual_snapshot_producers_supply_bound_account_and_margin_during_cash_outage(tmp_path, producer):
    from test_mt5_funding_runtime import profile
    from vati.app.portfolio import account_states
    from vati.funding.risk_fence import funding_risk_fence
    sdk, adapter, ledger, event = observed_owner(tmp_path, producer)
    before = ledger.count(); row = account_states(ledger, [profile()])[0]
    value = row['native_account_observation']
    assert value['state']=='OBSERVED' and value['snapshot_ref']==event.hash
    assert value['reported_equity']=='10250.5' and value['risk_equity']=='10000.0'
    assert value['valuation_state']=='CREDIT_EXCLUDED' and value['execution_authority'] is False
    assert row['equity']=='10000.0' and row['floating_pnl']=='0.0' and row['margin']['state']=='OBSERVED'
    assert row['margin']['risk_free_margin_bound']=='9000.0' and row['day_pnl'] is None
    assert not funding_risk_fence(ledger,adapter,adapter.sync_account(),now_ms=1000000).available
    assert ledger.count()==before and not sdk.sent


@pytest.mark.parametrize('credit', [None, -10.0])
def test_owner_receives_original_amounts_with_explicit_unknown_risk_valuation(tmp_path, credit):
    from test_mt5_funding_runtime import profile
    from vati.app.portfolio import account_states
    sdk, adapter, ledger, event = observed_owner(tmp_path, credit=credit)
    row = account_states(ledger, [profile()])[0]; value = row['native_account_observation']
    assert value['state']=='OBSERVED' and value['risk_equity'] is None
    assert value['reported_equity']=='10250.5' and row['balance']=='10000.0'
    assert row['equity'] is None and row['floating_pnl'] is None and row['margin']['state']=='UNAVAILABLE'
    assert row['raw_equity_change']['drawdown_from_raw_peak'] is None and not sdk.sent


@pytest.mark.parametrize('field,value', [('login','12345679'),('server','Different-Demo'),('currency','EUR'),('demo',False),('broker','CTRADER'),('login',None)])
def test_cash_outage_does_not_let_old_native_values_attach_to_changed_physical_profile(tmp_path, field, value):
    from test_mt5_funding_runtime import profile
    from vati.app.portfolio import account_states
    sdk, adapter, ledger, event = observed_owner(tmp_path)
    row = account_states(ledger, [profile(**{field:value})])[0]
    assert row['native_account_observation']['reason']=='CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'
    assert row['equity'] is None and row['balance'] is None and row['verified'] is False
    assert row['connection_state']=='STALE' and row['margin']['state']=='UNAVAILABLE'


@pytest.mark.parametrize('damage', ['authority','numeric-authority','source-seal','scope','future','bad-clock',
    'money','source-kind','alias','unknown-field','producer','snapshot-seal','snapshot-valuation'])
def test_original_account_readback_rejects_forged_or_unjoined_observations(tmp_path, damage):
    from copy import deepcopy
    from dataclasses import replace
    from vati.core.canonical import canonical_hash
    from test_mt5_funding_runtime import profile
    from vati.execution.mt5_observation import reported_account_observation
    sdk, adapter, ledger, event = observed_owner(tmp_path)
    p = deepcopy(event.payload); value=p['native_account_observation']
    if damage=='authority': value['execution_authority']=True
    elif damage=='numeric-authority': value['execution_authority']=0
    elif damage=='source-seal': value['source_ref']='0'*64
    elif damage=='scope': value['scope_hash']='0'*64
    elif damage=='future': value['observed_at_ms']=event.received_time_ms+1
    elif damage=='bad-clock': value['source_received_at_ms']=True
    elif damage=='money': value['risk_equity']='999999999'
    elif damage=='source-kind': value['source_kind']='LOG_IMPORT'
    elif damage=='alias': value['account_alias']='foreign'
    elif damage=='unknown-field': value['unearned_authority']='yes'
    elif damage=='producer': event=replace(event,producer='untrusted-import')
    elif damage=='snapshot-valuation': p['equity']='999999999'
    if damage not in {'source-seal','snapshot-seal'}:
        value['source_ref']=canonical_hash({k:v for k,v in value.items() if k!='source_ref'})
    event=replace(event,payload=p)
    if damage!='snapshot-seal': event=replace(event,hash=canonical_hash(event.body()))
    else: event=replace(event,hash='0'*64)
    row=reported_account_observation(event,profile())
    assert row['state']=='UNAVAILABLE' and row['execution_authority'] is False
    if damage!='snapshot-seal':
        from vati.app.portfolio import account_states
        ledger.append(event)
        projected=account_states(ledger,[profile()])[0]
        assert projected['equity'] is None and projected['balance'] is None
        assert projected['margin']['state']=='UNAVAILABLE' and projected['connection_state']=='STALE'


@pytest.mark.parametrize('credit', ['200', None])
def test_actual_pull_adapter_keeps_poll_and_read_clocks_without_cash_history(tmp_path, credit):
    from test_mt5_funding_contract import account
    from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
    from vati.execution.mt5_identity import Mt5Identity
    raw=account();raw.pop('funding');raw.update(trade_allowed=True,credit=credit)
    queue=BridgeQueue(tmp_path/'poll.sqlite');queue.set_state('native',raw,[],now_ms=9900,nonce='actual-poll-fixture')
    adapter=Mt5PullAdapter(queue,account_alias='native',clock=lambda:10000,
        identity=Mt5Identity('12345678','Broker-Demo','USD',True))
    result=adapter.sync_account(); value=result.native_observation
    assert result.funding_mark is None and value.source_kind=='MT5_SIGNED_EA_POLL'
    assert value.source_received_at_ms==9900 and value.observed_at_ms==10000
    assert value.source_nonce=='actual-poll-fixture'
    assert value.risk_equity==(D('10000') if credit is not None else None)
    assert queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0


def test_legacy_missing_observation_nonce_withholds_proof_without_disabling_protective_reads(tmp_path):
    from test_mt5_funding_contract import account
    from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
    from vati.execution.mt5_identity import Mt5Identity
    raw=account();raw.pop('funding');raw.update(trade_allowed=True)
    queue=BridgeQueue(tmp_path/'legacy-poll.sqlite');queue.set_state('native',raw,[],now_ms=9900,nonce=None)
    adapter=Mt5PullAdapter(queue,account_alias='native',clock=lambda:10000,
        identity=Mt5Identity('12345678','Broker-Demo','USD',True))
    value=adapter.sync_account()
    assert value.verified is True and value.native_observation is None and value.funding_mark is None
    assert adapter.positions()==[] and queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0


def test_legacy_alias_only_native_snapshot_cannot_supply_current_profile_money():
    from vati.core import Ledger, EventKind, make_event
    from vati.app.portfolio import account_states
    from test_mt5_funding_runtime import profile
    ledger=Ledger();ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',
        {'account_alias':'native','equity':'10000','balance':'10000','currency':'USD',
         'verified':True,'connected':True},event_time_ms=1000,received_time_ms=1000))
    row=account_states(ledger,[profile(server='Different-Demo')])[0]
    assert row['equity'] is None and row['balance'] is None and row['verified'] is False
    assert row['margin']['reason']=='NATIVE_SCOPE_UNBOUND' and row['connection_state']=='STALE'
