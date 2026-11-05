#!/usr/bin/env python3
"""Owner-approved isolated debug-character package; never a Forge/release admission.

Only the dedicated characterReview variant receives these generated assets.
Default debug and release asset merges must reject all review payloads.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, tempfile, zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
REQUEST='android/character-review/REVIEW_REQUEST.json'
OUTPUT='android/app/build/generated/van-character-review'
APP='com.dial.van.characterreview'
VARIANT='characterReview'
NAMES={'rive':'van_review.riv','context':'van_review.context.json','marker':'van-character-review.json'}
PREFIX='visual-authority/character-forge/08-prototypes/candidate-b-mechanics/raster-full-r5/'
MAX_RIVE=8*1024*1024
MAX_CONTEXT=16_384

def require(ok, message):
    if not ok:raise ValueError(message)

def sha_bytes(data):return hashlib.sha256(data).hexdigest()
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def file_at(root,relative):
    p=PurePosixPath(relative)
    require(not p.is_absolute() and '..' not in p.parts and p.parts,'Unsafe input path')
    file=root.joinpath(*p.parts)
    require(file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(root.resolve()),'Missing or escaping input: '+relative)
    return file

def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON property');result[key]=value
    return result

def parse(raw):
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def validate_context(root,data,binary_sha):
    require(0<len(data)<=MAX_CONTEXT,'Context byte bound')
    x=parse(data)
    require(x.get('schema')=='van.character.context/1' and x.get('asset_sha256')==binary_sha,'Wrong contextual binary binding')
    native=file_at(root,'android/app/src/main/java/com/dial/van/visual/VanContextGesture.kt').read_text()
    fallback={'ACK_NOD':2,'POINT_TARGET':7,'SHRUG':11,'CAUTION':9,'CLOSE_PANEL':14,'PRESENT_CARD':12,'CONFIRM':10}
    expected={int(code):(name,int(duration.replace('_','')),fallback[action]) for name,code,duration,action in re.findall(r'^    (\w+)\((\d+), ([\d_]+), VanFiniteAction\.(\w+)',native,re.M)}
    require(set(expected)==set(range(15,27)),'Incomplete actual native extension catalogue')
    rows=x.get('gestures');require(isinstance(rows,list) and len(rows)==12,'Incomplete context metadata')
    seen=set()
    for row in rows:
        require(isinstance(row,dict),'Invalid gesture row')
        require(all(type(row.get(k)) is int for k in ['code','duration_ms','legacy_action']),'Noninteger context field')
        code=row['code'];require(code not in seen and expected.get(code)==(row.get('name'),row['duration_ms'],row['legacy_action']),'Changed contextual gesture');seen.add(code)

def inputs(root):
    root=root.resolve();request_file=file_at(root,REQUEST);request=parse(request_file.read_bytes())
    require(request.get('schema')=='van.character-review.request/1','Unknown review request')
    require(request.get('review_only') is True and request.get('production_accepted') is False and request.get('physical_accepted') is False,'Review cannot grant acceptance')
    require(request.get('application_id')==APP and request.get('build_type')==VARIANT and request.get('asset_names')==NAMES,'Wrong variant or output names')
    approval=file_at(root,request['owner_instruction_path']);require(sha(approval)==request['owner_instruction_sha256'],'Owner instruction changed')
    a=parse(approval.read_bytes());require(a.get('id')==request['id'] and a.get('owner_response')=='Proceed' and a.get('production_accepted') is False and a.get('physical_testing')=='DEFERRED_FINAL_STAGE','Owner scope mismatch')
    require(a.get('cryptographic_owner_signature_claimed') is False,'Do not manufacture a signed owner gate')
    scoped=a.get('exact_candidate_scope') or {}
    require(all(scoped.get(k)==request.get(k) for k in ['rive_sha256','context_sha256','source_packet_sha256','application_id','build_type']) and scoped.get('runtime')==request['rive_runtime'],'Payload exceeds the exact approved candidate scope')
    require(a.get('question')=='Do you approve that candidate-only sequencing change, so I can put the refined character into the software-review build without declaring it production-approved?','Different approval scope')
    archive=file_at(root,request['source_packet_path']);require(sha(archive)==request['source_packet_sha256'],'Review source archive changed')
    evidence=file_at(root,request['native_software_receipt']);require(sha(evidence)==request['native_software_receipt_sha256'],'Native software evidence changed')
    e=parse(evidence.read_bytes());require(e['candidate_binary_sha256']==request['rive_sha256'] and e['native_behavior_tests']==e['native_behavior_passed']==122 and e['character_promoted'] is False,'Candidate/evidence mismatch')
    gradle=file_at(root,'android/app/build.gradle.kts').read_text();require(re.findall(r'app\.rive:rive-android:([^"\)]+)',gradle)==[request['rive_runtime']],'Runtime changed since compatibility proof')
    require(request['rive_runtime']=='9.13.10' and request['native_core']=='ff495d263f5ec29d8986dc16d49f5ed8ea22ca33','Unreviewed runtime')
    inventory=parse(file_at(root,'docs/rebuild/rev118/character-review/SOURCE_INVENTORY.json').read_bytes())
    require(inventory.get('request_sha256')==sha(request_file) and inventory.get('source_packet_sha256')==request['source_packet_sha256'],'Source inventory is for a different review request')
    require(inventory.get('source_owner_accepted_complete') is False and inventory.get('independent_visual_accepted') is False and inventory.get('production_accepted') is False,'Inventory cannot issue an acceptance')
    master=inventory['adopted_master'];require(master['sha256']=='cf7f51793692bfe8ea2e5f58f1a12e64d3a76468a85cb19d76d0db64ccef374c' and sha(file_at(root,master['path']))==master['sha256'],'Adopted Candidate B identity differs')
    with zipfile.ZipFile(archive) as z:
        allnames=z.namelist();require(len(allnames)==len(set(allnames)),'Duplicate archive members')
        manifest=parse(z.read('REVIEW_MANIFEST.json'));records={row['path']:row for row in manifest['files']}
        originals=inventory['original_identity_images']
        require(len(originals)==38,'Original identity source set incomplete')
        for relative,expected in originals.items():
            name=PREFIX+relative;require(sha_bytes(z.read(name))==expected==records[name]['sha256'],'Original identity pixels changed')
        for row in inventory['rig_source_files']:
            require(sha_bytes(z.read(row['path']))==row['sha256'],'Reviewed source file changed')
        data={}
        for key,relative,limit in [('rive','build/van_raster_full_r5_unadmitted.riv',MAX_RIVE),('context','van.context.json',MAX_CONTEXT),('rml','scene.rml',8*1024*1024)]:
            name=PREFIX+relative;info=z.getinfo(name);require(0<info.file_size<=limit,'Archive member byte bound')
            require((info.external_attr>>16)&0o170000!=0o120000,'Symlinked archive member')
            raw=z.read(name);require(sha_bytes(raw)==request[key+'_sha256']==records[name]['sha256'],'Archive source digest mismatch: '+key);data[key]=raw
    validate_context(root,data['context'],request['rive_sha256'])
    return request,sha(request_file),data

def atomic(path, data):
    fd,name=tempfile.mkstemp(prefix='.review-write-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as target:target.write(data);target.flush();os.fsync(target.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)

def prepare(root,output,provenance):
    root=root.resolve();require(output.resolve()==root/OUTPUT and not output.is_symlink(),'Only the generated review-variant directory may be written')
    request,request_sha,data=inputs(root)
    require(provenance.resolve()==root/'android/app/build/generated/van-build-provenance/van-build-provenance.json','Only the actual generated source provenance is accepted')
    p=parse(provenance.read_bytes());source=p.get('source_sha');require(isinstance(source,str) and re.fullmatch('[0-9a-f]{40}',source) is not None,'Missing current build source SHA')
    marker={'schema':'van.character-review.package/1','approval_id':request['id'],'review_only':True,'production_accepted':False,'physical_accepted':False,'admission_state':'UNACCEPTED_CANDIDATE','application_id':APP,'build_type':VARIANT,'request_sha256':request_sha,'owner_instruction_sha256':request['owner_instruction_sha256'],'source_commit':source,'rive_sha256':request['rive_sha256'],'context_sha256':request['context_sha256'],'rml_sha256':request['rml_sha256'],'rive_runtime':request['rive_runtime'],'label':'CHARACTER REVIEW — NOT PRODUCTION ACCEPTED'}
    output.mkdir(parents=True,exist_ok=True)
    allowed=set(NAMES.values())|{'van-build-provenance.json'}
    require(all(p.is_file() and not p.is_symlink() and p.name in allowed for p in output.iterdir()),'Unexpected review output; preserve and inspect instead of overwriting')
    # Marker installed last. A torn pair cannot pass runtime hashes or package guard.
    (output/NAMES['marker']).unlink(missing_ok=True)
    atomic(output/NAMES['rive'],data['rive']);atomic(output/NAMES['context'],data['context'])
    p.update(application_id=APP,build_type=VARIANT,review_only=True,production_accepted=False,character_rive_sha256=request['rive_sha256'],character_review_request_sha256=request_sha)
    atomic(output/'van-build-provenance.json',(json.dumps(p,sort_keys=True)+'\n').encode())
    atomic(output/NAMES['marker'],(json.dumps(marker,sort_keys=True)+'\n').encode())
    return guard(root,VARIANT,output)

def guard(root,variant,assets):
    request,request_sha,_=inputs(root)
    require(assets.is_dir() and not assets.is_symlink(),'Actual merged asset directory missing')
    files=[p for p in assets.rglob('*') if p.is_file()]
    require(all(not p.is_symlink() and p.resolve().is_relative_to(assets.resolve()) for p in files),'Asset symlink escape')
    hits=[p for p in files if p.name in NAMES.values() or p.suffix=='.riv' and sha(p)==request['rive_sha256']]
    if variant!=VARIANT:
        require(not hits,'REVIEW_ASSET_IN_NONREVIEW_VARIANT')
        return {'status':'NO_REVIEW_ASSETS','variant':variant,'review_only':False}
    require(set(p.name for p in hits)==set(NAMES.values()) and len(hits)==3,'Incomplete/renamed review payload')
    require(sha(assets/NAMES['rive'])==request['rive_sha256'] and sha(assets/NAMES['context'])==request['context_sha256'],'Review payload changed after preparation')
    marker=parse((assets/NAMES['marker']).read_bytes());provenance=parse((assets/'van-build-provenance.json').read_bytes())
    require(marker.get('schema')=='van.character-review.package/1' and marker.get('request_sha256')==request_sha and marker.get('approval_id')==request['id'],'Wrong review package marker')
    require(marker.get('review_only') is True and marker.get('production_accepted') is False and marker.get('physical_accepted') is False and marker.get('admission_state')=='UNACCEPTED_CANDIDATE','Package cannot self-accept')
    require(marker.get('application_id')==provenance.get('application_id')==APP and marker.get('build_type')==VARIANT,'Review identity mismatch')
    require(marker.get('rive_sha256')==request['rive_sha256'] and marker.get('context_sha256')==request['context_sha256'],'Marker payload identity mismatch')
    require(marker.get('source_commit')==provenance.get('source_sha') and provenance.get('review_only') is True and provenance.get('production_accepted') is False,'Review build provenance mismatch')
    require(not (assets/'van.riv').exists() and not (assets/'van.context.json').exists(),'Production and unaccepted character must not be mixed')
    return {'status':'UNACCEPTED_CHARACTER_REVIEW_PACKAGE_VERIFIED','variant':variant,'application_id':APP,'source_commit':marker['source_commit'],'rive_sha256':request['rive_sha256'],'context_sha256':request['context_sha256'],'request_sha256':request_sha,'production_accepted':False,'physical_accepted':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare');q.add_argument('--output',type=Path,required=True);q.add_argument('--provenance',type=Path,required=True)
    q=sub.add_parser('guard');q.add_argument('--variant',required=True);q.add_argument('--assets',type=Path,required=True)
    args=p.parse_args()
    try:
        value=prepare(ROOT,args.output,args.provenance) if args.command=='prepare' else guard(ROOT,args.variant,args.assets)
        print(json.dumps(value,sort_keys=True))
    except (ValueError,KeyError,OSError,zipfile.BadZipFile,json.JSONDecodeError) as exc:
        raise SystemExit('CHARACTER_REVIEW_REFUSED: '+str(exc))
if __name__=='__main__':main()
