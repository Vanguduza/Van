from pathlib import Path
from contextlib import closing
from tempfile import TemporaryDirectory
import json,subprocess,hashlib

from test_native_balance_reconciliation import mark,snapshot,observe
from test_funding_risk_fence import native
from vati.core import Ledger,EventKind
from vati.funding.reconciliation import period_report
from vati.funding.risk_fence import funding_risk_fence

root=Path.cwd()
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert head=='d844aa437e83623d2ff5975927bff4f12849d10e'
assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
class RollbackFixture(Exception):pass
with TemporaryDirectory(prefix='van-period-read-baseline-') as tmp:
 path=Path(tmp)/'facts.sqlite'
 with closing(Ledger(path)) as ledger:
  snapshot(ledger,mark(1000));scope=observe(ledger)
  try:
   with ledger.atomic():
    original=snapshot(ledger,mark(3000,equity='110'),received=6500)
    before=period_report(ledger,scope)
    adapter,account=native(mark(7000,equity='110'))
    ready=funding_risk_fence(ledger,adapter,account,now_ms=7000)
    raise RollbackFixture()
  except RollbackFixture:pass
  present=any(e.hash==original.hash for e in ledger.iter(EventKind.ACCOUNT_SNAPSHOT))
  try:after=period_report(ledger,scope);same={'state':after['state']}
  except Exception as error:same={'exception':type(error).__name__,'reason':str(error)}
  with closing(Ledger(path)) as independent:
   durable=period_report(independent,scope);chain=independent.verify_chain()[0]
  result={'schema':'van.readonly-period-baseline-counterexample/1',
   'context':'ACTUAL_UNMODIFIED_COMMITTED_BASELINE_SQLITE_WRITER_ROLLBACK',
   'source_head':head,'baseline_checkout_clean':True,
   'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in
    ['trading/vati/core/ledger.py','trading/vati/funding/reconciliation.py','trading/vati/funding/risk_fence.py']},
   'clock_order':'cash/deal receipt6000, staged closing receipt6500, current native mark/decision7000',
   'before_commit_report_state':before['state'],'claimed_return':before['performance']['flow_neutral_return'],
   'funding_prerequisite_before_commit_available':ready.available,'funding_prerequisite_reason':ready.reason,
   'staged_closing_ref':original.hash,'reference_present_after_rollback':present,
   'same_connection_first_read_after_rollback':same,
   'fresh_connection_after_rollback_state':durable['state'],
   'fresh_connection_after_rollback_reason':durable['reason'],
   'independent_chain_valid_after_rollback':chain,
   'qualification':'SOURCE_FIXTURE_COUNTEREXAMPLE_NO_NATIVE_FINANCIAL_EFFECT'}
  assert before['state']=='MEASURED' and ready.available and not present
  assert same=={'exception':'LedgerError','reason':'native_period_journal_invalid'}
  assert durable['state']=='UNMEASURED' and chain
  assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
  Path('/workspace/van-period-writer-baseline-counterexample-20261026.json').write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result))
