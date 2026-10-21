"""Independent document/source arithmetic probes; no application or venue execution."""
import copy, hashlib, importlib.util, json, re
from pathlib import Path
from decimal import Decimal as D
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parent
P = ROOT/'input/VAN_NEXT_UNIFIED_REBUILD_REV1_14_20261018'
spec = importlib.util.spec_from_file_location('baseline_document_checker', P/'verification/verify_rev114.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
d = {k:v.read(p) for k,p in v.FILES.items()}
parents = {k:v.read('lineage/rev1_13/'+p)[field] for k,(p,field) in v.PARENTS.items()}
rows=[]
def row(id, observed, expected, classification, **extra):
    rows.append(dict(id=id,observed=observed,expected=expected,classification=classification,**extra))

x=copy.deepcopy(d)
t=next(t for m in x['machines']['machines'] if m['id']=='SO-CHILD' for t in m['transitions'] if t['to']=='SUBMITTING')
t['proof_predicates'].remove('POLICY_QUALIFIED')
# Deliberately bypass byte identity to challenge the semantic checker, as its own selftests do.
row('DOC-DISPATCH-POLICY',v.check(x,parents,False),['CRITICAL_EDGE_PROOF_MISSING:SO-CHILD-T002:POLICY_QUALIFIED'],'DOCUMENT_VERIFIER_GAP',file_hash_checks=False)

child=next(m for m in d['machines']['machines'] if m['id']=='SO-CHILD')
edges={(t['from'],t['to']) for t in child['transitions']}
for a,b in [('OUTCOME_UNKNOWN','CANCELLED'),('OUTCOME_UNKNOWN','EXPIRED'),('CANCEL_REQUESTED','OUTCOME_UNKNOWN')]:
    row('DOC-EDGE-'+a+'-'+b,(a,b) in edges,True,'MISSING_RECOVERY_CONTRACT')

s=d['schemas']; validator=Draft202012Validator(s)
examples={}
for rel in d['example_index']['fixtures']:
    z=v.read('contracts/self_optimization/'+rel);examples[z['record_type']]=z
z=copy.deepcopy(examples['CryptoVenueProfile']);z['price_tick']='0';z['base_step']='0'
row('DOC-ZERO-TICK',validator.is_valid(z),False,'SCHEMA_SEMANTIC_GAP',input=z)
z=copy.deepcopy(examples['ExecutionQualityMeasurement']);z['measurement_state']='MATURE'
z['explicit_nonembedded_cost_quote']=None;z['total_benchmark_loss_quote']=None
row('DOC-MATURE-UNKNOWN-COST',validator.is_valid(z),False,'SCHEMA_SEMANTIC_GAP',input=z)
pat=s['$defs']['CryptoVenueProfile']['properties']['price_tick']['pattern']
row('DOC-DECIMAL-POSITIVE-CONTROL',{q:bool(re.fullmatch(pat,q)) for q in ['0.001','12.50','12\\x50']},{'0.001':True,'12.50':True,'12\\x50':False},'NO_DEFECT')

f=copy.deepcopy(d['fixture']);before=v.fixture_model(f)
# Fixture has no revision precedence. Distinct old revision arriving later can replace corrected truth.
e=copy.deepcopy(f['events'][0]);e.update(id='pA1-correction-r2',cursor=7,observation_revision=2,fill_price='99.0')
f['events'].append(e)
e2=copy.deepcopy(e);e2.update(id='pA1-late-r1',cursor=8,observation_revision=1,fill_price='105.0');f['events'].append(e2)
out=v.fixture_model(f)
row('DOC-STALE-REVISION',{'choices':out[0],'means':out[1]},'revision 1 cannot replace revision 2 in RESTATED state','REFERENCE_MODEL_GAP',input=f)

# Hand-derived counterexamples to inspected source formulas. No app imports or runtime results.
total=D('200');depth=D('10');participation=D('.25');slices=min(8,int(total/(depth*participation)))
row('SRC-SLICE-CAP',{'slice_quantity':str(total/slices),'cap':str(depth*participation),'ratio':str((total/slices)/(depth*participation))},'all slices <= cap or explicit infeasible refusal','STATIC_SOURCE_ARITHMETIC_COUNTEREXAMPLE',source='trading/vati/execution/style_selector.py:ExecutionStyleSelector._slice',source_sha='a39f241b0135cf92cc5a6b9a28af226aa294603d')
decision=D('100');arrival=D('100');submitted=D('99');fill=D('99');spread=D('2')
row('SRC-TCA-DECOMPOSITION',{'source_formula':str(fill-submitted+arrival-decision+spread/2),'fill_vs_decision':str(fill-decision)},'direct implementation shortfall -1; decomposition must sum to that value','STATIC_SOURCE_ARITHMETIC_COUNTEREXAMPLE',source='trading/vati/execution/tca.py:compute_tca',source_sha='a39f241b0135cf92cc5a6b9a28af226aa294603d')
row('SPEC-GROSS-FEE',{'gross_fill':'1','base_fee':'0.01','net_inventory':'0.99','incorrect_remaining':'0.01'},'gross execution budget exhausted; fee does not create a second buy allowance','SPECIFICATION_DISAMBIGUATION')
report={'scope':'DOCUMENT_CONFORMANCE_AND_STATIC_SOURCE_ARITHMETIC_ONLY','application_tests_executed':0,'venue_calls':0,'historical_backtests_executed':0,'profitability_claim':False,'probes':rows,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(ROOT/'independent_probe_results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'scope':report['scope'],'probes':len(rows),'classifications':{k:sum(r['classification']==k for r in rows) for k in sorted({r['classification'] for r in rows})}},indent=2))
