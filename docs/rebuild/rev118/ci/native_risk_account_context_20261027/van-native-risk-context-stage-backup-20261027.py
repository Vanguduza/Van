from pathlib import Path
import hashlib
import io
import json
import subprocess
import zipfile

repo = Path('/workspace/van-review-2026-10-18/publish')
work = Path('/workspace')

def git(*args, **kw):
    return subprocess.check_output(['git', *args], cwd=repo, **kw)

def sha(data):
    return hashlib.sha256(data).hexdigest()

base = git('rev-parse', 'HEAD', text=True).strip()
assert base == '74b1749a97c9d647776384e9a4da7d4e371f1b4b'
files = [x for x in git('diff', '--cached', '--name-only', '-z').decode().split('\0') if x]
assert files and all(name.startswith(('docs/rebuild/', 'trading/')) for name in files) and not git('diff', '--cached', '--diff-filter=D', '--name-only')
assert all(not p.startswith('docs/review-inputs/') for p in files)
with zipfile.ZipFile(work / 'van-native-risk-context-source-wip-r4-20261027.zip') as original:
    expected_source = json.loads(original.read('RECOVERY_MANIFEST.json'))['files']
assert set(name for name in files if name.startswith('trading/')) == set(expected_source)
assert all(sha((repo / name).read_bytes()) == digest for name, digest in expected_source.items())
raw = subprocess.run(['git', 'cat-file', '--batch'], cwd=repo, check=True,
    input=''.join(':' + name + '\n' for name in files).encode(), capture_output=True).stdout
stream = io.BytesIO(raw)
staged = {}
for name in files:
    header = stream.readline().decode().strip().split()
    assert len(header) == 3 and header[1] == 'blob', (name, header)
    body = stream.read(int(header[2])); assert stream.read(1) == b'\n'
    assert body == (repo / name).read_bytes(), name
    staged[name] = body
assert stream.read() == b''
manifest = json.loads((repo / 'docs/rebuild/rev118/pre003/SUBMISSION_MANIFEST.json').read_text())
tracked = set(git('ls-files', '-z').decode().split('\0'))
assert all(name in tracked and sha((repo / name).read_bytes()) == digest
           for name, digest in manifest['files'].items())
assert manifest['package_tree'] == 'ac0226a22a95f51642cfeb37b3709b40f7cacf10'
assert manifest['archive_sha256'] == '6c7c7c1cb4fbd4748c0d63ceb2add9bd460778b66fb3b2302e16de09ac3a57a8'
recovery = {'schema': 'van.staged-recovery/1', 'base_commit': base,
            'staged_tree': git('write-tree', text=True).strip(),
            'files': {name: sha(data) for name, data in staged.items()},
            'qualification': 'Verified staged candidate backup before genuine hook. No acceptance.'}
archive = work / 'van-native-risk-context-uncommitted-final-20261027.zip'
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
    z.writestr('RECOVERY_MANIFEST.json', json.dumps(recovery, indent=2) + '\n')
    for name, data in staged.items():
        z.writestr(name, data)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(sha(z.read(name)) == digest for name, digest in recovery['files'].items())
metadata = {'path': str(archive), 'bytes': archive.stat().st_size,
            'sha256': sha(archive.read_bytes()), 'base_commit': base,
            'changed_files': len(files), 'manifest_files': len(manifest['files']),
            'all_manifest_members_tracked': True, 'archive_members_and_crc_verified': True}
(work / 'van-native-risk-context-final-backup-20261027.json').write_text(json.dumps(metadata, indent=2) + '\n')
p = work / 'van-current-checkpoint-20261025.json'
d = json.loads(p.read_text()); c = d['active_checkpoint_v2']; c['final_staged_backup'] = metadata
c['current_packet'] = 'NATIVE_RISK_ACCOUNT_CONTEXT_STAGED_PENDING_GENUINE_HOOK'
c['next'] = 'Genuine hook commit with existing candidate-build authorization; actual required-baseline committed verify; normalpush/readback/exactCI; then sharedfinanciallineage/collateral/alloriginreservations/fullbackendprogramme. No acceptance.'
p.write_text(json.dumps(d, indent=2) + '\n')
print(json.dumps(metadata))
