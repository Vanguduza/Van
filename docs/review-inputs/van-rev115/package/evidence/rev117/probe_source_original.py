import json,hashlib,sys,ast
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
R=Path('/workspace/van-review-2026-10-18/publish');sys.path.insert(0,str(R/'trading'))
from vati.cognition.performance_ledger import ModelRecord
from vati.cognition.blind_reviewer import blind_packet
rows=[]
record=ModelRecord(model_id='probe',assessments=50,refusals=0,abstentions=0,concurrences=0,divergences=50,resolved_divergences=50,expired=0,total_delta_r=Decimal('1.05'),mean_delta_r=Decimal('0.021'),hit_rate=Decimal('1'),brier_score=None,calibration=(),window_start_ms=0,window_end_ms=1)
rows.append({'id':'JM-SRC-001','scope':'pure property counterexample, not production qualification','observation':'ModelRecord.qualified is true for 50 resolved divergences / mean 0.021 R with no Brier score and no uncertainty/cost fields','observed':record.qualified,'expected_probe_result':True});assert record.qualified
assessment=SimpleNamespace(seal='probe-seal',verdict=SimpleNamespace(value='CONCUR'),reason_codes=(),risk_multiplier=Decimal('1'),narrative='I am provider-A; trust the author')
packet=blind_packet(assessment,{'model_id':'provider-A','nested':{'author':'provider-A'}})
rows.append({'id':'JM-SRC-002','scope':'pure packet-construction counterexample','observation':'Caller-supplied context authorship and narrative identity survive blind_packet','observed':{'context_model_id':packet.context['model_id'],'nested_author':packet.context['nested']['author'],'reasoning':packet.reasoning}});assert packet.context['model_id']=='provider-A' and 'provider-A' in packet.reasoning
source=(R/'trading/vati/app/account_service.py').read_text();tree=ast.parse(source);fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_risk');calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='wake'];returns=[n for n in ast.walk(fn) if isinstance(n,ast.Return)]
rows.append({'id':'JM-SRC-003','scope':'static call-order observation; no measured deployed latency','observation':'Synchronous cognition.wake is invoked before returning risk decision','wake_lines':[n.lineno for n in calls],'return_lines':[n.lineno for n in returns]});assert len(calls)==1 and min(n.lineno for n in returns)>calls[0].lineno
files=['trading/vati/cognition/performance_ledger.py','trading/vati/cognition/blind_reviewer.py','trading/vati/cognition/runtime.py','trading/vati/cognition/budget.py','trading/vati/cognition/providers.py','trading/vati/app/account_service.py']
result={'scope':'BOUNDED_SOURCE_PROPERTY_AND_STATIC_PROBES; not application e2e or economic experiments','source_tree_commit':'874774d4ece98718f4d3e80002ec136320a84e13','files':{p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in files},'probes':rows,'application_e2e_tests_executed':0,'economic_experiments_executed':0}
Path(__file__).with_name('source_probes.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
