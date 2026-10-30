"""Run existing risk probes under the canonical software test-owner fixture."""
import importlib.util
from pathlib import Path
import sys


def test_existing_gate_probes_have_valid_controls_and_no_crash_credit(capsys):
    path = Path('/workspace/van-review-2026-10-18/publish/trading/tools/induce_gate_failures.py')
    spec = importlib.util.spec_from_file_location('van_risk_fault_probes', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    code = module.main()
    output = capsys.readouterr().out
    Path('/workspace/van-position-original-terms-invariant-faults-r2-20261027.txt').write_text(output)
    assert 'fuzz CRASHED' not in output, 'a probe exception is not semantic mutation evidence'
    assert code == 0
    assert '13/13 probes behaved as expected' in output
