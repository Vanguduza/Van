"""CI prerequisite: the backend job supplies the DDS source contracts the Artemis tests read.

Without the sibling ../dial-development-system, 134 tests in tests/contracts/test_artemis_*
error before asserting anything (van-ci run 39590832158). DDS is private and this repository
is public, so the workflow checks the files out at the pinned commit with a read-only deploy
key instead of copying them here. These tests keep that step honest: the pin is the one the
consolidation declares, the file list covers every DDS path the code reads, the step fails
rather than skips without its key, and it runs before the contract tests.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github" / "workflows" / "van-ci.yml"
DDS = ROOT.parent / "dial-development-system"


def backend_steps():
    return yaml.safe_load(LIVE.read_text())["jobs"]["backend"]["steps"]


def pin_step():
    return next(s for s in backend_steps() if s.get("with", {}).get("repository") == "Vanguduza/dial-development-system")


def verify_step():
    return next(s for s in backend_steps() if s.get("name") == "Verify pinned DDS contract blobs and place the sibling")


def blob_table():
    body = verify_step()["run"].split("<<'EOF'\n", 1)[1].split("\nEOF", 1)[0]
    return dict(reversed(line.split()) for line in body.strip().splitlines())


def test_pin_is_the_declared_native_dependency():
    declared = json.loads((ROOT / "CONSOLIDATION_STATE.json").read_text())["native_dependency"]["commit"]
    assert pin_step()["with"]["ref"] == declared
    assert f'test "$(git rev-parse HEAD)" = {declared}' in verify_step()["run"]


def test_checkout_is_read_only_scoped_and_leaves_no_credential():
    w = pin_step()["with"]
    assert w["ssh-key"] == "${{ secrets.DDS_CONTRACT_READ_DEPLOY_KEY }}"
    assert w["persist-credentials"] is False
    assert "token" not in w


def test_sparse_paths_cover_every_dds_path_the_code_reads():
    sparse = set(pin_step()["with"]["sparse-checkout"].split())
    source = (ROOT / "tools/certification/artemis_acceptance.py").read_text()
    read_by_plan = set(re.findall(r'"((?:agent-system|deploy)/[^"]+)"', source.split("contract_paths = [", 1)[1].split("]", 1)[0]))
    read_by_tests = set(re.findall(r'dial-development-system/([\w./-]+)"', (ROOT / "tests/contracts/test_artemis_acceptance_plan.py").read_text()))
    assert read_by_plan and read_by_plan | read_by_tests <= sparse
    assert set(blob_table()) == sparse


def test_missing_key_fails_rather_than_skips():
    steps = backend_steps()
    guard = next(i for i, s in enumerate(steps) if s.get("name") == "Require the DDS contract read key")
    assert "exit 1" in steps[guard]["run"] and "if" not in steps[guard]
    assert not any("if" in s for s in steps[guard:guard + 3]), "the DDS steps must not be conditional"
    assert "continue-on-error" not in pin_step() and "continue-on-error" not in verify_step()


def test_sibling_is_placed_before_any_test_runs():
    runs = [s.get("run", "") for s in backend_steps()]
    placed = next(i for i, r in enumerate(runs) if "mv .dds-contract-pin ../dial-development-system" in r)
    first_test = next(i for i, r in enumerate(runs) if r.strip().startswith("pytest"))
    assert placed < first_test


def test_recorded_blobs_are_the_pinned_dds_blobs_when_dds_is_present():
    """Where a DDS clone sits beside this checkout (CI after the step, or a developer), the
    table must equal the real blobs at the pin, so the table cannot drift from DDS."""
    if not (DDS / ".git").exists():
        import pytest
        pytest.skip("no DDS git clone beside this checkout; the CI step verifies the same table itself")
    pin = pin_step()["with"]["ref"]
    for path, blob in blob_table().items():
        real = subprocess.run(["git", "-C", str(DDS), "rev-parse", f"{pin}:{path}"], capture_output=True, text=True)
        if real.returncode:  # a sparse CI checkout is the pinned blob already verified by hash-object
            assert subprocess.run(["git", "hash-object", str(DDS / path)], capture_output=True, text=True).stdout.strip() == blob
        else:
            assert real.stdout.strip() == blob


def test_services_run_in_the_stream_hosts_own_hash_locked_environment():
    """The stream-host tests need aiortc/av/aiohttp from deploy/van-browser-stream/requirements.lock,
    whose cryptography/pyee pins differ from the backend lock. The services step must build that
    environment exactly as bootstrap.sh does and run the whole services tree in it."""
    step = next(s for s in backend_steps() if s.get("name") == "Browser Control Agent and stream-host logic")
    run = step["run"]
    assert "--require-hashes -r deploy/van-browser-stream/requirements.lock" in run
    assert 'PYTHONPATH="$PWD:$PWD/backend"' in run
    assert re.search(r"-m pytest -q services\s*$", run.strip())
    assert "--ignore" not in run and "-k " not in run and "continue-on-error" not in step
    lock = (ROOT / "deploy/van-browser-stream/requirements.lock").read_text()
    assert "aiortc==" in lock and lock.count("--hash=sha256:") >= lock.count("==")
