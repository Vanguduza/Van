import json
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
    result = subprocess.run(["bash", "-c", step["run"]], cwd=backend, capture_output=True, text=True)
    assert result.returncode == (2 if preflight_fails else 7), result.stdout + result.stderr
    assert marker.exists() is (not preflight_fails)
    assert json.loads((tmp_path / "artifacts/mutation/mutation-registry.json").read_text())["execution_state"] == "NOT_RUN"


def test_preflight_findings_are_published_even_when_execution_is_refused():
    upload = next(s for s in job()["steps"] if s.get("name") == "Upload mutation report")
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "artifacts/mutation/"
