"""Verify exact collected node identities against actual shard JUnit results."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,subprocess,datetime

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def verify(collection_dir, prefixes, source_pins):
    directory=Path(collection_dir);receipt=read(directory/'receipt.json')
    assert receipt['full_equals_disjoint_union'] is True
    assert receipt['source_pins_sha256']==sha(source_pins)
    for name,h in receipt['manifests'].items():assert sha(directory/name)==h,name
    env_pins=read(Path(source_pins).parent/'van-auth-shared-shard-environment-20261101.json')
    root=Path(env_pins['same_worktree'])
    for f,h in env_pins['source_config_fixture_files'].items():assert sha(root/f)==h,('fixture/config drift',f)
    for f,h in read(source_pins)['files'].items():assert sha(root/f)==h,('source drift',f)
    assert not env_pins['package_files_modified_or_metadata_changed_since_selected_start']
    assert not env_pins['source_config_fixture_files_modified_since_selected_start']
    freeze=subprocess.check_output([env_pins['same_python'],'-m','pip','freeze'],text=True)
    assert hashlib.sha256(freeze.encode()).hexdigest()==env_pins['package_freeze_sha256']
    package_root=Path(env_pins['same_python']).parent.parent/'lib/python3.12/site-packages'
    start=datetime.datetime.fromisoformat(env_pins['selected_started_at_utc']).timestamp()
    assert all(max(p.stat().st_mtime,p.stat().st_ctime)<=start for p in package_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'), 'package file metadata drift'
    full=read(directory/'full.json');expected=set(full['nodeids']);seen=set();results=[];allskips=[]
    for label,prefix in zip(['selected','remainder'],prefixes,strict=True):
        prefix=Path(prefix);manifest=read(directory/(label+'.json'));terminal=read(prefix.with_suffix('.json'))
        assert terminal['state']=='COMPLETED' and terminal['exit']==0,label
        audit=read(prefix.parent/(prefix.name.replace('-20261101','-audit-20261101')+'.json'))
        assert audit['forbidden_events']==[],label
        lookup={}
        for raw,canonical in zip(manifest['raw_nodeids'],manifest['nodeids'],strict=True):
            head,marker,param=raw.partition('[');parts=head.split('::');name=parts[-1]+(marker+param if marker else '')
            key=(parts[0][:-3].replace('/','.')+('.'+'.'.join(parts[1:-1]) if len(parts)>2 else ''),name)
            assert key not in lookup,key
            lookup[key]=canonical
        actual=set();passed=0;skips=[]
        for case in ET.parse(prefix.with_suffix('.xml')).findall('.//testcase'):
            key=(case.get('classname'),case.get('name'));assert key in lookup,(label,key)
            nid=lookup[key];assert nid not in actual,nid;actual.add(nid)
            assert case.find('failure') is None and case.find('error') is None,(label,nid)
            if case.find('skipped') is not None:skips.append({'name':nid,'reason':case.find('skipped').get('message','')})
            else:passed+=1
        assert actual==set(manifest['nodeids']),(label,'execution identity mismatch')
        assert not actual&seen,label;seen.update(actual);allskips.extend(skips)
        results.append({'label':label,'prefix':str(prefix),'terminal_sha256':sha(prefix.with_suffix('.json')),'xml_sha256':sha(prefix.with_suffix('.xml')),'tests':len(actual),'passed':passed,'skipped':len(skips),'skip_cases':skips})
    assert seen==expected,'Full corrected collection does not equal disjoint executed union'
    return {'schema':'van.auth-corrected-sharded-coverage/1','tests':len(expected),'passed':sum(x['passed'] for x in results),'skipped':len(allskips),'failures':0,'errors':0,'skip_cases':allskips,'shards':results,'full_corrected_collection_equals_disjoint_executed_union':True,'source_pins_sha256':sha(source_pins),'collection_receipt_sha256':sha(directory/'receipt.json')}
