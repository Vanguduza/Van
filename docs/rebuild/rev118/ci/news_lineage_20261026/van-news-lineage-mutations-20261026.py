from pathlib import Path
import os,subprocess,json,hashlib
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-news-lineage-mutations-20261026');out.mkdir(exist_ok=True)
variants={'discard-rewritten-origin-connection': ('trading/vati/events/news_lineage.py', "union(key, 'origin:' + canonical_hash(origin['origin']))", 'pass'), 'qualify-declared-sources': ('trading/vati/events/news_lineage.py', "'qualified_independent_sources': 0", "'qualified_independent_sources': 2"), 'skip-original-lineage-readback': ('trading/vati/events/news_ingress.py', 'if lineage is not None and confirmed!=lineage:', 'if False:'), 'ignore-required-origin-recovery': ('trading/vati/events/news_ingress.py', 'for oid,required in required_origins.items():', 'for oid,required in {}.items():'), 'backdate-enrichment': ('trading/vati/events/news_ingress.py', 'at=max(available_ms,existing_observation[1]) if existing_observation is not None else available_ms', 'at=available_ms'), 'discard-recovered-lineage': ('trading/vati/events/news_ingress.py', 'recovered._ledger=ledger;recovered._recovered=True', 'recovered._origins={};recovered._ledger=ledger;recovered._recovered=True'), 'accept-invalid-origin': ('trading/vati/events/news_ingress.py', "origin=PublisherOrigin.parse(row['original_publisher']) if 'original_publisher' in row else None", 'origin=None'), 'ignore-origin-availability': ('trading/vati/events/news_lineage.py', "if origin is not None and origin['available_ms'] > now_ms:", 'if False:')}
originals={path:(root/path).read_text() for path,_,_ in variants.values()};receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(path,old,new) in variants.items():
  original=originals[path];assert original.count(old)==1,(name,original.count(old));mutated=original.replace(old,new);(root/path).write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_news_publisher_lineage.py','-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=45)
  receipts.append({'case':name,'path':path,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});(root/path).write_text(original)
finally:
 for path,body in originals.items():(root/path).write_text(body)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':{p:hashlib.sha256(s.encode()).hexdigest() for p,s in originals.items()},'source_restored':all((root/p).read_text()==s for p,s in originals.items()),'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
print('8 fault subprocesses exit1; inspect JUnit assertions/errors independently')
