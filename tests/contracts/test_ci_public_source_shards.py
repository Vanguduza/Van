"""Public source sharding preserves the original required gate and other CI jobs."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = "fd33b0759b9ae170f8bdfdf27f9afe7082da7830"


def workflows():
    old = subprocess.check_output(["git", "show", BASE+":.github/workflows/van-ci.yml"], cwd=ROOT)
    return yaml.safe_load(old), yaml.safe_load((ROOT/".github/workflows/van-ci.yml").read_text())


def test_every_other_job_trigger_and_concurrency_boundary_is_unchanged():
    before, after = workflows()
    assert {k:v for k,v in before.items() if k != "jobs"} == {k:v for k,v in after.items() if k != "jobs"}
    assert set(after["jobs"]) == set(before["jobs"]) | {"backend-public-source-gateway"}
    for name, job in before["jobs"].items():
        if name != "backend-public-source": assert after["jobs"][name] == job, name


def test_original_required_gate_is_an_always_running_fail_closed_aggregate():
    _, after = workflows()
    gate = after["jobs"]["backend-public-source"]
    assert gate["name"] == "backend-public-source"
    assert gate["needs"] == ["backend-public-source-gateway"] and gate["if"] == "always()"
    verify = next(s for s in gate["steps"] if "verify-shards" in s.get("run", ""))
    assert verify["if"] == "always()"
    assert '--job-result "${{ needs.backend-public-source-gateway.result }}"' in verify["run"]
    assert '--expected-commit "${{ github.event.pull_request.head.sha || github.sha }}"' in verify["run"]
    assert not gate.get("continue-on-error", False)


def test_four_workers_are_fresh_native_fixtures_with_the_original_dependencies():
    before, after = workflows()
    old = before["jobs"]["backend-public-source"]
    worker = after["jobs"]["backend-public-source-gateway"]
    assert worker["strategy"] == {"fail-fast": False, "max-parallel": 4, "matrix": {"shard": [0,1,2,3]}}
    assert not worker.get("continue-on-error", False)
    for job in (worker, after["jobs"]["backend-public-source"]):
        for key in ("runs-on", "services", "env", "timeout-minutes"): assert job[key] == old[key], key
        assert job["steps"][:5] == old["steps"][:5]
    command = next(s["run"] for s in worker["steps"] if "run-shard" in s.get("run", ""))
    assert "--shards 4 --shard-index ${{ matrix.shard }}" in command
    assert '--expected-commit "${{ github.event.pull_request.head.sha || github.sha }}"' in command
    assert 'runner.temp }}/van-public-gateway-${{ matrix.shard }}' in command
    assert "pytest-xdist" not in command and " -n " not in command


def test_independent_full_collection_and_separate_hashed_media_runtime_remain():
    _, after = workflows()
    steps = after["jobs"]["backend-public-source"]["steps"]
    control = next(s for s in steps if "--runtime gateway --shards 4" in s.get("run", ""))
    assert control["if"] == "always()" and " collect " in " ".join(control["run"].split())
    media = next(s for s in steps if 'python -m venv "$RUNNER_TEMP/public-media-venv"' in s.get("run", ""))
    assert media["if"] == "always()"
    assert "--require-hashes -r deploy/van-browser-stream/requirements.lock" in media["run"]
    assert "--runtime media --shards 1" in media["run"]
    assert "media-control" in media["run"] and "run-shard" in media["run"]


def test_all_shard_evidence_and_original_named_aggregate_artifact_are_uploaded():
    _, after = workflows()
    worker = after["jobs"]["backend-public-source-gateway"]
    upload = next(s for s in worker["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert upload["if"] == "always()" and upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["name"] == "van-backend-public-source-gateway-${{ matrix.shard }}"
    aggregate = after["jobs"]["backend-public-source"]
    download = next(s for s in aggregate["steps"] if s.get("uses") == "actions/download-artifact@v4")
    assert download["if"] == "always()" and download["with"]["merge-multiple"] is False
    final = next(s for s in aggregate["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert final["if"] == "always()" and final["with"]["name"] == "van-backend-public-source"


def test_workflow_installer_mirror_and_frozen_mutation_source_remain_exact():
    assert (ROOT/".github/workflows/van-ci.yml").read_bytes() == (ROOT/"tools/ci/github-actions-ci.yml").read_bytes()
    previous = subprocess.check_output(["git", "show", BASE+":tools/audit/mutation_suite.py"], cwd=ROOT)
    # The independently reviewed LAC234 packet admitted exactly five retained edits.
    # Preserve the original frozen core, rather than rebasing the guard to arbitrary
    # current bytes or treating an authorized retarget as permission to alter a case.
    assert hashlib.sha256(previous).hexdigest() == "cbf114a3374538eeb1403d3f066ee4f22d2405b32e6a7f6b752fa9fe0d9a99df"
    current = (ROOT/"tools/audit/mutation_suite.py").read_bytes()
    assert hashlib.sha256(current).hexdigest() == "789f46dfefa7b022d869751e1548ca95a74177d6b51c4699f8d2692cdcc8c450"
    provenance = ROOT/"docs/rebuild/rev118/receipts/raw/queue-restoration-20261101/CATALOG_RECONCILIATION.json"
    assert hashlib.sha256(provenance.read_bytes()).hexdigest() == "290d5cd494d411ea03d7214f76d066fc08a9b542731016b1b9ed39dafcaf4d13"
    reviewed = json.loads(provenance.read_bytes())
    assert reviewed["identities_before_after"] == 374
    assert reviewed["edits_before_after"] == 383
    assert reviewed["case_order_ids_targets_test_selection_unchanged"] is True
    changes = {case["id"]: case for case in reviewed["exact_five_changes"]}
    assert len(changes) == 5
    restored = ast.parse(current)
    found = set()
    for node in ast.walk(restored):
        if not (isinstance(node, ast.Tuple) and len(node.elts) == 4
                and isinstance(node.elts[-1], ast.Constant) and node.elts[-1].value in changes):
            continue
        identity = node.elts[-1].value
        assert identity not in found
        found.add(identity)
        case = changes[identity]
        original, retarget = case["original"], case["retargeted"]
        assert original["id"] == retarget["id"] == identity
        assert original["tests"] == retarget["tests"]
        assert len(original["edits"]) == len(retarget["edits"]) == 1
        old, new = original["edits"][0], retarget["edits"][0]
        assert old[0] == new[0]
        assert ast.literal_eval(node.elts[1]) == new[1]
        assert ast.literal_eval(node.elts[2]) == new[2]
        node.elts[1], node.elts[2] = ast.Constant(old[1]), ast.Constant(old[2])
    assert found == set(changes)
    # Restoring only those ten string values must recover the entire original AST:
    # every case ID, order, target, selection, other edit and execution helper remains.
    assert ast.dump(restored) == ast.dump(ast.parse(previous))
    admitted = "629a986019a4eb298f58dd98c62e6bcbade36ab7"
    assert subprocess.check_output(["git", "show", admitted+":tools/audit/mutation_suite.py"], cwd=ROOT) == current
    rows = subprocess.check_output(["git", "show", admitted+":docs/project-state/LOCAL_CHANGE_LEDGER.jsonl"], cwd=ROOT)
    row = json.loads(rows.splitlines()[-1])
    assert "auth-20261022-owner-mutation-registry-reconciliation" in row["authorization_ids"]
    assert "tools/audit/mutation_suite.py" in row["changed_files"]
