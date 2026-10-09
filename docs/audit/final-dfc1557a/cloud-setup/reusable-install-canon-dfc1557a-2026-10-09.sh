#!/usr/bin/env bash
set -euo pipefail

# Root replaces this token with the separately published and qualified commit.
canon_revision='dfc1557ab99ad8d41cf84714e1bb671e89b045e6'
[[ "$canon_revision" =~ ^[0-9a-f]{40}$ ]] || { printf 'A published full VAN commit is required.\n' >&2; exit 2; }
state=/workspace/.onboarding
canon_parent="$state/canon/$canon_revision"
canon_root="$canon_parent/Van"
backend_venv=/workspace/van-audit/canon-backend-venv-2026-10-09
browser_venv=/workspace/van-browser-runtime-venv
mkdir -p "$state" "$canon_parent"
export VAN_CANON_REVISION="$canon_revision" VAN_CANON_ROOT="$canon_root"
export VAN_CANON_BACKEND_PYTHON="$backend_venv/bin/python"
export PIP_CACHE_DIR="$state/pip-cache"
export JAVA_HOME="$state/jdk/usr/lib/jvm/java-21-openjdk-amd64"
export GRADLE_USER_HOME="$state/gradle"
export ANDROID_HOME="$state/android-sdk" ANDROID_USER_HOME="$state/android-user"
export PLAYWRIGHT_BROWSERS_PATH="$state/playwright"
export DIAL_REPO="$canon_parent/dial-development-system"
export VAN_TEST_CHROMIUM="$state/playwright/chromium-1243/chrome-linux64/chrome"
python3 - <<'PLATFORM_CHECK'
import platform,sys
if sys.version_info[:2] != (3,12) or platform.system() != 'Linux' or platform.machine() != 'x86_64':
    raise RuntimeError('The measured browser wheel lock requires CPython 3.12 Linux x86_64; qualify another platform separately')
PLATFORM_CHECK

# Ordinary isolated clones only. Never reset, clean, sync, or build the original
# dirty /workspace/Van checkout, or move /workspace/dial-development-system.
python3 - <<'SOURCE_SETUP'
from pathlib import Path
import json, os, subprocess, tempfile
root=Path(os.environ['VAN_CANON_ROOT']); revision=os.environ['VAN_CANON_REVISION']
dds_revision='64d6b7158c723b7700e5b53175ea8048d4e92d00'
def git(path,*args):
    return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
def pinned_clone(url,path,sha):
    if not path.exists():
        temporary=Path(tempfile.mkdtemp(prefix=path.name+'-clone-',dir=path.parent))
        # A failed partial clone remains separate for diagnosis, never at path.
        subprocess.run(['git','clone','--no-checkout',url,str(temporary)],check=True)
        subprocess.run(['git','-C',str(temporary),'checkout','--detach',sha],check=True)
        temporary.rename(path)
    if git(path,'rev-parse','HEAD') != sha or git(path,'status','--porcelain=v1'):
        raise RuntimeError('Refusing a changed or different existing canonical checkout: '+str(path))
originals={}
for path in (Path('/workspace/Van'),Path('/workspace/dial-development-system')):
    if path.exists():
        originals[str(path)]={'head':git(path,'rev-parse','HEAD'),
                              'status':git(path,'status','--porcelain=v1')}
pinned_clone('https://github.com/Vanguduza/Van.git',root,revision)
dds=root.parent/'dial-development-system'
existing=Path('/workspace/dial-development-system')
if not dds.exists() and not dds.is_symlink():
    if existing.exists() and git(existing,'rev-parse','HEAD')==dds_revision and not git(existing,'status','--porcelain=v1'):
        dds.symlink_to(existing,target_is_directory=True)
    else:
        pinned_clone('https://github.com/Vanguduza/dial-development-system.git',dds,dds_revision)
if git(dds,'rev-parse','HEAD') != dds_revision or git(dds,'status','--porcelain=v1'):
    raise RuntimeError('The explicit DDS dependency changed; do not silently use master')
(root.parent/'original-workspaces-before-setup.json').write_text(json.dumps(originals,indent=2,sort_keys=True)+'\n')
print(json.dumps({'source_revision':revision,'dds_revision':dds_revision,'original_workspaces_modified':False}))
SOURCE_SETUP

# Retain matching isolated environments. The gateway lock is version pinned;
# browser runtime wheels have declared hashes and are installed separately.
if [ ! -x "$backend_venv/bin/python" ]; then python3 -m venv "$backend_venv"; fi
if ! "$backend_venv/bin/python" - <<'BACKEND_VERSIONS'
from importlib import metadata
from pathlib import Path
import os,re
rows=(Path(os.environ['VAN_CANON_ROOT'])/'backend/requirements.lock').read_text().splitlines()+['Pillow==11.3.0']
for line in rows:
    if not line.strip() or line.lstrip().startswith('#'): continue
    match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+)',line.strip())
    if match is None: raise RuntimeError('Backend lock must remain fully exact pinned')
    if metadata.version(match[1]) != match[2]: raise RuntimeError('Installed backend version differs: '+match[1])
BACKEND_VERSIONS
then
    "$backend_venv/bin/python" -m pip install --no-deps -r "$canon_root/backend/requirements.lock" 'Pillow==11.3.0'
fi
"$backend_venv/bin/python" -m pip check
if [ ! -x "$browser_venv/bin/python" ]; then python3 -m venv "$browser_venv"; fi
if ! "$browser_venv/bin/python" - <<'BROWSER_VERSIONS'
from importlib import metadata
from pathlib import Path
import os,re
rows=(Path(os.environ['VAN_CANON_ROOT'])/'deploy/van-browser-stream/requirements.lock').read_text().splitlines()
rows+=['pytest==8.3.5','pytest-asyncio==0.24.0','iniconfig==2.3.1','packaging==26.3','pluggy==1.6.0']
for line in rows:
    if not line.strip() or line.lstrip().startswith('#'): continue
    match=re.match(r'([A-Za-z0-9_.-]+)==([^\s]+)',line.strip())
    if match is None: raise RuntimeError('Browser lock must remain exact pinned')
    if metadata.version(match[1]) != match[2]: raise RuntimeError('Installed browser version differs: '+match[1])
BROWSER_VERSIONS
then
    "$browser_venv/bin/python" -m pip install --require-hashes --no-deps -r "$canon_root/deploy/van-browser-stream/requirements.lock"
    "$browser_venv/bin/python" -m pip install --no-deps 'pytest==8.3.5' 'pytest-asyncio==0.24.0' 'iniconfig==2.3.1' 'packaging==26.3' 'pluggy==1.6.0'
fi
"$browser_venv/bin/python" -m pip check

# Downloads preserve inherited proxy and CA trust. Pins below came from the
# previously verified Gradle distribution, official Google SDK, and signed
# Debian package installation. Changed artifacts require new qualification.
python3 - <<'TOOLS_SETUP'
from pathlib import Path
import hashlib, os, subprocess, tempfile, urllib.request, zipfile
base=Path('/workspace/.onboarding')
def checked(path,digest,size=None):
    if not path.is_file() or (size is not None and path.stat().st_size!=size): return False
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()==digest
def fetch(url,path,digest,size=None):
    if checked(path,digest,size): return
    pending=path.with_suffix(path.suffix+'.canon-pending')
    try:
        with urllib.request.urlopen(url,timeout=60) as source, pending.open('wb') as target:
            while block:=source.read(1024*1024): target.write(block)
        if not checked(pending,digest,size): raise RuntimeError('Downloaded tool differs from its qualified digest: '+path.name)
        pending.replace(path)
    finally: pending.unlink(missing_ok=True)
gradle=base/'gradle-8.11.1'
if not (gradle/'bin/gradle').is_file():
    archive=base/'gradle.zip'
    fetch('https://services.gradle.org/distributions/gradle-8.11.1-bin.zip',archive,'f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6',136920070)
    with zipfile.ZipFile(archive) as contents: contents.extractall(base)
    (gradle/'bin/gradle').chmod(0o755)
jdk=base/'jdk'
if not (jdk/'usr/lib/jvm/java-21-openjdk-amd64/bin/javac').is_file():
    jdk.mkdir(exist_ok=True)
    for name,digest,size in [
        ('openjdk-21-jdk-headless_21.0.12.1+1-1~deb13u1_amd64.deb','f3abafb6c644b03df042824e707cd211ea33254761d7f7b75be3f8dc0df97c7a',83035048),
        ('openjdk-21-jre-headless_21.0.12.1+1-1~deb13u1_amd64.deb','e95f36193e45464ac758e5436f940bf3eaecc77de67188275a42104f58aa7674',41900512)]:
        archive=base/name
        fetch('https://deb.debian.org/debian/pool/main/o/openjdk-21/'+name,archive,digest,size)
        subprocess.run(['dpkg-deb','-x',str(archive),str(jdk)],check=True)
    # Debian's JDK points at /etc/java-21-openjdk. If the managed base image
    # lacks those non-secret configuration files, use the same authenticated
    # package files already extracted under this private prefix.
    for path in (jdk/'usr/lib/jvm/java-21-openjdk-amd64').rglob('*'):
        if not path.is_symlink() or path.exists(): continue
        target=os.readlink(path)
        if target.startswith('/etc/java-21-openjdk/'):
            private=jdk/target.lstrip('/')
            if private.is_file():
                path.unlink();path.symlink_to(os.path.relpath(private,path.parent))
sdk=Path(os.environ['ANDROID_HOME']); user=Path(os.environ['ANDROID_USER_HOME'])
(sdk/'cmdline-tools').mkdir(parents=True,exist_ok=True); user.mkdir(parents=True,exist_ok=True)
if not (sdk/'cmdline-tools/latest/bin/sdkmanager').is_file():
    archive=base/'android-commandline-tools.zip'
    fetch('https://dl.google.com/android/repository/commandlinetools-linux-16111833_latest.zip',archive,'0877a1d048fe4a24efe2eff536ca4223f7adeb58648bb81909d33c446918cfa8',181052239)
    temporary=Path(tempfile.mkdtemp(prefix='sdk-tools-',dir=base))
    with zipfile.ZipFile(archive) as contents: contents.extractall(temporary)
    for executable in (temporary/'cmdline-tools/bin').iterdir(): executable.chmod(0o755)
    (temporary/'cmdline-tools').rename(sdk/'cmdline-tools/latest')
# Verify current critical executable bytes; never overwrite an unexpected tool.
pins={
    'gradle-8.11.1/bin/gradle':'02ab6f50b6361729fcb6d1efecaec111df5bed5068768d8314f5ccca52fe58ca',
    'gradle-8.11.1/lib/gradle-launcher-8.11.1.jar':'caae97e14491e7efabaeaa81233d5869acdfb6b215fbb23671ec0af42d6ada4a',
    'jdk/usr/lib/jvm/java-21-openjdk-amd64/bin/java':'6698f6f10143ed8463b06062281c727152d2e0ae2a3569b1716fbb2c6cedf0ba',
    'jdk/usr/lib/jvm/java-21-openjdk-amd64/bin/javac':'94b4eb733f5d6b44ff7ae8437206de8428ac4e2e3e8efc50b204e54c5d84dcc3',
    'android-sdk/cmdline-tools/latest/bin/sdkmanager':'5705db235fe2b11628e064b825b41afaa8eb42823d276454bff8f4145e8081f5'}
for relative,digest in pins.items():
    if not checked(base/relative,digest): raise RuntimeError('Existing tool differs from its qualified digest: '+relative)
TOOLS_SETUP

# Keep existing Gradle properties. Add current non-secret proxy host/port only;
# never copy proxy credentials or replace unrelated owner configuration.
python3 - <<'GRADLE_PROXY'
from pathlib import Path
import os,urllib.parse
path=Path(os.environ['GRADLE_USER_HOME'])/'gradle.properties';path.parent.mkdir(exist_ok=True)
lines=path.read_text().splitlines() if path.exists() else []
proxy=urllib.parse.urlparse(os.environ.get('HTTPS_PROXY',''))
updates={'org.gradle.workers.max':'2'}
if proxy.hostname:
    for protocol in ('http','https'):
        updates[f'systemProp.{protocol}.proxyHost']=proxy.hostname
        updates[f'systemProp.{protocol}.proxyPort']=str(proxy.port or 80)
lines=[line for line in lines if line.split('=',1)[0].strip() not in updates]
path.write_text('\n'.join(lines+[key+'='+value for key,value in updates.items()])+'\n')
GRADLE_PROXY
python3 - <<'SDK_PACKAGES'
from pathlib import Path
import os,subprocess,urllib.parse
root=Path(os.environ['ANDROID_HOME'])
needed=['platform-tools','platforms;android-36','build-tools;35.0.0','build-tools;36.0.0']
if not all((root/name.replace(';','/')/'package.xml').is_file() for name in needed):
    manager=[str(root/'cmdline-tools/latest/bin/sdkmanager'),f'--sdk_root={root}']
    proxy=urllib.parse.urlparse(os.environ.get('HTTPS_PROXY',''))
    if proxy.hostname: manager+=['--proxy=http',f'--proxy_host={proxy.hostname}',f'--proxy_port={proxy.port or 80}']
    subprocess.run(manager+['--licenses'],input='y\n'*100,text=True,check=True)
    subprocess.run(manager+needed,check=True)
SDK_PACKAGES
if [ ! -x "$VAN_TEST_CHROMIUM" ]; then "$backend_venv/bin/python" -m playwright install chromium; fi

# Workspace-only rsync for installer preservation checks. Qualified archive hashes
# are retained independently of apt's mutable latest-version resolution.
python3 - <<'RSYNC_SETUP'
from pathlib import Path
import hashlib,subprocess,urllib.request
base=Path('/workspace/.onboarding/browser-parser'); packages=base/'packages';root=base/'rsync-root'
packages.mkdir(parents=True,exist_ok=True);root.mkdir(exist_ok=True)
def checked(path,digest):
    if not path.is_file(): return False
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==digest
if not (root/'usr/bin/rsync').is_file():
    for name,digest,component in [
        ('rsync_3.4.1+ds1-5+deb13u4_amd64.deb','8aa122f6ba8d2ff112c72bb9814ee096ee516f0213b36b98bbe79c83c92fb226','r/rsync'),
        ('libpopt0_1.19+dfsg-2_amd64.deb','07f649b706852af937654295697dcfc7858f3295718ec18681dce1704663e4f2','p/popt')]:
        archive=packages/name
        if not checked(archive,digest):
            pending=archive.with_suffix('.canon-pending')
            try:
                with urllib.request.urlopen('https://deb.debian.org/debian/pool/main/'+component+'/'+name,timeout=60) as source,pending.open('wb') as output:
                    while block:=source.read(1024*1024): output.write(block)
                if not checked(pending,digest): raise RuntimeError('rsync archive digest mismatch')
                pending.replace(archive)
            finally: pending.unlink(missing_ok=True)
        subprocess.run(['dpkg-deb','-x',str(archive),str(root)],check=True)
RSYNC_SETUP
mkdir -p "$state/bin"
if [ ! -e "$state/bin/rsync" ]; then
    cat > "$state/bin/rsync" <<'RSYNC_WRAPPER'
#!/bin/sh
exec env LD_LIBRARY_PATH=/workspace/.onboarding/browser-parser/rsync-root/usr/lib/x86_64-linux-gnu /workspace/.onboarding/browser-parser/rsync-root/usr/bin/rsync "$@"
RSYNC_WRAPPER
    chmod 755 "$state/bin/rsync"
fi
python3 - <<'RSYNC_WRAPPER_CHECK'
from pathlib import Path
expected=b'#!/bin/sh\nexec env LD_LIBRARY_PATH=/workspace/.onboarding/browser-parser/rsync-root/usr/lib/x86_64-linux-gnu /workspace/.onboarding/browser-parser/rsync-root/usr/bin/rsync "$@"\n'
if Path('/workspace/.onboarding/bin/rsync').read_bytes()!=expected:
    raise RuntimeError('Unexpected rsync wrapper; preserve and inspect it before execution')
RSYNC_WRAPPER_CHECK
"$state/bin/rsync" --version

# Seed hash-verified public bytes from the retained 805f candidate archive cache.
# The new runtime-fix clone has sealed generated assets, without those archives.
# Every seed object is verified against the final source acquisition lock.
# The dirty original /workspace/Van cache is not consulted. Wrong/missing cache
# objects fall back to the source-locked official URLs with TLS verification.
export VAN_CANON_VOICE_CACHE="$state/canon-voice-acquisition"
python3 - <<'VOICE_CACHE'
from pathlib import Path
import hashlib,json,os,shutil
root=Path(os.environ['VAN_CANON_ROOT']); cache=Path(os.environ['VAN_CANON_VOICE_CACHE'])
source=Path('/workspace/van-audit/canon-runtime-fix-2026-10-09/android/app/build/voice-acquisition')
lock=json.loads((root/'android/voice/acquisition-lock.json').read_text())
manifest=(root/'android/voice/voice_asset_manifest.json').read_bytes()
if hashlib.sha256(manifest).hexdigest()!='7fa17db389349bd587c1f061c7162f9a4c419a552c9d57cd03e8e937bf935e30':
    raise RuntimeError('Selected canon has a different generic acoustic manifest')
asr=[row for row in lock['model_archives'] if row['capability']=='asr'][0]['archive']
if (asr['size'],asr['sha256'])!=(310562559,'ec7f27abbbdba3b261deab9a853803b5ec72cb3295c01a77f34e6de5b62bf5c4'):
    raise RuntimeError('Selected canon does not contain the measured October 9 ASR archive pin')
for row in [x['archive'] for x in lock['model_archives']]+lock.get('raw_models',[]):
    relative=Path(row['archive']) if 'archive' in row else Path('selected')/row['path']
    origin=source/relative;target=cache/relative
    if target.exists() or not origin.is_file(): continue
    with origin.open('rb') as stream: matches=origin.stat().st_size==row['size'] and hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
    if matches:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
VOICE_CACHE
cd "$canon_root"
if ! python3 android/tools/package_voice_assets.py --verify; then
    python3 android/tools/package_voice_assets.py --acquire --cache "$VAN_CANON_VOICE_CACHE"
fi
python3 android/tools/package_voice_assets.py --verify

# Install the collision-safe local functional helper, with no production values.
# Preserve an existing helper if somebody edited it outside this setup script.
helper_candidate=$(mktemp "$state/canon-local-gateway.XXXXXX.py")
cat > "$helper_candidate" <<'CANON_GATEWAY_HELPER'
"""Start and exercise an owned ephemeral local gateway; never a production host."""
from pathlib import Path
import argparse,json,os,secrets,socket,subprocess,tempfile,time,urllib.error,urllib.request
parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');args=parser.parse_args()
root=Path(os.environ['VAN_CANON_ROOT']).resolve(); revision=os.environ['VAN_CANON_REVISION']
if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=revision:
    raise RuntimeError('Selected local gateway source differs from the pinned canon')
if subprocess.check_output(['git','-C',str(root),'status','--porcelain=v1'],text=True).strip():
    raise RuntimeError('Selected canon has pending changes; qualify them separately')
with tempfile.TemporaryDirectory(prefix='canon-local-gateway-',dir='/workspace/.onboarding') as directory:
    state=Path(directory); ingress=secrets.token_urlsafe(32);observability=secrets.token_urlsafe(32)
    with socket.socket() as listener,socket.socket() as hermes:
        listener.bind(('127.0.0.1',0));listener.listen(128);hermes.bind(('127.0.0.1',0))
        # Preserve the managed proxy/CA/runtime environment while keeping every
        # inherited VAN product setting out of this development-only process.
        base='http://127.0.0.1:'+str(listener.getsockname()[1]);env={key:value for key,value in os.environ.items() if not key.upper().startswith('VAN_')}
        env.update(VAN_ENV='development',VAN_DATABASE_PATH=str(state/'gateway.sqlite3'),VAN_INGRESS_TOKEN=ingress,
                   VAN_OBSERVABILITY_TOKEN=observability,VAN_HERMES_BASE_URL='http://127.0.0.1:'+str(hermes.getsockname()[1]),
                   VAN_SCHEDULER_ENABLED='false',PYTHONPATH=str(root/'backend')+os.pathsep+str(root/'trading')+os.pathsep+str(root))
        with (state/'gateway.log').open('w') as log:
            process=subprocess.Popen([os.environ['VAN_CANON_BACKEND_PYTHON'],'-m','uvicorn','van_gateway.app:app',
                                      '--fd',str(listener.fileno())],cwd=state,env=env,
                                     pass_fds=(listener.fileno(),),stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    try:
                        request=urllib.request.Request(base+'/health',headers={'X-Van-Ingress-Token':ingress})
                        with urllib.request.urlopen(request,timeout=2) as response:health=json.load(response)
                        break
                    except (OSError,urllib.error.URLError):
                        if process.poll() is not None:raise RuntimeError('Owned gateway exited during startup')
                        time.sleep(.25)
                else:raise RuntimeError('Owned gateway startup timed out')
                assert health['service']=='van-gateway' and health['ok'] is False
                request=urllib.request.Request(base+'/v1/observability/health',headers={'X-Van-Internal-Token':observability})
                with urllib.request.urlopen(request,timeout=5) as response: operation=json.load(response)
                assert isinstance(operation['audit_chain'],dict)
                try:urllib.request.urlopen(base+'/health',timeout=5)
                except urllib.error.HTTPError as error:assert error.code==401
                else:raise AssertionError('Unauthenticated health was admitted')
                print(json.dumps({'status':'PASS','scope':'OWNED_ISOLATED_LOCAL_GATEWAY','source_revision':revision,
                                  'authenticated_health':True,'observability_readback':True,'unauthenticated_health_status':401,
                                  'hermes_offline':True,'production_qualification':False,'handset_cases_executed':0}),flush=True)
                if args.serve:
                    print('Owned local gateway listening on '+base+'; temporary authentication remains in this process.',flush=True)
                    raise SystemExit(process.wait())
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
CANON_GATEWAY_HELPER
if [ -e "$state/canon-local-gateway.py" ] || [ -L "$state/canon-local-gateway.py" ]; then
    if ! cmp -s "$helper_candidate" "$state/canon-local-gateway.py"; then
        printf 'Preserved existing gateway helper; inspect generated replacement %s.\n' "$helper_candidate" >&2
        exit 2
    fi
    rm "$helper_candidate"
else
    mv "$helper_candidate" "$state/canon-local-gateway.py"
fi

"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
"$state/gradle-8.11.1/bin/gradle" --version
node --version
"$backend_venv/bin/python" - <<'READINESS'
from pathlib import Path
import hashlib,json,os,subprocess
import aiosqlite,cryptography,fastapi,httpx,pypdf,uvicorn
from playwright.sync_api import sync_playwright
base=Path('/workspace/.onboarding')
pins={
    'android-sdk/build-tools/36.0.0/aapt':'c076aeeee8bd3ce58395a093747202265ab80c6c12e59358f598a30a81fde13b',
    'android-sdk/build-tools/36.0.0/apksigner':'b47549e373b895ce6ca620d0c7887e674d9615ffa837a86ac601dcfd04adb0f0',
    'android-sdk/platform-tools/adb':'a902be8f45c6c62e76c9efaf6947a0fa747c9cabd89a2ac8e0d16ecb30b3ed01',
    'playwright/chromium-1243/chrome-linux64/chrome':'8c599d43aec53f2460a31ae2f4af6bd863f8258b34ff519564bc5d4726bfaa1e',
    'browser-parser/rsync-root/usr/bin/rsync':'a56c05b960beb734169619d5760b43ff495e84f85a93eb1f54fe58118262fb20'}
for relative,digest in pins.items():
    with (base/relative).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=digest:raise RuntimeError('Tool artifact drift requires requalification: '+relative)
expected_wrapper=b'#!/bin/sh\nexec env LD_LIBRARY_PATH=/workspace/.onboarding/browser-parser/rsync-root/usr/lib/x86_64-linux-gnu /workspace/.onboarding/browser-parser/rsync-root/usr/bin/rsync "$@"\n'
if (base/'bin/rsync').read_bytes()!=expected_wrapper:
    raise RuntimeError('Unexpected rsync wrapper; preserve and inspect it before use')
with sync_playwright() as manager:
    browser=manager.chromium.launch(executable_path=os.environ['VAN_TEST_CHROMIUM'],headless=True)
    try:
        page=browser.new_page();page.set_content('<title>VAN isolated readiness</title><p id="status">ready</p>')
        assert page.title()=='VAN isolated readiness' and page.locator('#status').inner_text()=='ready'
    finally:browser.close()
print(json.dumps({'backend_dependency_imports':'PASS','local_chromium_functional_request':'PASS','production_browser_qualified':False}))
READINESS
"$browser_venv/bin/python" -c 'import aiohttp,aiortc,av,cryptography,PIL,pytest; print("Browser media/test dependency imports: PASS")'
"$backend_venv/bin/python" "$state/canon-local-gateway.py"
python3 - <<'PRESERVATION'
from pathlib import Path
import json,os,subprocess
root=Path(os.environ['VAN_CANON_ROOT']);before=json.loads((root.parent/'original-workspaces-before-setup.json').read_text())
for name,expected in before.items():
    actual={'head':subprocess.check_output(['git','-C',name,'rev-parse','HEAD'],text=True).strip(),
            'status':subprocess.check_output(['git','-C',name,'status','--porcelain=v1'],text=True).strip()}
    if actual!=expected:raise RuntimeError('Original workspace state changed during setup: '+name)
if subprocess.check_output(['git','-C',str(root),'status','--porcelain=v1'],text=True).strip():
    raise RuntimeError('Canonical source acquired unapproved changes during setup')
print(json.dumps({'setup':'PASS','source_revision':os.environ['VAN_CANON_REVISION'],'original_git_states_unchanged':True,
                  'scope':'CLOUD_DEVELOPMENT_ONLY','full_suites_rerun':False,'production_deployed':False,'physical_handset_cases':0}))
PRESERVATION
