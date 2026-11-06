#!/usr/bin/env python3
"""Reproduce exact-version native-core software checks without staging Android assets.

Inputs are explicit, upstream files remain immutable and the output directory is
create-only. This is not a Forge milestone or permission to promote an asset.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
from verify_result import verify


def sha(path: Path) -> str:
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def require(ok: bool, reason: str) -> None:
    if not ok:raise ValueError(reason)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def source_path(root: Path, relative: str) -> Path:
    parts=PurePosixPath(relative)
    require(not parts.is_absolute() and '..' not in parts.parts and bool(parts.parts),'Unsafe upstream path')
    item=root.joinpath(*parts.parts)
    require(item.is_file() and not item.is_symlink(),'Missing/symlink upstream source: '+relative)
    require(item.resolve().is_relative_to(root.resolve()),'Upstream path escaped source root')
    return item


def locked_json(path: Path, digest: str) -> dict[str,Any]:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=8*1024*1024,'Unbounded/missing source tree response')
    require(sha(path)==digest,'Official source tree response differs from reviewed lock')
    value=json.loads(path.read_text())
    require(isinstance(value,dict) and value.get('truncated') is False,'Incomplete upstream source tree')
    return value


def verify_inputs(source: Path, core_tree: Path, android_tree: Path, gradle: Path,
                  lock: dict[str,Any]) -> dict[str,Any]:
    require(source.is_dir() and not source.is_symlink(),'Explicit original source directory required')
    android=locked_json(android_tree,lock['android_tree_response_sha256'])
    core=locked_json(core_tree,lock['core_tree_response_sha256'])
    require(android['sha']==lock['android_commit'],'Wrong Android source tag')
    submodules=[x for x in android['tree'] if x['path']=='submodules/rive-runtime']
    require(len(submodules)==1 and submodules[0]['type']=='commit' and submodules[0]['sha']==lock['core_commit'],'Android tag does not bind the chosen core')
    require(core['sha']==lock['core_commit'],'Wrong native core source tree')
    declarations=re.findall(r'app\.rive:rive-android:([^"\)]+)',gradle.read_text())
    require(declarations==[lock['android_version']],'Application runtime pin differs; update evidence, not the application pin')
    wanted={x['path']:x['sha'] for x in core['tree'] if x['type']=='blob' and Path(x['path']).suffix in {'.cpp','.hpp','.h','.lua'}}
    actual={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and p.suffix in {'.cpp','.hpp','.h','.lua'}}
    require(actual==set(wanted),'Native source/header/build-rule set differs from official tree')
    records={}
    for relative,expected in sorted(wanted.items()):
        item=source_path(source,relative);raw=item.read_bytes()
        require(git_blob(raw)==expected,'Native source modified: '+relative)
        records[relative]=hashlib.sha256(raw).hexdigest()
    cpp=[p for p in records if p.startswith('src/') and p.endswith('.cpp')]
    require(len(cpp)==lock['cpp_sources'],'Incomplete native C++ implementation set')
    return {'android_version':lock['android_version'],'android_commit':lock['android_commit'],
        'core_commit':lock['core_commit'],'source_files':len(records),'cpp_sources':len(cpp),
        'source_sha256':records,'gradle_sha256':sha(gradle),'lock_sha256':sha(HERE/'SOURCE_LOCK.json')}


def new_output(path: Path) -> Path:
    # Restrict creation to the selected repository's existing evidence/work area.
    candidate=path.absolute()
    require(not candidate.exists() and not candidate.is_symlink(),'Output already exists; preserve prior results')
    require(candidate.parent.exists(),'Create the intended working parent explicitly first')
    parent=candidate.parent.resolve();relative=parent.relative_to(ROOT.resolve())
    require(relative.parts and relative.parts[0] in {'.git','evidence'},'Output must stay in this repository .git/ or evidence/ working area')
    require(candidate.name not in {'','.', '..'},'Invalid output name')
    candidate.mkdir()
    return candidate


def execute(command: list[str], output: Path, timeout: int) -> dict[str,Any]:
    start=time.monotonic();stdout=output.with_suffix('.stdout');stderr=output.with_suffix('.stderr')
    try:
        with stdout.open('x') as out,stderr.open('x') as err:
            code=subprocess.run(command,stdout=out,stderr=err,timeout=timeout,check=False).returncode
    except subprocess.TimeoutExpired:code=124
    return {'argv':command,'exit_code':code,'seconds':round(time.monotonic()-start,3),
        'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr)}


def cpp_driver(path: Path) -> Path:
    # clang++ may be a symlink to clang; resolving the leaf changes argv[0]
    # and silently selects C-driver linking without the C++ runtime/libm.
    result=path.absolute().parent.resolve()/path.name
    require(result.is_file() and '++' in result.name,'An explicit C++ compiler driver is required')
    return result


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','core-tree','android-tree','candidate','control','compiler','cairo-include','cairo-library','output']:
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args();lock=json.loads((HERE/'SOURCE_LOCK.json').read_text())
    for name in ['source','core_tree','android_tree','candidate','control','cairo_include','cairo_library']:
        setattr(args,name,getattr(args,name).resolve())
    args.compiler=cpp_driver(args.compiler)
    require(platform.system()=='Linux','This diagnostic implementation supports Linux only')
    require(args.candidate.is_file() and 4<=args.candidate.stat().st_size<=8*1024*1024,'Candidate byte bounds')
    require(sha(args.control)==lock['positive_control_sha256'],'Wrong positive control')
    require(args.compiler.is_file() and (args.cairo_include/'cairo.h').is_file() and args.cairo_library.is_file(),'Missing actual compiler/Cairo dependency')
    binding=verify_inputs(args.source,args.core_tree,args.android_tree,ROOT/'android/app/build.gradle.kts',lock)
    output=new_output(args.output);stages=[]
    identity={'scope':lock['renderer_scope'],'physical_tested':False,'android_jni_qualified':False,'owner_accepted':False,
        'source_binding':binding,'candidate_sha256':sha(args.candidate),'positive_control_sha256':sha(args.control),
        'tool_source_sha256':{f.name:sha(f) for f in HERE.iterdir() if f.is_file()},
        'compiler_sha256':sha(args.compiler),'cairo_library_sha256':sha(args.cairo_library),'cairo_header_sha256':sha(args.cairo_include/'cairo.h'),
        'host_architecture':platform.machine(),'stages':stages,'status':'NOT_PASSED'}
    try:
        for label,command,limit in [
            ('configure',['cmake','-S',str(HERE),'-B',str(output/'build'),'-G','Ninja',
                '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_COMPILER='+str(args.compiler),
                '-DRIVE_SOURCE='+str(args.source),'-DCAIRO_INCLUDE_DIR='+str(args.cairo_include),'-DCAIRO_LIBRARY='+str(args.cairo_library)],90),
            ('compile',['cmake','--build',str(output/'build'),'--parallel','1'],900),
        ]:
            stage=execute(command,output/label,limit);stages.append({'stage':label,**stage})
            require(stage['exit_code']==0,label+' failed; no compatibility pass')
        binary=output/'build/native_probe';identity['native_probe_sha256']=sha(binary)
        for label,asset,extra in [('positive-control',args.control,['control']),('candidate',args.candidate,[])]:
            folder=output/label;folder.mkdir()
            stage=execute([str(binary),str(asset),str(folder),*extra],folder/'runtime',120)
            (folder/'runtime.stdout').rename(folder/'runtime.jsonl')
            receipt={'scope':lock['renderer_scope'],'case':label,'candidate_sha256':sha(asset),
                'native_core_commit':lock['core_commit'],'probe_sha256':sha(binary),'physical':False,**stage}
            (folder/'EXECUTION_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
            stages.append({'stage':label,**stage});require(stage['exit_code']==0,label+' actual runtime failed')
        require(sha(args.candidate)==identity['candidate_sha256'],'Candidate changed during native run')
        require(sha(ROOT/'android/app/build.gradle.kts')==binding['gradle_sha256'],'Application runtime declaration changed during run')
        require(sha(args.compiler)==identity['compiler_sha256'] and sha(args.cairo_library)==identity['cairo_library_sha256'],'Native tool dependency changed during run')
        require(all(sha(args.source/f)==h for f,h in binding['source_sha256'].items()),'Upstream source changed during compilation')
        require(all(sha(HERE/f)==h for f,h in identity['tool_source_sha256'].items()),'Diagnostic code changed during run')
        result=verify(output/'candidate',output/'positive-control',args.candidate)
        (output/'COMPATIBILITY.json').write_text(json.dumps(result,indent=2)+'\n')
        identity['compatibility_tests']=result['tests'];identity['compatibility_passed']=result['passed']
        require(result['status']=='PINNED_NATIVE_CORE_COMPATIBILITY_PASSED','Actual native behavior check failed')
        identity['status']='PINNED_NATIVE_CORE_SOFTWARE_VERIFIED'
    except (ValueError,AssertionError,OSError) as exc:
        identity['failure']=str(exc)
        raise
    finally:
        (output/'RUN_RECEIPT.json').write_text(json.dumps(identity,indent=2)+'\n')
        print(json.dumps({k:identity.get(k) for k in ['status','candidate_sha256','compatibility_tests','compatibility_passed','failure']}),flush=True)
if __name__=='__main__':main()
