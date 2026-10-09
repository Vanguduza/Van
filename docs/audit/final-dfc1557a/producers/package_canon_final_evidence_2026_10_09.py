"""Package only explicitly selected local receipts, with independent ZIP readback."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import sys
import zipfile

configuration = Path(sys.argv[1]).resolve()
spec = json.loads(configuration.read_text())
revision = spec['source_sha']
assert len(revision) == 40 and all(c in '0123456789abcdef' for c in revision)
out = Path('/workspace/van-audit')
stem = 'VAN_FINAL_SOURCE_AND_QUALIFICATION_' + revision[:8] + '_2026-10-09'
archive = out / (stem + '.zip')
inventory_path = out / (stem + '_INVENTORY.json')
verification_path = out / (stem + '_VERIFICATION.json')
assert not any(p.exists() for p in (archive, inventory_path, verification_path))

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

files = {}
categories = {
    'qualification_receipt': ({out}, {'.json'}),
    'input_manifest': ({out}, {'.json'}),
    'test_log': ({out}, {'.log'}),
    'junit': ({out}, {'.xml'}),
    'audit_report': ({out}, {'.md', '.json'}),
    'frontend_registry': ({out}, {'.json', '.html', '.md'}),
    'source_patch': ({out}, {'.patch'}),
    'source_bundle': ({out}, {'.bundle'}),
    'public_apk_metadata': ({out}, {'.txt', '.json'}),
    'package_signature_proof': ({out}, {'.txt'}),
    'helper_source': ({out}, {'.py'}),
    'setup_script': ({Path('/workspace/.onboarding')}, {'.sh'}),
    'setup_start_skill': ({Path('/workspace/.onboarding')}, {'.md'}),
    'setup_receipt': ({Path('/workspace/.onboarding')}, {'.json', '.log'}),
}
for record in spec['files']:
    name = record['archive_path']
    assert isinstance(name, str) and '\\' not in name
    assert all(ord(character) >= 32 and ord(character) != 127 for character in name)
    assert str(PurePosixPath(name)) == name
    supplied = Path(record['path'])
    path = supplied.resolve()
    kind = record['kind']
    assert kind in categories
    parents, extensions = categories[kind]
    assert supplied.is_absolute() and path == supplied
    assert path.is_file() and path.parent in parents and path.suffix in extensions
    assert not path.name.startswith('.')
    if kind == 'setup_script':
        assert path.name.startswith('reusable-install-canon-')
    elif kind == 'setup_start_skill':
        assert path.name.startswith('canon-start-skill-')
    elif kind == 'setup_receipt':
        assert path.name.startswith('canon-setup-')
    elif kind == 'frontend_registry':
        assert path.name.startswith('VAN_OWNER_')
    elif kind == 'package_signature_proof':
        assert path.name.startswith('postgres-current-source-final-') and path.name.endswith('-debian-signatures.txt')
    assert digest(path) == record['reviewed_sha256']
    assert name and not name.startswith('/') and '..' not in Path(name).parts
    assert name not in files and name != 'INVENTORY.json'
    assert '.git' not in Path(name).parts
    files[name] = {'kind': kind, 'source_path': str(path), 'bytes': path.stat().st_size,
                   'sha256': digest(path)}
inventory = {
    'record_kind': 'EXPLICIT_LOCAL_SOURCE_AND_QUALIFICATION_EVIDENCE_INVENTORY',
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_sha': revision, 'files': files,
    'physical_cases_executed': 0, 'production_deployed': False,
    'owner_release_qualified': False, 'project_truth_admitted': False,
    'limits': [
        'Local source/build/controlled-service receipts do not qualify production hosts or a handset.',
        'The debug APK and generic model binaries are not included; production release requires existing protected bindings.',
        'Passed, failed and skipped historical runs remain distinct in their original receipts.',
    ],
}
with inventory_path.open('x') as stream:
    json.dump(inventory, stream, indent=2, sort_keys=True)
    stream.write('\n')
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
    bundle.write(inventory_path, 'INVENTORY.json')
    for name, record in files.items():
        bundle.write(record['source_path'], name)
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    assert set(bundle.namelist()) == set(files) | {'INVENTORY.json'}
    assert bundle.read('INVENTORY.json') == inventory_path.read_bytes()
    for name, record in files.items():
        raw = bundle.read(name)
        assert len(raw) == record['bytes']
        assert hashlib.sha256(raw).hexdigest() == record['sha256']
        assert digest(Path(record['source_path'])) == record['sha256']
verification = {
    'record_kind': 'LOCAL_EVIDENCE_ZIP_INDEPENDENT_READBACK',
    'source_sha': revision, 'archive_path': str(archive),
    'archive_bytes': archive.stat().st_size, 'archive_sha256': digest(archive),
    'inventory_path': str(inventory_path), 'inventory_sha256': digest(inventory_path),
    'verified_file_count': len(files), 'all_originals_unchanged': True,
    'zip_readback_matches_all_selected_original_bytes': True,
    'physical_cases_executed': 0, 'production_deployed': False,
    'producer_path': str(Path(__file__)), 'producer_sha256': digest(Path(__file__)),
}
with verification_path.open('x') as stream:
    json.dump(verification, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps(verification, sort_keys=True))
