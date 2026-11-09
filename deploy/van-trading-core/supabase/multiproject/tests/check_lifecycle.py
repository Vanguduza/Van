#!/usr/bin/env python3
"""Native systemd-parser and SHA-256 guards for canonical one-stack lifecycle.

No service manager actions, container daemon, production file read or writes.
The candidate references deployment paths but is only generated/parsed privately.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import tempfile
from test_compose_lifecycle import fixture_spec
import compose_lifecycle as life
BASE=pathlib.Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=pathlib.Path,required=True)
    parser.add_argument('--donor-ref',required=True)
    parser.add_argument('--report',type=pathlib.Path,required=True)
    a=parser.parse_args()
    if not life.re.fullmatch('[a-f0-9]{40}',a.donor_ref) or not a.report.is_absolute() or a.report.exists():raise ValueError('IMMUTABLE_SOURCE_AND_NEW_REPORT_REQUIRED')
    original=subprocess.check_output(['git','-C',str(a.repo),'show',a.donor_ref+':deploy/van-trading-core/systemd/vati-supabase.service'],text=True,timeout=10)
    spec=fixture_spec(original);spec['source_sha']=a.donor_ref
    artifact=life.compile_bundle(spec,original);receipt=json.loads(artifact['lifecycle-candidate.json'])
    checks={};diagnostics={}
    with tempfile.TemporaryDirectory(prefix='dial-lifecycle-check-') as td:
        root=pathlib.Path(td)
        for label,content in [('original',original),('complete',original+'\n'+artifact['90-dial-multiproject.conf'])]:
            path=root/label;path.mkdir();unit=path/life.UNIT;unit.write_text(content)
            result=subprocess.run(['/usr/bin/systemd-analyze','verify','--man=no',str(unit)],capture_output=True,text=True,timeout=15)
            checks[label+'_native_systemd_verification']=result.returncode==0
            diagnostics[label]={'exit_code':result.returncode,'stderr':result.stderr[:4000]}
        # The same native sha256sum binary configured in the unit is exercised
        # on private material only, not actual production secrets/configuration.
        items=[]
        for i,value in enumerate(receipt['file_bindings']):
            path=root/('pinned-'+str(i));payload=('fixture-private-input-'+str(i)).encode()
            path.write_bytes(payload);path.chmod(0o600)
            items.append((path,payload,hashlib.sha256(payload).hexdigest()))
        guard=root/'inputs.sha256';guard.write_text(''.join(digest+'  '+str(path)+'\n' for path,payload,digest in items))
        cmd=['/usr/bin/sha256sum','--check','--strict','--status',str(guard)]
        checks['all_expected_private_fixture_files_verified']=subprocess.run(cmd,capture_output=True,timeout=10).returncode==0
        for i,(path,payload,digest) in enumerate(items):
            path.write_bytes(payload+b'corruption')
            checks['tamper_refused_'+str(i)]=subprocess.run(cmd,capture_output=True,timeout=10).returncode!=0
            path.write_bytes(payload)
        chosen,payload,_=items[-1];chosen.unlink()
        checks['missing_input_refused']=subprocess.run(cmd,capture_output=True,timeout=10).returncode!=0
        chosen.write_bytes(payload)
        checks['original_fixture_inputs_reverified_after_test']=subprocess.run(cmd,capture_output=True,timeout=10).returncode==0
        lines=artifact['90-dial-multiproject.conf'].splitlines()
        starts=[shlex.split(x[len('ExecStart='):]) for x in lines if x.startswith('ExecStart=') and x!='ExecStart=']
        stops=[shlex.split(x[len('ExecStop='):]) for x in lines if x.startswith('ExecStop=') and x!='ExecStop=']
        checks['one_canonical_start_command']=starts==[receipt['start_argv']]
        checks['same_full_model_used_by_stop']=stops[-1]==receipt['stop_argv'] and starts[0][:-3]==stops[-1][:-1]
        checks['stop_also_checks_pinned_inputs']=stops[0][:4]==['/usr/bin/sha256sum','--check','--strict','--status']
        checks['all_eight_compose_inputs_in_both_actions']=starts[0].count('-f')==8 and stops[-1].count('-f')==8
        checks['all_five_env_inputs_in_both_actions']=starts[0].count('--env-file')==5 and stops[-1].count('--env-file')==5
        checks['explicit_original_project_and_local_daemon']=starts[0][1:4]==['--host','unix:///var/run/docker.sock','compose'] and starts[0][starts[0].index('--project-name')+1]==spec['observed_project_name']
        checks['no_deployment_or_authority_claim']=receipt['production_deployed'] is False and receipt['authorizes_execution'] is False
        result={'state':'PASS' if all(checks.values()) else 'FAIL','check_count':len(checks),'checks':checks,
            'donor_ref':a.donor_ref,'original_unit_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'source_sha256':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'tools/compose_lifecycle.py',BASE/'tests/test_compose_lifecycle.py',pathlib.Path(__file__))},
            'native_systemd':subprocess.check_output(['/usr/bin/systemd-analyze','--version'],text=True,timeout=5).splitlines()[0],
            'native_parser_diagnostics':diagnostics,'service_manager_reloaded':False,'container_daemon_used':False,
            'production_unit_changed':False,'actual_host_observation':False,'synthetic_file_content':True}
        fd=os.open(a.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
        print('CANONICAL_LIFECYCLE_'+result['state']+' '+str(len(checks)))
        if not all(checks.values()):print('FAILED_CHECKS '+','.join(k for k,v in checks.items() if not v))
        return 0 if all(checks.values()) else 1

if __name__=='__main__':raise SystemExit(main())
