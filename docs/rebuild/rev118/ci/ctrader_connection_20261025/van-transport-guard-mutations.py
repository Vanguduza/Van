import hashlib,json,pathlib,sys
root=pathlib.Path('/workspace/van-review-2026-10-18/publish')
sys.path.insert(0,str(root/'tools/audit'))
from mutation import run,JOURNAL
out=pathlib.Path('/workspace/van-transport-guard-mutations');out.mkdir(exist_ok=True)
t='trading/vati/execution/ctrader/transport.py';a='trading/vati/execution/ctrader/adapter.py'
cases=[
(t,'if self._sock is not sock:\n                return','if False:\n                return','retired socket may retire replacement'),
(t,'reader.join(self.timeout_s)','pass  # deliberately omit owned reader join','close returns before owned reader finishes'),
(t,'if self._pending_sockets.get(cid) is sock:','if False:','pending original is not woken on close'),
(t,'elif raw is not None:\n                    raw.close()','elif raw is not None:\n                    pass','TLS refusal leaks raw socket'),
(a,'self._auth_connection == getattr(self.transport, "connection_id", None)','True','cached authentication ignores replacement connection'),
(a,'or native_integer(body["ctidTraderAccountId"], minimum=1) != account','or False','native account authentication accepts another account'),
(a,'if getattr(self.transport, "connection_id", None) != connection:\n                raise ValueError("native symbol connection changed during refresh")','if False:\n                raise ValueError("native symbol connection changed during refresh")','mixed-connection contract snapshot is published'),
(a,'self._last_spot.clear()','pass  # deliberately retain old quote cache','reconnect reuses original quote cache'),
(t,'if self._sock is not sock:\n                    return None','if False:\n                    return None','retired subscription quote is delivered after reconnect'),
]
original={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in (t,a)}
observed=[]
def observe(kind,reason,result):
 index=len(observed)
 log=out/f'{index:02d}-{kind}.log';log.write_text(result.stdout+result.stderr)
 observed.append({'kind':kind,'reason':reason,'exit':result.returncode,'log':log.name})
survived=run(cases,['trading/tests/test_ctrader_transport_lifecycle.py','trading/tests/test_ctrader_connection_auth.py'],root=root,cwd=root,observe=observe)
restored={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in original}
assert original==restored and not JOURNAL.exists()
receipt={'schema':'van.ctrader-connection-guard-mutations/1','scope':'nine supplemental component mutants, separate from canonical374','observed':observed,'survived':survived,'source_sha256':original,'restored':True,'journal_absent':True}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert not survived
