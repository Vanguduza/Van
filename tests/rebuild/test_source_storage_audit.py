"""Keep the actual filesystem misuse probes in the documentary CI suite."""
import json
from pathlib import Path
import subprocess
import sys


def test_storage_audit_rejects_planted_writes_and_preserves_valid_access():
    tool=Path(__file__).resolve().parents[2]/'tools/rebuild/source_storage_audit.py'
    result=subprocess.run([sys.executable,str(tool),'--selftest'],capture_output=True,text=True,check=True)
    observed=json.loads(result.stdout)
    assert observed['rejected']>=14
    assert observed['allowed_read_and_external_write'] is True
