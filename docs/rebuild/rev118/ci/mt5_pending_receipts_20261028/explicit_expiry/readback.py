from pathlib import Path
import sys,json,hashlib,tempfile
from dataclasses import replace
sys.path[:0]=['/workspace/van-review-2026-10-18/publish/trading','/workspace/van-review-2026-10-18/publish/trading/tests']
from test_mt5_pending_receipts import command
from vati.execution.mt5_pull import BridgeQueue,Mt5PullAdapter
from vati.execution.mt5_identity import Mt5Identity
root=Path('/workspace/van-review-2026-10-18/publish');identity=Mt5Identity('12345678','broker-demo','USD',True)
out=[]
with tempfile.TemporaryDirectory(prefix='van-original-expiry-') as folder:
 for status in ['ACCEPTED','FILLED','PARTIAL','REJECTED','CANCELLED','EXPIRED','QUEUED','TAKEN']:
  path=Path(folder)/(status+'.sqlite');q=BridgeQueue(path);second=None
  try:
   cmd=replace(command(),expires_at_ms=200,command_hash='').sealed()
   adapter=Mt5PullAdapter(q,identity=identity,clock=lambda:130)
   cid=q.enqueue('mt5_ea','ORDER_SEND_EXPIRING',adapter._entry_body(cmd),now_ms=100)
   if status!='QUEUED':assert q.take_pending('mt5_ea',now_ms=110,expected_identity=identity)[0]['id']==cid
   if status not in ['QUEUED','TAKEN']:
    native={'status':status,'order':18446744073709551615,'sl_confirmed':True}
    if status in ['FILLED','PARTIAL']:
     native|={'volume':str(cmd.quantity if status=='FILLED' else cmd.quantity/2),'price':str(cmd.entry_price),'position':42,'server_time_ms':115}
    assert q.complete('mt5_ea',cid,native,now_ms=120)
   original=adapter.recover_entry(cmd,now_ms=130)
   assert original.status==(status if status not in ['QUEUED','TAKEN'] else 'UNKNOWN')
   second=BridgeQueue(path);historical=Mt5PullAdapter(second,identity=identity,clock=lambda:60000)
   assert historical.recover_entry(cmd,now_ms=60000)==original
   assert historical.submit(cmd,now_ms=60000)==original
   assert len(second.native_entries('mt5_ea'))==1
   assert original.received_time_unix_ms==(120 if status not in ['QUEUED','TAKEN'] else None)
   out.append({'original_status':status,'after_expiry_status':original.status,'original_received_ms':original.received_time_unix_ms,'receipt_hash':original.receipt_hash,'original_claims':1,'passed':True})
  finally:
   if second is not None:second.close()
   q.close()
result={'schema':'van.mt5-original-expired-command-recovery/1','source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['trading/vati/execution/mt5_pull.py','trading/tests/test_mt5_pending_receipts.py']},'checks':out,'native_effects_executed':False,'scope':'Real SQL original bounded command and historical completion recovery; no native terminal execution.'}
Path('/workspace/van-mt5-pending-receipt-expiry-readback-20261028.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':len(out),'native_effects_executed':False}))
