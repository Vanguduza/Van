from pathlib import Path
import json,xml.etree.ElementTree as ET,collections,hashlib,datetime
W=Path('/workspace');C=W/'van-auth-corrected-collection-r2-20261101';O=W/'van-storage-recovery-sets-20261101';O.mkdir(exist_ok=False)
def key(n):
 head,marker,param=n.partition('[');p=head.split('::');return (p[0][:-3].replace('/','.')+('.'+'.'.join(p[1:-1]) if len(p)>2 else ''),p[-1]+(marker+param if marker else ''))
def plan(label,expected,lookup,xml):
 cases=ET.parse(xml).findall('.//testcase');observed={};bad=set();skip=set()
 for c in cases:
  k=(c.get('classname'),c.get('name'));assert k in lookup,(label,k);nid=lookup[k];observed.setdefault(nid,[]).append(c)
  if c.find('failure') is not None or c.find('error') is not None:bad.add(nid)
  if c.find('skipped') is not None:skip.add(nid)
 unexecuted=expected-set(observed);recovery=sorted(bad|unexecuted);passed={nid for nid,rows in observed.items() if all(r.find('failure') is None and r.find('error') is None and r.find('skipped') is None for r in rows)};assert not passed&bad
 doc={'label':label,'expected_unique_cases':len(expected),'observed_unique_cases':len(observed),'fully_passed_original_cases':sorted(passed),'declared_skip_cases':sorted(skip-bad),'failed_or_error_cases':sorted(bad),'unexecuted_cases':sorted(unexecuted),'recovery_cases':recovery,'recovery_count':len(recovery),'original_xml':str(xml),'original_xml_sha256':hashlib.sha256(Path(xml).read_bytes()).hexdigest(),'original_failed_run_reclassified_as_success':False}
 (O/(label+'.json')).write_text(json.dumps(doc,indent=2)+'\n');(O/(label+'-targets.txt')).write_text('\n'.join(recovery)+'\n');return {k:len(v) if isinstance(v,list) else v for k,v in doc.items() if k not in ['original_xml_sha256']}
results=[]
for label,stem in [('selected','van-auth-corrected-affected-20261101'),('remainder','van-auth-corrected-remainder-20261101')]:
 manifest=json.load(open(C/(label+'.json')));lookup={key(raw):nid for raw,nid in zip(manifest['raw_nodeids'],manifest['nodeids'],strict=True)};assert len(lookup)==manifest['total'];results.append(plan(label,set(manifest['nodeids']),lookup,W/(stem+'.xml')))
P=W/'van-successor-regression-pg-r2-20261101';events=[json.loads(line) for line in (P/'test-events.jsonl').read_text().splitlines()];expected={x['nodeid'] for x in events};lookup={key(n):n for n in expected};assert len(lookup)==5775;results.append(plan('successor',expected,lookup,P/'full-trading.xml'))
(O/'summary.json').write_text(json.dumps({'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_unchanged':True,'plans':results},indent=2)+'\n');print(json.dumps(results),flush=True)
