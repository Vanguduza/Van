"""Execute the real published serializer over unchanged original constructors."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

repo = Path('/workspace/van-review-2026-10-18/publish')
original = Path('/workspace/van-native-context-original74-serializer-20261027')
head = '74b1749a97c9d647776384e9a4da7d4e371f1b4b'
paths = ['trading/vati/risk/contracts.py', 'trading/vati/risk/authority.py',
         'trading/vati/risk/serde.py', 'trading/tests/conftest.py']
hashes = {}
for name in paths:
    actual = (repo / name if name.startswith('trading/tests/') else original / name).read_bytes()
    assert actual == subprocess.check_output(['git', 'show', head + ':' + name], cwd=repo)
    hashes[name] = hashlib.sha256(actual).hexdigest()
sys.path[:0] = [str(original / 'trading'), str(repo / 'trading/tests'), str(repo / 'backend')]
from conftest import snapshot, eurusd
from vati.risk.authority import _canonical_hash
from vati.risk.serde import snapshot_to_dict

value = snapshot(eurusd.__wrapped__(), used_margin=None)
legacy = asdict(value)
legacy.pop('used_margin')
body = snapshot_to_dict(value)
assert 'native_account_context' not in asdict(value)
assert _canonical_hash(value) == _canonical_hash(legacy) == _canonical_hash(body)
fixture = json.loads((repo / 'trading/tests/fixtures/legacy_risk_snapshot_no_margin_74b1749a.json').read_text())
assert body == fixture['snapshot'] and _canonical_hash(value) == fixture['original_snapshot_hash']
receipt = {'source_commit': head, 'source_sha256': hashes, 'snapshot': body,
           'original_snapshot_hash': _canonical_hash(value), 'native_execution_or_authority': False,
           'meaning': 'Original source serialization fixture, not native or financial qualification'}
Path('/workspace/van-native-context-original74-serializer-reexecuted-20261027.json').write_text(
    json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'original_hash': receipt['original_snapshot_hash'], 'original_source_files_verified': len(paths)}))
