"""Read fixed Git objects only; no checkout, application import, merge or effect."""
import ast, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).parent
def git(*args): return subprocess.check_output(['git','--git-dir='+str(ROOT/'source.git'),*args])
refs=dict(line.split(' ',1) for line in git('for-each-ref','--format=%(refname) %(objectname)').decode().splitlines() if not line.startswith('refs/external/'))
rows=[]
paths=['trading/vati/execution/policy.py','trading/vati/execution/style_selector.py','trading/vati/execution/tca.py','trading/vati/execution/paper.py','trading/vati/execution/router.py','trading/vati/core/ledger.py','trading/vati/risk/lockouts.py','trading/vati/app/cycle.py','trading/vati/app/account_service.py','trading/vati/app/account_coordinator.py']
heads={}
for ref,sha in refs.items():heads.setdefault(sha,[]).append(ref)
for sha,names in heads.items():
 tree={}
 for line in git('ls-tree','-r',sha).decode().splitlines():
  meta,path=line.split('\t',1);mode,kind,blob=meta.split();tree[path]=(kind,blob)
 rows.append({'commit':sha,'refs':names,'tracked_paths':len(tree),'selected_blobs':{p:tree.get(p,[None,None])[1] for p in paths},'feature_paths':[p for p in tree if any(k in p.lower() for k in ['jev','temperament','muse','ownercontrol','owner_control','cognit'])]})
chosen={'opus':'refs/review-pr/101','canon':'refs/review-pr/93','modes':'refs/review-pr/92','cognition':'refs/review-pr/77','muse':'refs/review-pr/95','muse_interaction':'refs/review-pr/97','owner_controls':'refs/review-pr/98','studio':'refs/review-pr/99','review_inputs':'refs/heads/review/muse-vati-rev114-inputs-20261018'}
snaps=[]
for name,ref in chosen.items():
 sha=refs[ref]; files=git('ls-tree','-r','--name-only',sha).decode().splitlines()
 selected=set(p for p in paths if p in files)
 selected.update(p for p in files if p.endswith(('.py','.ts','.mjs','.kt')) and any(t in p.lower() for t in ['jev','temperament','learning_boundary','cognitive','muse','ownercontrols','owner_control']) and not '/tests/' in p and not '/test/' in p)
 for p in sorted(selected):
  raw=git('show',sha+':'+p);dest=ROOT/'source_review'/name/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
  syms=[]
  if p.endswith('.py'):
   try:
    tree=ast.parse(raw);syms=[{'name':n.name,'line':n.lineno,'end_line':n.end_lineno,'kind':type(n).__name__} for n in ast.walk(tree) if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]
   except SyntaxError:pass
  snaps.append({'label':name,'ref':ref,'commit':sha,'path':p,'sha256':hashlib.sha256(raw).hexdigest(),'symbols':syms})
 for pattern in ['ExecutionPolicyEngine','policy_engine.observe','execution_policy.observe','compute_tca','ExecutionStyleSelector','Jev','LearningBoundary']:
  r=subprocess.run(['git','--git-dir='+str(ROOT/'source.git'),'grep','-n','-F',pattern,sha,'--','trading/vati','services'],capture_output=True,text=True)
  if r.returncode not in (0,1):raise RuntimeError(r.stderr)
  q=ROOT/'source_review'/'callers'/name/(pattern.replace('.','_')+'.txt');q.parent.mkdir(parents=True,exist_ok=True);q.write_text(r.stdout)
report={'scope':'Complete fetched-ref head-tree inventory; selected file/symbol/caller evidence, not full semantic coverage or PR open-state proof','branch_heads':sum(r.startswith('refs/heads/') for r in refs),'pr_heads':sum(r.startswith('refs/review-pr/') for r in refs),'distinct_heads':len(heads),'refs':refs,'head_inventory':rows,'selected_files':snaps}
(ROOT/'source_review/SOURCE_RECONCILIATION_EVIDENCE.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['branch_heads','pr_heads','distinct_heads']}));print('selected source files',len(snaps))
