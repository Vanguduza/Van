"""Review I6 M3 — the gateway and the Harness apply one URL scope rule.

``backend/van_gateway/browser/task_scope.py`` and the Harness helpers
(``deploy/van-browser-core/browser/harness_service.py`` ``VAN_HELPERS_PY``, which runs inside
browser-harness and cannot import the gateway) carry the same ``_vs_*`` block, byte for byte,
and both run the shared vector file ``backend/tests/fixtures/task_scope/url_vectors.v1.json``.
The real-Chromium check that the vectors match the browser's WHATWG parser is in
``backend/tests/test_browser_review_i6_scope.py``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "backend/van_gateway/browser/task_scope.py"
HARNESS = ROOT / "deploy/van-browser-core/browser/harness_service.py"
VECTORS = json.loads((ROOT / "backend/tests/fixtures/task_scope/url_vectors.v1.json").read_text(encoding="utf-8"))
BEGIN = "# --- VAN shared URL scope rule: begin"
END = "# --- VAN shared URL scope rule: end ---"


def _block(text: str) -> str:
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    return text[text.index(BEGIN): text.index(END) + len(END)]


def _harness(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("van_harness_shared_rule", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_block_is_byte_identical_on_both_sides(monkeypatch, tmp_path):
    gateway = _block(GATEWAY.read_text(encoding="utf-8"))
    assert _block(HARNESS.read_text(encoding="utf-8")) == gateway
    # ...and it is what the Harness actually executes (the helpers embedded in its scripts).
    hs = _harness(monkeypatch, tmp_path)
    assert gateway in hs.VAN_HELPERS_PY and gateway in hs.CLICK_SCRIPT and gateway in hs.LANDING_SCRIPT


def _sides(monkeypatch, tmp_path):
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from van_gateway.browser import task_scope

    hs = _harness(monkeypatch, tmp_path)
    return {"gateway": task_scope, "harness": hs}


@pytest.mark.parametrize("side", ["gateway", "harness"])
def test_both_sides_run_the_shared_vectors(monkeypatch, tmp_path, side):
    module = _sides(monkeypatch, tmp_path)[side]
    entries = VECTORS["scope_entries"]
    assert len(VECTORS["vectors"]) >= 40
    for vector in VECTORS["vectors"]:
        parsed = module._vs_parse(vector["input"], vector["base"])
        got = None if parsed is None else {"origin": module._vs_origin(parsed), "path": parsed[3]}
        assert got == vector["parsed"], vector
        assert module._vs_scope_violation(entries, vector["input"], "PAGE", vector["base"]) == vector["violation_docs_scope"], vector
    if side == "gateway":
        from van_gateway.browser.task_scope import TaskScope, url_scope_violation

        scope = TaskScope.model_validate({"entries": entries})
        for vector in VECTORS["vectors"]:
            assert url_scope_violation(scope, vector["input"], base=vector["base"]) == vector["violation_docs_scope"]
    else:
        for vector in VECTORS["vectors"]:
            if vector["base"] is None:
                assert module._van_scope_violation({"entries": entries}, vector["input"]) == vector["violation_docs_scope"]
