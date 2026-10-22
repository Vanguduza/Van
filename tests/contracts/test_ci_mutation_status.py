import json
import os
from collections import Counter
import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def job():
    return yaml.safe_load((ROOT / ".github/workflows/van-ci.yml").read_text())["jobs"]["mutation"]


@pytest.mark.parametrize("preflight_fails", [True, False])
def test_actual_ci_shell_preserves_preflight_and_runner_failures(tmp_path, preflight_fails):
    backend = tmp_path / "backend"
    backend.mkdir()
    (tmp_path / "tools/rebuild").mkdir(parents=True)
    (tmp_path / "tools/audit").mkdir(parents=True)
    (tmp_path / "tools/rebuild/mutation_registry.py").write_text(
        "print('{\"execution_state\":\"NOT_RUN\"}')\n"
        + ("raise SystemExit(2)\n" if preflight_fails else "")
    )
    marker = tmp_path / "executed"
    (tmp_path / "tools/audit/mutation_suite.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
        "print('runner failed')\nraise SystemExit(7)\n"
    )
    step = next(s for s in job()["steps"] if s.get("name") == "Mutation testing (non-blocking)")
    assert job()["continue-on-error"] is True  # existing advisory policy preserved
    assert "continue-on-error" not in step
    result = subprocess.run(["bash", "-c", step["run"]], cwd=backend, capture_output=True, text=True,
                            env={**os.environ, "MUTATION_FAMILY": "python", "MUTATION_SHARD": "0/1"})
    assert result.returncode == (2 if preflight_fails else 7), result.stdout + result.stderr
    assert marker.exists() is (not preflight_fails)
    assert json.loads((tmp_path / "artifacts/mutation/mutation-registry.json").read_text())["execution_state"] == "NOT_RUN"


def test_preflight_findings_are_published_even_when_execution_is_refused():
    upload = next(s for s in job()["steps"] if s.get("name") == "Upload mutation report")
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "artifacts/mutation/"


def test_ci_partitions_cover_every_retained_identity_exactly_once():
    spec = importlib.util.spec_from_file_location("mutation_ci_partition", ROOT / "tools/audit/mutation_suite.py")
    suite = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suite)
    expected = [m[-1] for _, ms, _ in suite.groups() for m in ms] + [m[-1] for m in suite.KOTLIN]
    actual = []
    for row in job()["strategy"]["matrix"]["include"]:
        shard = tuple(map(int, row["shard"].split("/")))
        actual.extend(m[-1] for _, ms, _ in suite.groups(family=row["family"], shard=shard) for m in ms)
        if row["family"] == "kotlin":
            actual.extend(m[-1] for m in suite.select(suite.KOTLIN, shard=shard))
    assert len(expected) == 374
    assert Counter(actual) == Counter(expected)
    assert all(count == 1 for count in Counter(actual).values())


def test_component_runtimes_are_prepared_without_merging_incompatible_locks():
    steps = job()["steps"]
    backend = next(s for s in steps if s.get("name") == "Install backend dependencies")
    browser = next(s for s in steps if s.get("name") == "Install browser mutation dependencies")
    kotlin = next(s for s in steps if s.get("name") == "Resolve and prove the Kotlin control before offline mutations")
    assert backend["if"] == "matrix.family == 'python'"
    assert browser["if"] == "matrix.family == 'browser-agent'"
    assert "--require-hashes -r deploy/van-browser-stream/requirements.lock" in browser["run"]
    assert kotlin["if"] == "matrix.family == 'kotlin'"
    assert "--offline" not in kotlin["run"]
