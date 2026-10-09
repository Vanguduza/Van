"""Publish separate review evidence without moving the qualified application branch."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

spec_path = Path(sys.argv[1]).resolve()
spec = json.loads(spec_path.read_text())
revision = spec['source_sha']
out = Path('/workspace/van-audit')
branch = 'codex/van-canon-runtime-evidence-2026-10-09'
url = 'https://github.com/Vanguduza/Van.git'
clone = out / f'canon-evidence-publication-{revision[:8]}-2026-10-09'
readback = out / f'canon-evidence-publication-{revision[:8]}-2026-10-09-remote-readback'
receipt_path = out / f'canon-evidence-publication-{revision[:8]}-2026-10-09.json'
assert not any(path.exists() for path in (clone, readback, receipt_path))
publication_path = out / f'canon-source-publication-{revision[:8]}-2026-10-09.json'
publication = json.loads(publication_path.read_text())
assert publication['source_sha'] == revision
application_ref = 'refs/heads/' + publication['branch']

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()

def remote_refs():
    result = subprocess.check_output(['git', 'ls-remote', url, 'refs/heads/main', application_ref,
                                     'refs/heads/' + branch, 'refs/pull/93/head', 'refs/pull/94/head'], text=True)
    return {ref: oid for oid, ref in (line.split() for line in result.splitlines())}

packet_stem = 'VAN_FINAL_SOURCE_AND_QUALIFICATION_' + revision[:8] + '_2026-10-09'
packet_verification_path = out / (packet_stem + '_VERIFICATION.json')
packet_inventory_path = out / (packet_stem + '_INVENTORY.json')
packet_path = out / (packet_stem + '.zip')
verified_packet = json.loads(packet_verification_path.read_text())
inventory = json.loads(packet_inventory_path.read_text())
packet_artifact_hashes = {str(path): sha(path) for path in (packet_path, packet_inventory_path, packet_verification_path)}
spec_sha256 = sha(spec_path)
assert verified_packet['producer_path'] == str(out / 'package_canon_final_evidence_2026_10_09.py')
assert verified_packet['producer_sha256'] == sha(out / 'package_canon_final_evidence_2026_10_09.py')
assert verified_packet['source_sha'] == inventory['source_sha'] == revision
assert verified_packet['archive_path'] == str(packet_path)
assert verified_packet['inventory_path'] == str(packet_inventory_path)
assert verified_packet['archive_sha256'] == sha(packet_path)
assert verified_packet['inventory_sha256'] == sha(packet_inventory_path)
assert verified_packet['all_originals_unchanged'] is True
assert verified_packet['zip_readback_matches_all_selected_original_bytes'] is True
assert verified_packet['verified_file_count'] == len(spec['files']) == len(inventory['files'])
selected = {}
for record in spec['files']:
    name = record['archive_path']
    assert isinstance(name, str) and '\\' not in name
    assert all(ord(character) >= 32 and ord(character) != 127 for character in name)
    assert str(PurePosixPath(name)) == name
    assert name not in selected
    selected[name] = record
assert set(selected) == set(inventory['files'])
with zipfile.ZipFile(packet_path) as packet:
    assert packet.testzip() is None
    assert set(packet.namelist()) == set(selected) | {'INVENTORY.json'}
    assert packet.read('INVENTORY.json') == packet_inventory_path.read_bytes()
    for name, record in selected.items():
        measured = inventory['files'][name]
        supplied = Path(record['path'])
        assert supplied.is_absolute() and supplied.resolve() == supplied
        assert record['kind'] == measured['kind']
        assert str(supplied) == measured['source_path']
        assert record['reviewed_sha256'] == measured['sha256'] == sha(supplied)
        assert supplied.stat().st_size == measured['bytes']
        assert hashlib.sha256(packet.read(name)).hexdigest() == measured['sha256']

before = remote_refs()
assert before.get(application_ref) == revision
assert 'refs/heads/' + branch not in before, 'Never overwrite existing evidence'
subprocess.run(['git', 'clone', '--shared', publication['independent_https_readback_root'], str(clone)], check=True)
assert git(clone, 'rev-parse', 'HEAD') == revision and not git(clone, 'status', '--porcelain=v1')
subprocess.run(['git', '-C', str(clone), 'switch', '-c', branch], check=True)
subprocess.run(['git', '-C', str(clone), 'config', 'core.hooksPath', '.githooks'], check=True)
destination = clone / 'docs/audit' / ('final-' + revision[:8])
destination.mkdir()
copied = {}
for record in spec['files']:
    source = Path(record['path']).resolve()
    name = record['archive_path']
    assert name and not name.startswith('/') and '..' not in Path(name).parts and '.git' not in Path(name).parts
    assert source.is_file() and sha(source) == record['reviewed_sha256']
    target = destination / name
    assert not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(target) == record['reviewed_sha256']
    copied[str(target.relative_to(clone))] = {'sha256': sha(target), 'bytes': target.stat().st_size, 'kind': record['kind']}
for source, kind in ((packet_inventory_path, 'packet_inventory'),
                     (packet_verification_path, 'packet_verification'), (spec_path, 'packet_selection')):
    target = destination / source.name
    assert not target.exists()
    shutil.copyfile(source, target)
    copied[str(target.relative_to(clone))] = {'sha256': sha(target), 'bytes': target.stat().st_size, 'kind': kind}
readme = destination / 'README.md'
assert not readme.exists()
readme.write_text(
    '# Final VAN source qualification evidence\n\n'
    f'Tested application source: `{revision}` on `{publication["branch"]}`. '
    'This evidence branch adds review documents and receipts; its HEAD is a separate evidence identity. '
    'Use the application SHA for releases and acceptance, and rebuild if integration changes that selected source.\n\n'
    'Open the qualification report and direct DIAL continuation prompt. Preserve individual suite execution '
    'and input-equivalence scopes, the Project Truth failure, privileged skips and physical 0/826. '
    'These receipts do not admit source, sign a production release, deploy a service or test a handset.\n\n'
    f'[Qualification report](review-and-handoff/VAN_FINAL_QUALIFICATION_REVIEW_{revision[:8]}_2026-10-09.md) · '
    f'[Direct DIAL/Artemis prompt](review-and-handoff/VAN_FINAL_DIRECT_DIAL_CONTINUATION_PROMPT_2026-10-09_{revision[:8]}.md) · '
    '[Searchable frontend contract](frontend/VAN_OWNER_FRONTEND_CONTRACT_DFC1557A_2026-10-09.html)\n\n'
    'The packet inventory and verification describe the separately verified local ZIP. '
    'The explicit selection file preserves each original path, category and measured digest. '
    'The source bundle requires PR93 base 4ad31883d57ab518ba9af414aa849db6e240eb71.\n'
)
copied[str(readme.relative_to(clone))] = {'sha256': sha(readme), 'bytes': readme.stat().st_size, 'kind': 'audit_report'}
subprocess.run(['git', '-C', str(clone), 'add', str(destination.relative_to(clone))], check=True)
sys.path.insert(0, str(clone / 'tools/ci'))
import project_truth_ledger as ledger
repo = ledger.Repo(clone)
files = ledger.staged_files(repo)
assert files and all(name.startswith('docs/audit/final-' + revision[:8] + '/') for name in files)
digest = ledger.staged_digest(repo)
change = ledger._Change(repo, None, revision, files)
auths = ledger.Authorizations.load(repo, None, ledger.allowed_authorities(ledger.load_config(repo)))
row = ledger._row(repo, 'precommit-staged-diff',
    'Canonical project_truth_ledger.py helpers; explicit uncovered evidence recording without authorization selection',
    change, digest, [revision], [], auths, set(),
    'Review-only source-bound qualification and direct-DIAL continuation evidence. No authorization record, '
    'signature, trusted intake, deployment or device acceptance is created. Application branch and SHA stay separate.')
assert not row['authorization_ids'] and not row['covered_files'] and row['uncovered_files'] == files
ledger_path = clone / ledger.LEDGER_REL
ledger_prefix = ledger_path.read_bytes()
ledger._append(repo, [row])
assert ledger_path.read_bytes().startswith(ledger_prefix)
repo.git('add', ledger.LEDGER_REL)
assert ledger.staged_digest(repo) == digest
subprocess.run(['git', '-C', str(clone), 'diff', '--cached', '--check'], check=True)
environment = dict(os.environ, PROJECT_TRUTH_ALLOW_UNCOVERED='1')
subprocess.run(['git', '-C', str(clone), 'commit', '-m', 'docs(audit): publish exact-source VAN qualification and Artemis handoff'], env=environment, check=True)
evidence_revision = git(clone, 'rev-parse', 'HEAD')
assert not git(clone, 'status', '--porcelain=v1')
actual_changed = set(git(clone, 'diff', '--name-only', revision, evidence_revision).splitlines())
assert actual_changed == set(copied) | {ledger.LEDGER_REL}
started = datetime.now(timezone.utc).isoformat()
subprocess.run(['git', '-C', str(clone), 'push', '--force-with-lease=refs/heads/' + branch + ':',
                url, evidence_revision + ':refs/heads/' + branch], check=True)
after = remote_refs()
assert after.get('refs/heads/' + branch) == evidence_revision and after.get(application_ref) == revision
subprocess.run(['git', 'clone', '--single-branch', '--branch', branch, url, str(readback)], check=True)
assert git(readback, 'rev-parse', 'HEAD') == evidence_revision and not git(readback, 'status', '--porcelain=v1')
for name, record in copied.items():
    assert sha(readback / name) == record['sha256']
for record in spec['files']:
    assert sha(Path(record['path'])) == record['reviewed_sha256']
assert (readback / ledger.LEDGER_REL).read_bytes() == ledger_path.read_bytes()
assert git(readback, 'diff', '--name-only', revision, evidence_revision).splitlines() == git(clone, 'diff', '--name-only', revision, evidence_revision).splitlines()
assert all(sha(Path(path)) == digest for path, digest in packet_artifact_hashes.items())
assert sha(spec_path) == spec_sha256
result = {
    'record_kind': 'SEPARATE_REVIEW_EVIDENCE_BRANCH_ACTUAL_PUBLICATION',
    'application_sha': revision, 'evidence_sha': evidence_revision, 'evidence_branch': branch,
    'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
    'refs_before': before, 'refs_after': after, 'application_branch_unchanged': after.get(application_ref) == revision,
    'main_unchanged': before.get('refs/heads/main') == after.get('refs/heads/main'),
    'existing_pr_heads_unchanged': all(before.get(name) == after.get(name) for name in ('refs/pull/93/head', 'refs/pull/94/head')),
    'independent_https_readback_root': str(readback), 'files_byte_verified': copied,
    'verified_packet_path': str(packet_path), 'verified_packet_sha256': packet_artifact_hashes[str(packet_path)],
    'verified_packet_inventory_sha256': packet_artifact_hashes[str(packet_inventory_path)],
    'verified_packet_receipt_sha256': packet_artifact_hashes[str(packet_verification_path)],
    'verified_packet_selection_sha256': spec_sha256,
    'all_selected_original_files_unchanged': True,
    'ledger_prefix_preserved': True, 'authorization_ids': [], 'admitted': False,
    'main_merged': False, 'production_deployed': False, 'physical_cases_executed': 0,
}
with receipt_path.open('x') as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps({'receipt': str(receipt_path), 'application_sha': revision,
                  'evidence_sha': evidence_revision, 'files_verified': len(copied)}))
