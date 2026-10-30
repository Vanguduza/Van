"""Verify every built/downloaded wheel against the tested platform manifest."""
from pathlib import Path
import hashlib
import json
import sys


def verify(directory,manifest):
    root=Path(directory);expected=json.loads(Path(manifest).read_text())['wheels']
    actual={p.name:p for p in root.glob('*.whl')}
    if set(actual)!={row['wheel'] for row in expected}:raise ValueError('MODEL_WHEEL_SET_MISMATCH')
    for row in expected:
        path=actual[row['wheel']]
        if path.stat().st_size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('MODEL_WHEEL_HASH_MISMATCH:'+row['wheel'])
    return len(expected)


if __name__=='__main__':
    print(json.dumps({'verified_wheels':verify(sys.argv[1],sys.argv[2])}))
