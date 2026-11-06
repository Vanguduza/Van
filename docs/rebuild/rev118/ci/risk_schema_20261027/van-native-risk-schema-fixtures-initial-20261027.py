from pathlib import Path
from dataclasses import replace
from decimal import Decimal as D
import tempfile,json,hashlib,subprocess,sys
root=Path('/workspace/van-review-2026-10-18/publish');sys.path[:0]=[str(root/'trading/tests'),str(root/'trading')]
from test_native_risk_account_context import mt5_context
from test_funding_runtime import setup as ctrader_setup
from vati.risk.account_context import context_for_account
from vati.risk.serde import snapshot_from_dict,snapshot_to_dict
from vati.risk.contracts import OpenPosition,StopRiskTerms,Direction
base=snapshot_from_dict(json.loads((root/'trading/tests/fixtures/legacy_risk_snapshot_b58bb578.json').read_text())['snapshot'])
examples={}
with tempfile.TemporaryDirectory(prefix='van-risk-schema-fixture-',dir='/workspace') as folder:
    ledger,adapter,account,captured,context=mt5_context(Path(folder))
    try:
        position=OpenPosition(symbol='EURUSD',direction=Direction.LONG,lots=D('.1'),stop_distance=D('.001'),
            value_per_price_unit_per_lot=D('100000'),base_currency='EUR',quote_currency='USD',
            broker_position_id=None,stop_terms=StopRiskTerms(D('1.1000'),D('1.0990'),D('.00001'),D('1.00')))
        value=replace(base,account_alias=account.account_alias,equity=account.equity,balance=account.balance,
            native_account_context=context,open_positions=(position,))
        examples['MT5']=snapshot_to_dict(value)
        assert context.source_query_ref==next(ledger.iter(__import__('vati.core',fromlist=['EventKind']).EventKind.FUNDING_MT5_QUERY)).hash
    finally:ledger.close();adapter.queue._conn.close()
with tempfile.TemporaryDirectory(prefix='van-risk-schema-ctrader-',dir='/workspace') as folder:
    ledger,transport,adapter=ctrader_setup(Path(folder))
    try:
        account=adapter.sync_account();before=list(transport.requests)
        context=context_for_account(ledger,adapter,account,now_ms=3000)
        value=replace(base,account_alias=account.account_alias,equity=account.equity,balance=account.balance,
            symbol_contract=replace(base.symbol_contract,venue='ctrader',account_currency=account.currency),
            native_account_context=context)
        examples['CTRADER']=snapshot_to_dict(value)
        assert transport.requests==before and context.execution_authority is False
    finally:ledger.close()
files=['trading/vati/risk/contracts.py','trading/vati/risk/serde.py','trading/vati/risk/account_context.py','trading/vati/funding/mt5_journal.py']
hashes={}
for name in files:
    raw=(root/name).read_bytes();assert raw==subprocess.check_output(['git','show','e9cbdd69c9d98688e14b088c19c65e5df80c6e42:'+name],cwd=root)
    hashes[name]=hashlib.sha256(raw).hexdigest()
receipt={'schema':'van.source-risk-schema-fixtures/1','source_head':'e9cbdd69c9d98688e14b088c19c65e5df80c6e42',
    'source_sha256':hashes,'generator':'Actualproduction serializers and native-context builders over canonical isolated MT5/cTrader source fixtures, including actual SQLite MT5 query; no live provider/network/order/owner-authority effects.',
    'execution_authority':False,'economic_evidence':False,'snapshots':examples}
out=root/'tests/rebuild/fixtures/native_risk_snapshots_e9cbdd69.json';assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'fixture':str(out),'providers':list(examples),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'source_only':True}))
