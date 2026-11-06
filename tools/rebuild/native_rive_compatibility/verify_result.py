#!/usr/bin/env python3
"""Read actual pinned-native trace/PNGs. No renderer mocks, gate or asset mutation.

This verifies native-core behavior using the original compiled .riv file. Cairo
is a diagnostic transport, not the Android/JNI/Skia or PLS rendering backend.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

EXPECTED_CORE = 'ff495d263f5ec29d8986dc16d49f5ed8ea22ca33'
EXPECTED_ANDROID = '9.13.10'
CONTRACT_INPUTS = ['state','speaking','listening','attention_x','attention_y','mouth_open','urgency','viseme','action_code','point','ack','celebrate','warning','wave','shrug','present','panel']
STATES = ['OFFLINE','CONNECTING','IDLE','ATTENTIVE','LISTENING','THINKING','SEARCHING','WORKING','DELEGATING','SPEAKING','WAITING','WAITING_FOR_OWNER','DEGRADED','WARNING','ERROR','SUCCESS','URGENT','SLEEPING']
ACTIONS = ['HELLO_WAVE','ACK_NOD','POINT_LEFT','POINT_RIGHT','POINT_UP','POINT_DOWN','POINT_TARGET','CELEBRATE','CAUTION','CONFIRM','SHRUG','PRESENT_CARD','OPEN_PANEL','CLOSE_PANEL','EXPLAIN_OPEN_PALMS','COMPARE_OPTIONS','THINK_CHIN','INSPECT_TARGET','LISTEN_EMPHASIS','POLITE_REFUSAL','ACKNOWLEDGE_ERROR','YIELD_TO_INTERRUPTION','REQUEST_CLARIFICATION','HANDOFF_RESULT','RECOVERY_READY','GUIDE_NEXT_STEP']
ARMS = ['rig_shoulder_l','rig_elbow_l','rig_wrist_l','rig_shoulder_r','rig_elbow_r','rig_wrist_r','rig_nod']
FINGERS = [f'rig_{part}_{side}' for side in ['l','r'] for part in ['index_prox','index_tip','thumb','middle','ring','little']]

def sha(path: Path) -> str:
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()

def require(condition: bool, reason: str) -> None:
    if not condition:raise AssertionError(reason)

def load_trace(folder: Path) -> tuple[list[dict[str,Any]],dict]:
    receipt=json.loads((folder/'EXECUTION_RECEIPT.json').read_text())
    require(receipt['exit_code']==0,'Native process did not succeed')
    require(receipt['native_core_commit']==EXPECTED_CORE,'Wrong native core revision')
    require(sha(folder/'runtime.jsonl')==receipt['stdout_sha256'],'Native trace changed')
    require(sha(folder/'runtime.stderr')==receipt['stderr_sha256'],'Native stderr changed')
    require((folder/'runtime.stderr').stat().st_size==0,'Unexpected native warning/error requires review')
    return [json.loads(line) for line in (folder/'runtime.jsonl').read_text().splitlines()],receipt

def verify(candidate: Path, control: Path, binary: Path) -> dict[str,Any]:
    from PIL import Image
    rows,receipt=load_trace(candidate);controls,control_receipt=load_trace(control)
    require(receipt['candidate_sha256']==sha(binary),'Trace belongs to a different binary')
    require(control_receipt['probe_sha256']==receipt['probe_sha256'],'Positive control used different probe')
    cases=[];samples={row['label']:row for row in rows if row['kind']=='sample'}
    def test(name,action):
        try:action();cases.append({'name':name,'passed':True})
        except (AssertionError,KeyError,ValueError,TypeError) as exc:cases.append({'name':name,'passed':False,'reason':str(exc)})
    def node(label,name):return samples[label]['nodes'][name]
    def quiet(label):
        for name in ARMS+FINGERS:
            require(abs(node(label,name)['rotation'])<.05,f'{label}: {name} did not return to rest')
    imports=[r for r in rows if r['kind']=='import'];surface=[r for r in rows if r['kind']=='surface']
    test('Original native runtime imports one Van artboard and decodes all52 PNG images',lambda:require(len(imports)==1 and imports[0]['artboards']==1 and imports[0]['decoded_pngs']==52 and imports[0]['decoded_pixels']==339750,'Incomplete native asset import'))
    test('Original nine inputs/eight triggers survive exact native import',lambda:require(len(surface)==1 and surface[0]['inputs']==CONTRACT_INPUTS,'Input contract differs'))
    test('Official unrelated positive control visibly renders first',lambda:require(any(r.get('kind')=='control' and r.get('visible_pixels',0)>1000 for r in controls),'Empty/absent positive control'))
    test('Every reported native transform remains finite',lambda:require(all(math.isfinite(v) for r in samples.values() for n in r['nodes'].values() for v in n.values()),'Nonfinite native transform'))
    for code,name in enumerate(STATES):
        def state_test(code=code,name=name):
            row=samples[f'state-{code}'];require('r5_expression_'+name.lower() in row['events'],'Wrong state selected');require(row['visible_pixels']>60_000,'Empty/truncated native character')
        test('Actual native durable state '+name,state_test)
    for code,name in enumerate(ACTIONS,1):
        def action_test(code=code,name=name):
            row=samples[f'action-{code}'];event=('action_r5_' if code<=14 else 'context_')+name.lower()
            require(event in row['events'],'Wrong finite/context clip selected');require(row['visible_pixels']>60_000,'Blank gesture capture')
        test('Actual native gesture '+name,action_test)
        test('Six-frame native cancellation resets arms and allfinger controls '+name,lambda code=code:quiet(f'clear-{code}'))
    for finger in FINGERS:
        test('Independent native finger articulation '+finger,lambda finger=finger:require(abs(node('action-4',finger)['rotation'])>.02,'Finger not independently animated'))
    for i in range(16):
        def target_test(i=i):
            row=samples[f'target-{i}']['nodes'];w=row['rig_wrist_r'];t=row['r5_live_point_target'];a=row['rig_shoulder_r'];angle=i*math.tau/16
            require(math.hypot(w['x']-t['x'],w['y']-t['y'])<.05,'Native IK missed its target')
            require(math.hypot(t['x']-a['x']-100*math.cos(angle),t['y']-a['y']-100*math.sin(angle))<.05,'Native attention mapping is nonlinear')
        test('Native continuous IK direction '+str(i),target_test)
    for i in range(3):
        def retarget(i=i):
            row=samples[f'retarget-{i}'];w=row['nodes']['rig_wrist_r'];t=row['nodes']['r5_live_point_target']
            require(math.hypot(w['x']-t['x'],w['y']-t['y'])<.05,'Retarget missed')
            require(row['events'].count('action_r5_point_target')==samples['retarget-initial']['events'].count('action_r5_point_target')==1,'Retarget restarted the clip')
        test('Native in-flight target update '+str(i),retarget)
    test('Critical caution preempts active wave in6 native frames',lambda:require('action_r5_caution' in samples['urgent-preemption']['events'] and 'r5_expression_urgent' in samples['urgent-preemption']['events'],'Critical override not active'))
    for code in [-1,99]:test('Invalid action safely clears '+str(code),lambda code=code:quiet(f'invalid-action-{code}'))
    test('Legacy trigger-only wave remains animated',lambda:require('action_r5_hello_wave' in samples['legacy-wave']['events'] and node('legacy-wave','rig_shoulder_r')['rotation']<-.7,'Trigger-only gesture missing'))
    test('Legacy trigger-only wave ends without action-code input',lambda:quiet('legacy-wave-clear'))
    def orbital():
        start=node('orb-start','rig_orb');other=node('orb-other-side','rig_orb');end=node('orb-return','rig_orb')
        require(other['x']-start['x']>289,'Orb did not travel to opposite side')
        require(abs(other['rotation']-math.pi)<.01 and abs(end['rotation']-math.tau)<.01,'Orb spin missing')
        require(math.hypot(start['x']-end['x'],start['y']-end['y'])<.01,'Orb loop not continuous')
    test('Native orb travels left/right/return with independent rotation',orbital)
    test('State/context changes do not reset native orb clock',lambda:require(node('orbit-control','rig_orb')==node('orbit-context-changed','rig_orb'),'Orb depends on character action'))
    for label in ['sleep-held','sleep-after-blink-cycle']:
        test('Sleep keeps eyelids closed '+label,lambda label=label:require(all(node(label,n)['scaleY']>.99 for n in ['rig_eyelid_l','rig_eyelid_r']),'Sleeping eyes reopened'))
    test('Wake restores ordinary blinking',lambda:require(node('woken','rig_eyelid_l')['scaleY']<.05,'Wake retained closed-eye pose'))
    def blinking():
        peaks=next(r['peaks'] for r in rows if r['kind']=='blink');require(len(peaks)==14,'Native blink count differs')
        require(sum(b-a<30 for a,b in zip(peaks,peaks[1:]))==2,'Native double blinks missing/extra')
    test('Native natural blink programme contains14closures and2double events',blinking)
    for code in range(5):
        test('Native mouth shape '+str(code),lambda code=code:require(f'viseme_{code}' in samples[f'mouth-{code}']['events'] and node(f'mouth-{code}','rig_mouth_open')['scaleY']>.7,'Mouth cue not applied'))
    images=[]
    for filename in sorted(candidate.glob('*.png')):
        with Image.open(filename) as image:
            rgba=image.convert('RGBA');alpha=rgba.getchannel('A');bounds=alpha.getbbox()
            require(image.size==(593,593) and bounds is not None,'Invalid native image evidence')
        images.append({'path':filename.name,'sha256':sha(filename),'alpha_bounds':bounds,'bytes':filename.stat().st_size})
    test('All53 expected native character render captures retained',lambda:require(len(images)==53,'Native capture set incomplete'))
    failed=[c for c in cases if not c['passed']]
    return {'status':'PINNED_NATIVE_CORE_COMPATIBILITY_PASSED' if not failed else 'FAILED','candidate_sha256':sha(binary),'native_core_commit':EXPECTED_CORE,'android_wrapper_version':EXPECTED_ANDROID,'probe_sha256':receipt['probe_sha256'],'tests':len(cases),'passed':len(cases)-len(failed),'checks':cases,'native_captures':images,'scope':'Unmodified core used by Android9.13.10 compiled on Linux with a real diagnostic Cairo PNG/path/mesh transport. No Android/JNI/Skia/PLS or S24 acceptance. Optional text/audio/flex-layout disabled; only default artboard style, not flex-layout behavior, occurs in this candidate.','android_native_render_qualified':False,'physical_tested':False,'owner_accepted':False}

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-output',required=True,type=Path)
    parser.add_argument('--control-output',required=True,type=Path)
    parser.add_argument('--binary',required=True,type=Path)
    parser.add_argument('--receipt',required=True,type=Path)
    args=parser.parse_args()
    if args.receipt.exists():raise SystemExit('Refusing to overwrite a prior receipt')
    result=verify(args.candidate_output,args.control_output,args.binary)
    args.receipt.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','candidate_sha256','tests','passed']}))
    for case in result['checks']:
        if not case['passed']:print('FAILED',case['name'],case['reason'])
    raise SystemExit(0 if result['status']=='PINNED_NATIVE_CORE_COMPATIBILITY_PASSED' else 1)
if __name__=='__main__':main()
