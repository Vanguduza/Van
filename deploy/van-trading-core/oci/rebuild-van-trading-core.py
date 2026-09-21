#!/usr/bin/env python3
# Rebuilds only tagged VAN trading-core instances; control-plane nodes are protected and never selected.
import base64, json, os, pathlib, re, shlex, subprocess, sys, tempfile, textwrap, time, urllib.request

OCI='/home/ubuntu/.local/bin/oci'
TARGET='van-trading-core'; PRIVATE_IP='10.0.1.233'; TRADING_SUBNET='van-trading-subnet'
ADMIN_IP='10.0.0.123'; HERMES_IP='10.0.0.184'; VEKL_IP='10.0.0.51'; SHAPE='VM.Standard.A1.Flex'
VEKL_OCID='ocid1.instance.oc1.af-johannesburg-1.anvg4ljrvbgkoeqcctvikyk5hgz362mirgruwg64fzlhwwox35ozh5bjc2ha'
OCPUS=2.0; MEMORY_GB=12.0; BOOT_GB=50
BRANCH=os.environ.get('VAN_REBUILD_BRANCH','main')
REPO='https://github.com/Vanguduza/Van.git'
ADMIN_KEY=pathlib.Path.home()/'.ssh/node-admin-to-trading'
HERMES_KEY='~/.ssh/node-hermes-to-trading'

def run(cmd, check=True, capture=True, timeout=None):
    p=subprocess.run(cmd, text=True, capture_output=capture, check=False, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f"command failed {p.returncode}: {shlex.join(cmd)}\n{(p.stderr or p.stdout)[-1200:]}")
    return p

def oci(*args, check=True):
    p=run([OCI,*args,'--auth','instance_principal','--output','json'],check=check)
    return json.loads(p.stdout) if p.returncode==0 and p.stdout.strip() else None

def resolve_repository_sha():
    """Resolve the selected branch once so provisioning cannot silently chase a moving ref."""
    p=run(['git','ls-remote',REPO,f'refs/heads/{BRANCH}'])
    parts=p.stdout.strip().split()
    if len(parts) < 2 or not re.fullmatch(r'[0-9a-f]{40}',parts[0]):
        raise RuntimeError(f'cannot resolve exact repository SHA for branch {BRANCH!r}')
    return parts[0]

def imds():
    r=urllib.request.Request('http://169.254.169.254/opc/v2/instance/',headers={'Authorization':'Bearer Oracle'})
    return json.load(urllib.request.urlopen(r,timeout=5))

def ssh(host, command, key=None, check=True, timeout=30):
    cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=accept-new']
    if key: cmd += ['-i',str(key)]
    return run(cmd+[host,command],check=check,timeout=timeout)

def wait_instance(iid, want, timeout=900):
    end=time.time()+timeout
    while time.time()<end:
        st=oci('compute','instance','get','--instance-id',iid)['data']['lifecycle-state']
        if st==want:
            print('INSTANCE_STATE',want,flush=True)
            return
        time.sleep(5)
    raise RuntimeError(f'instance {iid} did not reach {want}')

def ensure_keys():
    ADMIN_KEY.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not ADMIN_KEY.exists():
        run(['ssh-keygen','-q','-t','ed25519','-N','','-C','node-admin-to-trading','-f',str(ADMIN_KEY)],capture=False)
    os.chmod(ADMIN_KEY,0o600)
    apub=run(['ssh-keygen','-y','-f',str(ADMIN_KEY)]).stdout.strip()+' node-admin-to-trading'
    hp=ssh('hermes',f'test -f {HERMES_KEY} || ssh-keygen -q -t ed25519 -N "" -C node-hermes-to-trading -f {HERMES_KEY}; cat {HERMES_KEY}.pub').stdout.strip()
    if not hp.startswith('ssh-ed25519 '): raise RuntimeError('invalid Hermes trading public key')
    return apub,hp

def get_resources(comp):
    inst=oci('compute','instance','list','--compartment-id',comp,'--all')['data']
    active=[x for x in inst if x['lifecycle-state']!='TERMINATED']
    by={x['display-name']:x for x in active}
    for n in ('oracle-admin','dial-hermes-control','vekl-worker'):
        if n not in by: raise RuntimeError(f'protected control node missing: {n}')
    if by['vekl-worker']['id'] != VEKL_OCID: raise RuntimeError('vekl-worker OCID mismatch; refusing destructive action')
    subs=oci('network','subnet','list','--compartment-id',comp,'--all')['data']
    sub=next((s for s in subs if s['display-name']==TRADING_SUBNET),None)
    if not sub or sub['cidr-block']!='10.0.1.0/24': raise RuntimeError('canonical trading subnet missing/mismatched')
    if sub.get('prohibit-public-ip-on-vnic'): raise RuntimeError('trading subnet must permit public edge IP')
    return active,by,sub

def tcp_rule(source,port,desc):
    return {'protocol':'6','source':source,'sourceType':'CIDR_BLOCK','isStateless':False,'description':desc,
            'tcpOptions':{'destinationPortRange':{'min':port,'max':port}}}

def harden_subnet(sub):
    ingress=[
        tcp_rule(f'{ADMIN_IP}/32',22,'SSH from oracle-admin only'),
        tcp_rule(f'{HERMES_IP}/32',22,'SSH from dial-hermes-control only'),
        tcp_rule(f'{ADMIN_IP}/32',9133,'Commander admin from oracle-admin only'),
        tcp_rule(f'{HERMES_IP}/32',9133,'Commander MCP from dial-hermes-control only'),
        tcp_rule('0.0.0.0/0',80,'ACME HTTP challenge / redirect'),
        tcp_rule('0.0.0.0/0',443,'Public Caddy TLS edge'),
        {'protocol':'1','source':'10.0.0.0/16','sourceType':'CIDR_BLOCK','isStateless':False,
         'description':'Private VCN ICMP diagnostics','icmpOptions':{'type':3}},
        {'protocol':'1','source':'0.0.0.0/0','sourceType':'CIDR_BLOCK','isStateless':False,
         'description':'Path MTU discovery','icmpOptions':{'type':3,'code':4}},
    ]
    egress=[{'protocol':'all','destination':'0.0.0.0/0','destinationType':'CIDR_BLOCK','isStateless':False,
             'description':'Outbound package, market-data, broker and ACME traffic'}]
    for sl in sub.get('security-list-ids') or []:
        with tempfile.TemporaryDirectory() as td:
            ip=pathlib.Path(td)/'ingress.json'; ep=pathlib.Path(td)/'egress.json'
            ip.write_text(json.dumps(ingress)); ep.write_text(json.dumps(egress))
            oci('network','security-list','update','--security-list-id',sl,'--ingress-security-rules',f'file://{ip}',
                '--egress-security-rules',f'file://{ep}','--force')
    print('SUBNET_POLICY_HARDENED',flush=True)

def ensure_reserved_ip(comp):
    data=oci('network','public-ip','list','--scope','REGION','--compartment-id',comp)['data']
    matches=[p for p in data if p.get('display-name')=='van-trading-core-reserved-ip' and p['lifecycle-state']!='TERMINATED']
    if len(matches)>1: raise RuntimeError('multiple reserved trading public IPs exist')
    if matches:
        p=matches[0]
        if p.get('lifetime')!='RESERVED': raise RuntimeError('named trading public IP is not RESERVED')
    else:
        p=oci('network','public-ip','create','--compartment-id',comp,'--lifetime','RESERVED',
              '--display-name','van-trading-core-reserved-ip','--freeform-tags',json.dumps({'project':'VAN','role':'TRADING_EDGE'}))['data']
    addr=p['ip-address']; host=addr.replace('.','-')+'.sslip.io'
    print('RESERVED_PUBLIC_IP',addr,'PUBLIC_HOST',host,flush=True)
    return p['id'],addr,host

def terminate_trading(active):
    doomed=[]
    for x in active:
        tags=x.get('freeform-tags') or {}
        if x['display-name'].startswith('van-trading-core') and tags.get('project')=='VAN' and tags.get('role')=='TRADING_CORE':
            doomed.append(x)
    for x in doomed:
        print('TERMINATING',x['display-name'],x['id'],flush=True)
        oci('compute','instance','terminate','--instance-id',x['id'],'--preserve-boot-volume','false','--force')
    for x in doomed: wait_instance(x['id'],'TERMINATED',1200)
    return doomed

def firstboot(public_host, expected_sha):
    return textwrap.dedent(f'''\
    #!/bin/bash
    set -Eeuo pipefail
    exec > >(tee -a /var/log/van-trading-firstboot.log | logger -t van-firstboot -s 2>/dev/console) 2>&1
    trap 'echo FIRSTBOOT_FAILED line=$LINENO rc=$?; touch /var/lib/van-trading-firstboot.failed' ERR
    export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
    export VAN_BRANCH={shlex.quote(BRANCH)} VAN_CORE_IP={PRIVATE_IP} VAN_VEKL_WORKER_HOST={VEKL_IP}
    export VAN_ADMIN_CIDRS={ADMIN_IP}/32,{HERMES_IP}/32
    for n in $(seq 1 30); do apt-get -o Acquire::Retries=3 update -qq && apt-get install -y -qq --no-install-recommends git ca-certificates curl jq >/dev/null && break; sleep 5; done
    command -v git >/dev/null || exit 41
    rm -rf /opt/van-bootstrap-source
    git clone --depth 1 --branch {shlex.quote(BRANCH)} {shlex.quote(REPO)} /opt/van-bootstrap-source
    cd /opt/van-bootstrap-source
    bash deploy/van-trading-core/bootstrap.sh --branch={shlex.quote(BRANCH)} --public-host={shlex.quote(public_host)} --with-nautilus
    VAN_EXPECTED_REPOSITORY_SHA={shlex.quote(expected_sha)} bash deploy/van-trading-core/qualify.sh | tee /var/lib/van-trading/qualification-latest.json
    jq -e '.status=="GREEN" and .required_failures==0 and .repository_sha==.expected_repository_sha' /var/lib/van-trading/qualification-latest.json >/dev/null
    install -m 0600 /dev/null /var/lib/van-trading/firstboot-complete
    date -u +%Y-%m-%dT%H:%M:%SZ > /var/lib/van-trading/firstboot-complete
    echo FIRSTBOOT_GREEN
    ''')

def launch_instance(comp,ad,sub,image,keys_file,user_data):
    tags={'project':'VAN','role':'TRADING_CORE','environment':'production','managed-by':'oracle-admin','bootstrap':'one-pass-v1'}
    sc={'ocpus':OCPUS,'memoryInGBs':MEMORY_GB}
    args=['compute','instance','launch','--availability-domain',ad,'--compartment-id',comp,'--display-name',TARGET,
          '--hostname-label','van-trading-core','--image-id',image,'--shape',SHAPE,'--shape-config',json.dumps(sc),
          '--subnet-id',sub['id'],'--private-ip',PRIVATE_IP,'--assign-public-ip','false','--boot-volume-size-in-gbs',str(BOOT_GB),
          '--ssh-authorized-keys-file',str(keys_file),'--user-data-file',str(user_data),'--freeform-tags',json.dumps(tags)]
    last=''
    for attempt in range(1,9):
        r=run([OCI,*args,'--auth','instance_principal','--output','json'],check=False,timeout=180)
        if r.returncode==0:
            d=json.loads(r.stdout)['data']; print('LAUNCHED',d['id'],flush=True)
            wait_instance(d['id'],'RUNNING',900); return d['id']
        last=(r.stderr or r.stdout)[-1600:]
        transient=any(x in last for x in ('TooManyRequests','"status": 429','Conflict','"status": 409','InternalServerError','ServiceUnavailable','"status": 500','"status": 503'))
        if not transient: raise RuntimeError(f'instance launch failed permanently on attempt {attempt}: {last}')
        delay=min(120,10*(2**(attempt-1)))
        print(f'LAUNCH_RETRY attempt={attempt}/8 delay={delay}s reason=OCI_TRANSIENT',flush=True); time.sleep(delay)
    raise RuntimeError('instance launch exhausted bounded retries: '+last)

def bind_reserved_ip(comp,iid,reserved_id):
    va=oci('compute','vnic-attachment','list','--compartment-id',comp,'--instance-id',iid)['data']
    primary=next(a for a in va if a['lifecycle-state']=='ATTACHED')
    v=oci('network','vnic','get','--vnic-id',primary['vnic-id'])['data']
    if v['private-ip']!=PRIVATE_IP: raise RuntimeError(f'unexpected private IP {v["private-ip"]}')
    pis=oci('network','private-ip','list','--vnic-id',v['id'])['data']
    pi=next(p for p in pis if p['ip-address']==PRIVATE_IP)
    current=oci('network','public-ip','get','--private-ip-id',pi['id'],check=False)
    if current and current.get('data'):
        cp=current['data']
        if cp['id']!=reserved_id:
            if cp.get('lifetime')!='EPHEMERAL': raise RuntimeError('unexpected non-ephemeral public IP already attached')
            oci('network','public-ip','delete','--public-ip-id',cp['id'],'--force')
            time.sleep(3)
    oci('network','public-ip','update','--public-ip-id',reserved_id,'--private-ip-id',pi['id'],'--force')
    bound=oci('network','public-ip','get','--public-ip-id',reserved_id)['data']
    if bound.get('private-ip-id')!=pi['id']: raise RuntimeError('reserved public IP binding failed')
    print('RESERVED_IP_BOUND',bound['ip-address'],flush=True)
    return v['id']

def wait_ssh(ip,key,via_hermes=False,timeout=900):
    end=time.time()+timeout; last=''
    while time.time()<end:
        if via_hermes:
            p=ssh('hermes',f"ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -i {HERMES_KEY} ubuntu@{ip} 'sudo -n true && echo SSH_ADMIN_OK'",check=False,timeout=15)
        else:
            p=ssh(f'ubuntu@{ip}','sudo -n true && echo SSH_ADMIN_OK',key=key,check=False,timeout=15)
        if p.returncode==0 and 'SSH_ADMIN_OK' in p.stdout: return
        last=(p.stderr or p.stdout)[-300:]; time.sleep(8)
    raise RuntimeError(f'SSH admin path did not become ready: {last}')

def remote_write(host, path, content, mode='0600'):
    payload=base64.b64encode(content.encode()).decode()
    py=("import base64,os,pathlib; p=pathlib.Path("+repr(path)+"); "
        "p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(base64.b64decode("+repr(payload)+")); os.chmod(p,"+oct(int(mode,8))+")")
    ssh(host, 'python3 -c '+shlex.quote(py))

def install_ssh_aliases():
    admin_cfg=pathlib.Path.home()/'.ssh/config'
    block=f'''\nHost van-trading-core\n    HostName {PRIVATE_IP}\n    User ubuntu\n    IdentityFile {ADMIN_KEY}\n    IdentitiesOnly yes\n    ServerAliveInterval 30\n    ServerAliveCountMax 3\n'''
    txt=admin_cfg.read_text() if admin_cfg.exists() else ''
    txt=re.sub(r'(?ms)^Host van-trading-core\n(?:^[ \t].*\n?)*','',txt)
    admin_cfg.write_text(txt.rstrip()+block+'\n'); os.chmod(admin_cfg,0o600)

def pipe_secret_to_hermes(remote_path, hermes_path, mode='0600'):
    src=['ssh','-o','BatchMode=yes','-i',str(ADMIN_KEY),f'ubuntu@{PRIVATE_IP}',f'sudo -n cat {shlex.quote(remote_path)}']
    a=subprocess.Popen(src,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    cmd=f'umask 077; mkdir -p ~/.van; cat > {shlex.quote(hermes_path)}; chmod {mode} {shlex.quote(hermes_path)}'
    b=subprocess.run(['ssh','-o','BatchMode=yes','hermes',cmd],stdin=a.stdout,capture_output=True,text=False)
    if a.stdout: a.stdout.close()
    err=a.stderr.read().decode(errors='replace') if a.stderr else ''
    arc=a.wait()
    if arc or b.returncode: raise RuntimeError(f'secret transfer failed rc={arc}/{b.returncode}: {err[-200:]}')

def configure_hermes_access(repo):
    hcfg='''Host van-trading-core\n    HostName 10.0.1.233\n    User ubuntu\n    IdentityFile ~/.ssh/node-hermes-to-trading\n    IdentitiesOnly yes\n    ServerAliveInterval 30\n    ServerAliveCountMax 3\n'''
    py="import re,pathlib,os; p=pathlib.Path.home()/'.ssh/config'; s=p.read_text() if p.exists() else ''; s=re.sub(r'(?ms)^Host van-trading-core\\n(?:^[ \\t].*\\n?)*','',s); p.write_text(s.rstrip()+'\\n\\n'+"+repr(hcfg)+"); os.chmod(p,0o600)"
    ssh('hermes','python3 -c '+shlex.quote(py))
    pipe_secret_to_hermes('/opt/van-trading/secrets/commander.token.hermes','/home/ubuntu/.van/commander.hermes.token')
    # The owner gateway gets its own mutation principal. It is deliberately not the
    # Hermes token and is never placed in the Hermes MCP configuration.
    pipe_secret_to_hermes('/opt/van-trading/secrets/commander.token.van-gateway','/home/ubuntu/.config/van/commander.gateway.token')
    pipe_secret_to_hermes('/opt/van-trading/secrets/pki/ca.crt','/home/ubuntu/.van/van-trading-bridge-ca.crt')
    pipe_secret_to_hermes('/opt/van-trading/secrets/automation/n8n-hermes-api.key','/home/ubuntu/.van/n8n-api.key')
    gateway_commander_env=(
        f'VAN_COMMANDER_URL=https://{PRIVATE_IP}:9133\\n'
        'VAN_COMMANDER_TOKEN_FILE=/home/ubuntu/.config/van/commander.gateway.token\\n'
        'VAN_COMMANDER_CA_FILE=/home/ubuntu/.van/van-trading-bridge-ca.crt\\n'
    )
    remote_write('hermes','/home/ubuntu/.config/van/trading-commander.env',gateway_commander_env,'0600')
    reg=(f'cd {shlex.quote(repo)} && VAN_REPO={shlex.quote(repo)} '
         f'COMMANDER_URL=https://{PRIVATE_IP}:9133 TOKEN_FILE=/home/ubuntu/.van/commander.hermes.token '
         'CA_FILE=/home/ubuntu/.van/van-trading-bridge-ca.crt bash deploy/van-trading-core/hermes/register-commander-mcp.sh')
    ssh('hermes',reg,timeout=60)
    unit='''[Unit]\nDescription=VAN Trading Core n8n management tunnel\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nExecStart=/usr/bin/ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:15678:127.0.0.1:5678 van-trading-core\nRestart=always\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n'''
    remote_write('hermes','/home/ubuntu/.config/systemd/user/van-trading-core-n8n-tunnel.service',unit,'0644')
    ssh('hermes','systemctl --user daemon-reload && systemctl --user enable --now van-trading-core-n8n-tunnel.service',timeout=60)
    env='VAN_TRADING_CORE_HOST=10.0.1.233\nVAN_COMMANDER_URL=https://10.0.1.233:9133\nVAN_N8N_API_URL=http://127.0.0.1:15678/api/v1\n'
    remote_write('hermes','/home/ubuntu/.van/trading-core.env',env,'0600')
    # Re-read the isolated commander environment immediately. A deployment that
    # provisions the mutation credential but leaves the gateway on LocalAccountControl
    # is not a completed account-onboarding path.
    ssh('hermes','systemctl --user daemon-reload && systemctl --user restart van-gateway.service && systemctl --user is-active --quiet van-gateway.service',timeout=60)

def verify_hermes_access(repo):
    p=ssh('hermes',"curl -fsS -H \"X-N8N-API-KEY: $(cat /home/ubuntu/.van/n8n-api.key)\" 'http://127.0.0.1:15678/api/v1/workflows?limit=1' >/dev/null && echo N8N_HERMES_GREEN",timeout=30)
    if 'N8N_HERMES_GREEN' not in p.stdout: raise RuntimeError('Hermes n8n management canary failed')
    live=("printf '%s\\n' '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}' "
          "'{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"status\",\"arguments\":{}}}' | "
          f"VAN_COMMANDER_URL=https://{PRIVATE_IP}:9133 VAN_COMMANDER_TOKEN_FILE=/home/ubuntu/.van/commander.hermes.token "
          f"NODE_EXTRA_CA_CERTS=/home/ubuntu/.van/van-trading-bridge-ca.crt timeout 25 node {shlex.quote(repo)}/trading/commander/mcp_stdio.mjs")
    q=ssh('hermes',live,check=False,timeout=35)
    if q.returncode or '"id":2' not in q.stdout or '"isError":false' not in q.stdout.replace(' ',''):
        raise RuntimeError('Hermes Commander MCP live canary failed: '+q.stdout[-500:]+q.stderr[-300:])
    print('HERMES_COMMANDER_MCP_GREEN',flush=True)

def wait_firstboot(timeout=2400):
    end=time.time()+timeout; last=''
    while time.time()<end:
        p=ssh(f'ubuntu@{PRIVATE_IP}',"sudo -n test -f /var/lib/van-trading/firstboot-complete && echo FIRSTBOOT_DONE || (sudo -n test -f /var/lib/van-trading-firstboot.failed && echo FIRSTBOOT_FAILED || true)",key=ADMIN_KEY,check=False,timeout=20)
        if 'FIRSTBOOT_DONE' in p.stdout: return
        if 'FIRSTBOOT_FAILED' in p.stdout:
            log=ssh(f'ubuntu@{PRIVATE_IP}','sudo -n tail -n 120 /var/log/van-trading-firstboot.log',key=ADMIN_KEY,check=False,timeout=20)
            raise RuntimeError('firstboot failed:\n'+log.stdout[-5000:])
        last=(p.stderr or p.stdout)[-300:]; time.sleep(10)
    raise RuntimeError('firstboot timeout: '+last)

def public_tls_canary(host, timeout=600):
    end=time.time()+timeout; last=''
    while time.time()<end:
        p=run(['curl','-fsS','--max-time','15',f'https://{host}/health'],check=False)
        if p.returncode==0:
            print('PUBLIC_TLS_GREEN',host,flush=True); return
        last=(p.stderr or p.stdout)[-300:]; time.sleep(10)
    raise RuntimeError('public TLS canary failed: '+last)

def main():
    meta=imds(); comp=meta['compartmentId']; ad=meta['availabilityDomain']
    active,by,sub=get_resources(comp)
    protected={by[n]['id'] for n in ('oracle-admin','dial-hermes-control','vekl-worker')}
    doomed=[x for x in active if x['display-name'].startswith('van-trading-core') and (x.get('freeform-tags') or {}).get('project')=='VAN' and (x.get('freeform-tags') or {}).get('role')=='TRADING_CORE']
    force_recreate='--force-recreate' in sys.argv
    dry_run='--dry-run' in sys.argv
    if not doomed:
        print('NO_EXISTING_TRADING_CORE: proceeding with clean creation',flush=True)
    if any(x['id'] in protected for x in doomed):
        raise RuntimeError('protected instance selected for termination')
    print('PROTECTED',[(n,by[n]['id']) for n in ('oracle-admin','dial-hermes-control','vekl-worker')],flush=True)
    print('TRADING_CORE_CANDIDATES',[(x['display-name'],x['id']) for x in doomed],flush=True)
    if doomed and not force_recreate:
        if len(doomed) != 1:
            raise RuntimeError('multiple active trading-core instances found; refusing automatic selection or termination')
        live=doomed[0]
        print('EXISTING_TRADING_CORE_PROTECTED',live['display-name'],live['id'],flush=True)
        print('RESUME_EXISTING_REQUIRED: no OCI lifecycle action taken; use --force-recreate only for explicit owner-approved replacement',flush=True)
        return
    if dry_run:
        action='force-recreate the existing trading core' if doomed else 'create a clean trading core'
        print(f'DRY_RUN_GREEN: would harden trading subnet and {action}; protected control nodes remain untouched',flush=True)
        return
    expected_sha=resolve_repository_sha()
    print('EXPECTED_REPOSITORY_SHA',expected_sha,flush=True)
    apub,hpub=ensure_keys()
    reserved_id,reserved_addr,public_host=ensure_reserved_ip(comp)
    harden_subnet(sub)
    terminate_trading(active)
    run(['ssh-keygen','-R',PRIVATE_IP],check=False)
    ssh('hermes',f'ssh-keygen -R {PRIVATE_IP} >/dev/null 2>&1 || true',check=False)
    image=by['dial-hermes-control']['image-id']
    with tempfile.TemporaryDirectory() as td:
        td=pathlib.Path(td)
        keys=td/'authorized_keys'; keys.write_text(apub+'\n'+hpub+'\n')
        ud=td/'firstboot.sh'; ud.write_text(firstboot(public_host,expected_sha)); os.chmod(ud,0o600)
        iid=launch_instance(comp,ad,sub,image,keys,ud)
    bind_reserved_ip(comp,iid,reserved_id)
    wait_ssh(PRIVATE_IP,ADMIN_KEY,False,900); print('ORACLE_ADMIN_SSH_GREEN',flush=True)
    wait_ssh(PRIVATE_IP,None,True,900); print('HERMES_SSH_GREEN',flush=True)
    install_ssh_aliases()
    wait_firstboot(3000); print('FIRSTBOOT_GREEN',flush=True)
    q=ssh(f'ubuntu@{PRIVATE_IP}',f"sudo -n env VAN_EXPECTED_REPOSITORY_SHA={expected_sha} bash /opt/van-trading/app/deploy/van-trading-core/qualify.sh",key=ADMIN_KEY,timeout=180)
    try: qj=json.loads(q.stdout)
    except Exception as exc: raise RuntimeError('qualification output not JSON') from exc
    if qj.get('status')!='GREEN' or qj.get('required_failures')!=0 or qj.get('repository_sha')!=expected_sha or qj.get('expected_repository_sha')!=expected_sha:
        raise RuntimeError('trading qualification not green for the exact selected repository SHA')
    print('TRADING_QUALIFICATION_GREEN',flush=True)
    repo='/home/ubuntu/work/van-google-runtime-closure'
    configure_hermes_access(repo)
    verify_hermes_access(repo)
    public_tls_canary(public_host,900)
    print(json.dumps({'status':'GREEN','instance_id':iid,'private_ip':PRIVATE_IP,'reserved_public_ip':reserved_addr,'public_host':public_host,'protected_vekl_worker':VEKL_OCID,'branch':BRANCH,'repository_sha':expected_sha},indent=2),flush=True)

if __name__=='__main__':
    main()
