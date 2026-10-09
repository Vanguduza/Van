"""Create a new review branch, then independently compare its checkout bytes and Git modes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys

repo = Path(sys.argv[1]).resolve()
revision = sys.argv[2]
branch = 'codex/van-canon-runtime-closure-2026-10-09'
url = 'https://github.com/Vanguduza/Van.git'
out = Path('/workspace/van-audit')
stem = 'canon-source-publication-' + revision[:8] + '-2026-10-09'
receipt = out/(stem+'.json')
clone = out/(stem+'-remote-readback')
assert not receipt.exists() and not clone.exists()

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()

def remote_refs():
    result = subprocess.check_output(['git', 'ls-remote', url, 'refs/heads/main',
        'refs/heads/'+branch, 'refs/pull/93/head', 'refs/pull/94/head'], text=True)
    return {ref: sha for sha, ref in (line.split() for line in result.splitlines())}

def tree_inputs(path):
    result = {}
    raw = subprocess.check_output(['git', '-C', str(path), 'ls-files', '-s', '-z'])
    for item in raw.split(b'\0'):
        if not item:
            continue
        header, raw_name = item.split(b'\t', 1)
        mode, blob, stage = header.decode().split()
        assert stage == '0' and mode in ('100644', '100755', '120000')
        name = os.fsdecode(raw_name)
        file = path/name
        if mode == '120000':
            value = os.fsencode(os.readlink(file))
            digest = hashlib.sha256(value).hexdigest()
            size = len(value)
        else:
            with file.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            size = file.stat().st_size
            assert bool(file.stat().st_mode & 0o111) == (mode == '100755'), name
        result[name] = {'git_mode': mode, 'git_blob': blob, 'sha256': digest, 'bytes': size}
    return result

assert git(repo, 'rev-parse', 'HEAD') == revision
assert not git(repo, 'status', '--porcelain=v1')
before = remote_refs()
assert 'refs/heads/'+branch not in before, 'Concurrent/existing review branch; never overwrite it'
inputs = tree_inputs(repo)
started = datetime.now(timezone.utc).isoformat()
subprocess.run(['git', '-C', str(repo), 'push',
    '--force-with-lease=refs/heads/'+branch+':', url,
    revision+':refs/heads/'+branch], check=True)
after = remote_refs()
assert after.get('refs/heads/'+branch) == revision
subprocess.run(['git', 'clone', '--single-branch', '--branch', branch, url, str(clone)], check=True)
assert git(clone, 'rev-parse', 'HEAD') == revision and not git(clone, 'status', '--porcelain=v1')
readback = tree_inputs(clone)
differences = sorted(name for name in inputs.keys() | readback.keys() if inputs.get(name) != readback.get(name))
assert not differences, differences
assert git(repo, 'rev-parse', 'HEAD') == revision and not git(repo, 'status', '--porcelain=v1')
assert tree_inputs(repo) == inputs
result = {'source_sha': revision, 'branch': branch, 'repository': url,
    'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
    'publication': 'NEW_REVIEW_BRANCH_VERIFIED', 'refs_before': before, 'refs_after': after,
    'main_unchanged_during_publication': before.get('refs/heads/main') == after.get('refs/heads/main'),
    'existing_pr_heads_unchanged_during_publication': all(before.get(name) == after.get(name) for name in ('refs/pull/93/head','refs/pull/94/head')),
    'independent_https_readback_root': str(clone), 'verified_file_count': len(inputs),
    'comparison': 'actual file bytes and Git tree modes; local write-permission differences are not Git modes',
    'changed_inputs': differences, 'files': inputs, 'main_merged': False,
    'production_deployed': False, 'handset_cases_executed': 0}
receipt.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
print(json.dumps({'receipt': str(receipt), 'source_sha': revision, 'files_verified': len(inputs),
    'main_unchanged': result['main_unchanged_during_publication']}))
