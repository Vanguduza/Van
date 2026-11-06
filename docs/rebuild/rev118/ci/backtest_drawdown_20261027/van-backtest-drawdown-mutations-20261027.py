from pathlib import Path
from decimal import Decimal as D
from fractions import Fraction
import hashlib,sys,types,json
path=Path('/workspace/van-review-2026-10-18/publish/trading/vati/backtest/metrics.py')
original=path.read_bytes();source=original.decode()
probes=[('earlier_percentage_peak',D(100),[D(-50),D(950),D(-100)],100.0,.5),
        ('negative_equity_drawdown',D(100),[D(-150),D(1050),D(-200)],200.0,1.5),
        ('native_cent',D('1e30'),[D('-.01')],.01,1e-32)]
def run(code,name):
 module=types.ModuleType(name);sys.modules[name]=module
 try:
  exec(compile(code,str(path),'exec'),module.__dict__)
  result=[]
  for label,start,pnls,amount,ratio in probes:
   value=module.compute_metrics(pnls,[D(0)]*len(pnls),start)
   result.append({'case':label,'passed':value.max_drawdown==amount and value.max_drawdown_pct==ratio,
                  'actual':[value.max_drawdown,value.max_drawdown_pct]})
  return result
 finally:sys.modules.pop(name,None)
baseline=run(source,'van_drawdown_positive');assert all(row['passed'] for row in baseline)
old='''        mdd = max(mdd, dd)
        if peak:
            mdd_pct = max(mdd_pct, dd / peak)'''
new='''        if dd > mdd:
            mdd = dd
            mdd_pct = dd / peak if peak else Fraction(0)'''
assert source.count(old)==1
assert source.count('eq = Fraction(start_equity)')==1
mutants=[('coupled_percentage_maximum',source.replace(old,new,1)),
         ('float_equity_path',source.replace('eq = Fraction(start_equity)','eq = float(start_equity)',1))]
reports=[]
for index,(name,code) in enumerate(mutants):
 assert code!=source
 rows=run(code,'van_drawdown_mutant_'+str(index));assert any(not row['passed'] for row in rows)
 reports.append({'mutation':name,'mutated_source_sha256':hashlib.sha256(code.encode()).hexdigest(),
                 'caught_by':[row['case'] for row in rows if not row['passed']],'probes':rows})
restored=run(source,'van_drawdown_restored');assert all(row['passed'] for row in restored)
assert path.read_bytes()==original
report={'schema':'van.rebuild.backtest-drawdown-supplemental-faults/1',
        'source_sha256':hashlib.sha256(original).hexdigest(),'positive_controls':baseline,'faults':reports,
        'restored_controls':restored,'source_unchanged':True,'canonical_registry_cases_executed':False,
        'qualification':'Two supplemental in-memory source faults; no active source mutation, live trade, admission or profitability evidence.'}
Path('/workspace/van-backtest-drawdown-mutations-20261027.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'caught':len(reports),'positive':len(baseline),'restored':len(restored),'source_unchanged':True}))
