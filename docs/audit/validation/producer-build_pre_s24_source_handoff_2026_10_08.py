"""Package and verify current authorized changes without committing or touching the checkout."""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import shutil
import stat
import subprocess
import tarfile

ROOT = Path('/workspace/Van')
OUT = Path('/workspace/van-audit')
STAGE = OUT / 'van-wiring-source-handoff-2026-10-08'
RESTORE = OUT / 'van-wiring-source-restore-check-2026-10-08'
ARCHIVE = OUT / 'van-wiring-source-handoff-2026-10-08.tar.gz'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe(path):
    parts = PurePosixPath(path).parts
    assert parts and not path.startswith('/') and '..' not in parts, path
    return path

assert not STAGE.exists() and not RESTORE.exists() and not ARCHIVE.exists()
base = git('rev-parse', 'HEAD').decode().strip()
freeze_path = 'docs/audit/validation/van-production-source-freeze-2026-10-08.json'
freeze_bytes = (ROOT / freeze_path).read_bytes()
freeze = json.loads(freeze_bytes)
assert base == freeze['base_commit']
assert all(sha((ROOT / p).read_bytes()) == h for p, h in freeze['files'].items())

patch = git('diff', '--binary', 'HEAD')
tracked = [safe(x.decode()) for x in git('diff', '--name-only', '-z', 'HEAD').split(b'\0') if x]
untracked = [safe(x.decode()) for x in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x]
all_files = tracked + untracked
assert len(all_files) == len(set(all_files))
records = {}
for p in all_files:
    src = ROOT / p
    assert not src.is_symlink(), p
    if src.exists():
        assert src.is_file(), p
        records[p] = {'sha256': sha(src.read_bytes()), 'bytes': src.stat().st_size,
                      'mode': oct(stat.S_IMODE(src.stat().st_mode))}
    else:
        assert p in tracked
        records[p] = {'deleted': True}

STAGE.mkdir()
(STAGE / 'tracked.patch').write_bytes(patch)
for p in untracked:
    dst = STAGE / 'untracked' / p
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / p, dst)

manifest = {
    'schema_version': 1,
    'repository': 'Vanguduza/Van',
    'base_commit': base,
    'tracked_patch_sha256': sha(patch),
    'tracked_changed_paths': tracked,
    'untracked_paths': untracked,
    'files': records,
    'production_manifest': freeze_path,
    'production_manifest_sha256': sha(freeze_bytes),
    'scope': 'Exact current source/docs/test/registry changes. Excludes ignored builds, local toolchains, credential bindings and Git metadata. No deployment or handset qualification.',
    'source_control': {'committed': False, 'pushed': False},
}
(STAGE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(STAGE / 'README.md').write_text(f'''VAN source handoff — 8 October 2026

This archive preserves the current authorized implementation, registries and evidence
without committing or pushing. It is based on Vanguduza/Van commit {base}.
The base commit alone does not contain these changes. No deployment, owner release,
provider canary or physical Android acceptance is included.

Use a clean, separate checkout of that exact base commit. Preserve existing local work.
Verify tracked.patch against manifest.json, then run git apply --check tracked.patch
and git apply tracked.patch from that checkout. Copy the relative paths under untracked/
only when each destination is absent or already has the exact manifest hash. Do not
overwrite conflicting local files. Verify the complete production source manifest and
all current registry/validation hashes after restoration.

Start review at docs/audit/VAN_PRE_S24_CLOSURE_2026-10-08.md and
docs/audit/OWNER_FRONTEND_CONTRACT.html. These distinguish supported source functions
from external provider contracts, asset bindings and unverified live readiness. Supplements retain
the original full-suite skips and separately record later actual environment checks.

For later physical acceptance, use tools/certification/NATIVE_ARTEMIS_HANDOFF_PROMPT.md.
Native Artemis must operate directly through DIAL/Commander on dial-control, outside
Hermes orchestration. The app still uses Hermes as its application runtime. The selected
backend is van-trading-core; S24 serial RFCX2054F5W is owner-reported, not independently
observed here. Bind actual host trust, provider credentials and release signing through
operator settings and signed installer provisioning. No in-app host/key fields are needed.

The ignored debug APK and managed cloud toolchains are intentionally outside this source
archive. The recorded debug APK is not a signed owner release. Build and inspect the exact
operator-bound release before claiming live zero-configuration connection acceptance.
''')

# Reconstruct in a directory with no Git metadata or production credentials.
RESTORE.mkdir()
with tarfile.open(fileobj=io.BytesIO(git('archive', '--format=tar', base))) as baseline:
    baseline.extractall(RESTORE, filter='data')
subprocess.run(['git', 'apply', '--check', str(STAGE / 'tracked.patch')], cwd=RESTORE, check=True)
subprocess.run(['git', 'apply', str(STAGE / 'tracked.patch')], cwd=RESTORE, check=True)
for p in untracked:
    dst = RESTORE / p
    assert not dst.exists(), p
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STAGE / 'untracked' / p, dst)
for p, record in records.items():
    target = RESTORE / p
    if record.get('deleted'):
        assert not target.exists(), p
    else:
        assert sha(target.read_bytes()) == record['sha256'], p
        assert oct(stat.S_IMODE(target.stat().st_mode)) == record['mode'], p
assert all(sha((RESTORE / p).read_bytes()) == h for p, h in freeze['files'].items())
assert git('diff', '--binary', 'HEAD') == patch
assert [x.decode() for x in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x] == untracked
assert all(sha((ROOT / p).read_bytes()) == r['sha256'] for p, r in records.items() if not r.get('deleted'))

with tarfile.open(ARCHIVE, 'w:gz') as archive:
    archive.add(STAGE, arcname=STAGE.name)
with tarfile.open(ARCHIVE, 'r:gz') as archive:
    for member in archive.getmembers():
        safe(member.name)
        assert not member.issym() and not member.islnk()
        if member.isfile():
            expected = STAGE.parent / member.name
            assert sha(archive.extractfile(member).read()) == sha(expected.read_bytes()), member.name
checksum = sha(ARCHIVE.read_bytes())
Path(str(ARCHIVE) + '.sha256').write_text(f'{checksum}  {ARCHIVE.name}\n')
receipt = {'schema_version': 1, 'status': 'RESTORED_AND_HASH_VERIFIED',
           'archive': str(ARCHIVE), 'archive_sha256': checksum,
           'archive_bytes': ARCHIVE.stat().st_size, 'base_commit': base,
           'tracked_changed_paths': len(tracked), 'untracked_files': len(untracked),
           'production_files_restored_and_verified': len(freeze['files']),
           'manifest_sha256': sha((STAGE / 'manifest.json').read_bytes()),
           'patch_check': 'PASS', 'source_unchanged_during_packaging': True,
           'physical_tests': 0, 'production_deployment': False}
(OUT / 'van-wiring-source-handoff-verification-2026-10-08.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
