#!/usr/bin/env python3
"""Refresh reviewed R7 inputs after the parent declares runtime source stable.

The supplied manifest binds reviewed runtime and regression bytes. This producer
does not change modes, source logic, authority, prior reviews, or feature counts.
"""
from pathlib import Path
import copy
import datetime
import hashlib
import json
import subprocess
import sys

ROOT = Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09')
sys.path.insert(0, str(ROOT / 'tools/audit'))
import registry_sources as rs

assert rs.ROOT == ROOT
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
freeze_path = Path(sys.argv[1]).resolve()
freeze = json.loads(freeze_path.read_text())
head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip()
assert head == freeze['base_application_sha']
runtime_files = freeze['files']
assert runtime_files and all(sha(ROOT / f) == h for f, h in runtime_files.items())
assert all(not f.startswith(('tools/ci/', '.githooks/', 'docs/project-state/')) for f in runtime_files)
prior_path = ROOT / 'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r6.json'
prior_hash = sha(prior_path)
assert prior_hash == '9f92777dee9a5b08d239f86fb1a23e38900bfcaea6c7fd76b13befb4fd371539'
prior = json.loads(prior_path.read_text())
output_path = ROOT / 'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json'
assert not output_path.exists(), 'Immutable review already exists'
guide = ROOT / 'docs/audit/OWNER_FRONTEND_REGISTRY_GUIDE.md'
old_guide = guide.read_text()
old_pointer = 'VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r6.json'
assert old_guide.count(old_pointer) == 1
features = json.loads((ROOT / 'registries/owner_features.json').read_text())
screens = json.loads((ROOT / 'registries/owner_screens.json').read_text())
prior_rows = [copy.deepcopy(features['features']), copy.deepcopy(screens['screens'])]
refresher = rs.Refresh({})
checked = 0

def check(v, historical=False):
    global checked
    if isinstance(v, dict):
        if not historical and {'file', 'line', 'ref', 'sha256'} <= v.keys() and v['ref'] == 'WORKSPACE_PATCH':
            assert sha(ROOT / v['file']) == v['sha256'], v
            checked += 1
        for k, child in v.items():
            check(child, historical or k.startswith(('baseline', 'historical')))
    elif isinstance(v, list):
        for child in v:
            check(child, historical)

for doc in (features, screens):
    assert doc['current_source_qualification']['source_review_manifest'] == str(prior_path.relative_to(ROOT))
    # The changed parser/runtime files have no current frontend line citations.
    # A new mismatch must be explicitly reviewed, never silently relocated.
    refresher.walk(doc)
    assert not refresher.unresolved, refresher.unresolved
    check(doc)
assert features['features'] == prior_rows[0] and screens['screens'] == prior_rows[1]
guide.write_text(old_guide.replace(old_pointer, 'VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json'))
files = {f: sha(ROOT / f) for f in prior['files']}
changed = {f for f, h in files.items() if h != prior['files'][f]}
assert changed <= set(runtime_files) | {'docs/audit/OWNER_FRONTEND_REGISTRY_GUIDE.md'}, changed
additional = sorted(set(runtime_files) - set(files))
files.update(runtime_files)
review = {
    'schema_version': 1,
    'status': 'REVIEWED_SOURCE_ONLY',
    'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'base_application_sha': head,
    'files': files,
    'physical_cases_executed': 0,
    'owner_release': False,
    'deployment_accepted': False,
    'actual_native_schema_discovery': False,
    'native_schema_fixture_is_live': False,
    'scope': 'Current byte-bound source review after the final independently reproduced Chromium URL/runtime corrections. R7 binds the reviewed runtime and regression inputs and updates the active guide/manifest pointers. Owner feature/function/surface/endpoint contracts, current citation locations, original historical evidence and CORE_ONLY_V2 roles remain unchanged. Local suites, production deployment, owner release and physical handset acceptance remain separate observations.',
    'prior_source_review_manifest': str(prior_path.relative_to(ROOT)),
    'prior_source_review_manifest_sha256': prior_hash,
    'changed_review_inputs_from_prior': sorted(changed),
    'additional_review_inputs': additional,
    'reviewed_runtime_freeze_path': str(freeze_path),
    'reviewed_runtime_freeze_sha256': sha(freeze_path),
    'source_review_producer_sha256': sha(Path(__file__)),
    'permission_policy': 'Producer changes no file modes; parent owns the final tracked content/permission freeze after this scoped mutation.',
}
assert all(sha(ROOT / f) == h for f, h in files.items())
with output_path.open('x') as out:
    json.dump(review, out, indent=2, ensure_ascii=False)
    out.write('\n')
for doc, filename in ((features, 'owner_features.json'), (screens, 'owner_screens.json')):
    doc.setdefault('historical_source_qualifications', {})['pre_oct9_r7_chromium_runtime_correction'] = copy.deepcopy(doc['current_source_qualification'])
    doc['current_source_qualification']['source_review_manifest'] = str(output_path.relative_to(ROOT))
    doc['current_source_qualification']['source_review_manifest_sha256'] = sha(output_path)
    (ROOT / 'registries' / filename).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
assert sha(prior_path) == prior_hash
assert all(sha(ROOT / f) == h for f, h in runtime_files.items())
print(json.dumps({'review': str(output_path), 'review_sha256': sha(output_path), 'source_inputs': len(files), 'changed_review_inputs': sorted(changed), 'additional_review_inputs': additional, 'current_citations_hash_verified': checked, 'feature_and_screen_rows_unchanged': True, 'prior_review_unchanged': True, 'chmod_calls': 0}))
