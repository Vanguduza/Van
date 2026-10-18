#!/usr/bin/env python3
"""Read-only paper-adapter diagnostic on the pinned Opus checkout; sends no real order.

This detects existing defects; success of this script is NOT repaired application
qualification. It refuses an unexpected source head and leaves tracked files alone.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from decimal import Decimal as D
from pathlib import Path
SHA='a39f241b0135cf92cc5a6b9a28af226aa294603d'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True,type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args();r=a.repo.resolve()
 head=subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip()
 if head!=SHA:raise ValueError('SOURCE_MISMATCH:'+head)
 sys.path.insert(0,str(r/'trading'))
 from vati.execution import PaperAdapter
 from vati.execution.base import OrderCommand,StopMode
 from vati.risk.contracts import Direction,LossModel
 from vati.execution.policy_templates import DEFAULT_TEMPLATES,STOP_ENTRY
 rows=[]
 for side in [Direction.LONG,Direction.SHORT]:
  pa=PaperAdapter(spread=D('0.00010'),slippage=D('0.00002'))
  pa.mark('EURUSD',D('1.09995'),D('1.10005'),now_ms=0)
  lim=D('1.10000');stop=D('1.09700') if side is Direction.LONG else D('1.10300')
  cmd=OrderCommand('test-'+side.value,'d'*64,'k-'+side.value,'paper_primary','paper','EURUSD',side,'LIMIT',D('0.10'),lim,stop,StopMode.VENUE,LossModel.STOP_DISTANCE,max_slippage=D('0.0003')).sealed()
  rec=pa.submit(cmd,now_ms=1)
  worsened=rec.average_fill is not None and ((rec.average_fill>lim) if side is Direction.LONG else (rec.average_fill<lim))
  rows.append({'side':side.value,'requested_limit':str(lim),'reported_status':rec.status,'reported_fill':str(rec.average_fill),'limit_boundary_violated':worsened})
 pa=PaperAdapter();pa.mark('EURUSD',D('1.09995'),D('1.10005'),now_ms=0)
 cmd=OrderCommand('rest','d'*64,'rest-k','paper_primary','paper','EURUSD',Direction.LONG,'STOP',D('0.10'),D('1.10200'),D('1.09900'),StopMode.VENUE,LossModel.STOP_DISTANCE,max_slippage=D('0.0003')).sealed();pa.submit(cmd,now_ms=1)
 pending=list(pa.pending.values())[0];policy=DEFAULT_TEMPLATES[STOP_ENTRY]
 result={'schema':'van.source.counterexample/1.0','scope':'PAPER_ADAPTER_ONLY_NO_LIVE_ORDER_NO_FIX','source_sha':head,'source_file_sha256':hashlib.sha256((r/'trading/vati/execution/paper.py').read_bytes()).hexdigest(),'limit_probes':rows,'expiry_probe':{'adapter_wait_ms':pending['expires_ms']-1,'policy_max_wait_ms':policy.max_wait_ms,'different':pending['expires_ms']-1!=policy.max_wait_ms},'tracked_files_clean':not subprocess.check_output(['git','-C',str(r),'status','--porcelain=v1','-uno'],text=True).strip()}
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:print(str(e),file=sys.stderr);raise SystemExit(2)
