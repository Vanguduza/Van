from pathlib import Path
import os,subprocess,json,hashlib
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-news-rss-mutations-20261026');out.mkdir(exist_ok=True)
variants={'renew-unchanged-raw-clock': ('trading/vati/events/news_runtime.py', "observed_ms=news.source_snapshot['captured_ms']", 'observed_ms=now_ms'), 'skip-raw-readback': ('trading/vati/events/news_feed.py', 'if confirmed is None or confirmed.hash != original.hash or confirmed.payload != original.payload:', 'if False:'), 'guess-unzoned-publication': ('trading/vati/events/news_feed.py', 'if date.tzinfo is None or date.utcoffset() is None:', 'if False:'), 'invent-origin-from-title': ('trading/vati/events/news_feed.py', "key=_text(item,'guid') or link", "key=_text(item,'guid') or link or title"), 'accept-dtd': ('trading/vati/events/news_feed.py', "raise ValueError('RSS DTD/entity declarations are unsupported')", 'pass'), 'ignore-original-raw-checksum': ('trading/vati/events/news_feed.py', "or hashlib.sha256(raw).hexdigest() != value['raw_sha256']", 'or False'), 'ignore-missing-snapshot-recovery': ('trading/vati/events/news_ingress.py', 'if snapshots_seen!=ledger.count(EventKind.NEWS_SOURCE_SNAPSHOT):', 'if False:'), 'alias-owner-snapshot-report': ('trading/vati/events/news_ingress.py', 'else deepcopy(self.source_health)', 'else dict(self.source_health)')}
originals={path:(root/path).read_text() for path,_,_ in variants.values()};receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(path,old,new) in variants.items():
  original=originals[path];assert original.count(old)==1,(name,original.count(old));mutated=original.replace(old,new);(root/path).write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_news_rss_feed.py','-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=45)
  receipts.append({'case':name,'path':path,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});(root/path).write_text(original)
finally:
 for path,body in originals.items():(root/path).write_text(body)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':{p:hashlib.sha256(s.encode()).hexdigest() for p,s in originals.items()},'source_restored':all((root/p).read_text()==s for p,s in originals.items()),'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
print('8 fault subprocesses exit1; inspect JUnit assertions/errors independently')
