"""Public source sharding preserves the original required gate and other CI jobs."""
from pathlib import Path
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
    assert (ROOT/"tools/audit/mutation_suite.py").read_bytes() == previous
