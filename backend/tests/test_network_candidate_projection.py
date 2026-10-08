"""Canonical network candidate projection retains the guarded execution path."""
import importlib.util
from pathlib import Path
import sys

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "deploy/van-browser-core/browser/harness_service.py"


@pytest.fixture
def worker():
    name = "van_network_candidate_projection_test"
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


def test_network_candidates_use_guarded_runner_and_strip_sensitive_url_parts(worker, monkeypatch):
    calls = []
    def guarded(alias, script):
        calls.append(alias)
        return {"candidates": [
            {"url": "https://example.invalid/search?token=private#private", "initiator_type": "fetch"},
            {"url": "https://username:password@example.invalid/path"},
            {"url": "file:///private"},
            {"url": "https://example.invalid:bad/path"},
            {"url": "https://example.invalid/public"},
        ]}
    monkeypatch.setattr(worker, "_run", guarded)
    monkeypatch.setattr(worker, "run_harness", lambda *_: pytest.fail("unguarded runner must not be used"))
    result = worker.network_candidates({}, "public_research", "example.invalid")
    assert calls == ["public_research"]
    assert result["candidates"] == [
        {"url": "https://example.invalid/search", "initiator_type": "fetch"},
        {"url": "https://example.invalid/public", "initiator_type": "other"},
    ]
    assert worker.OPERATIONS["/network_candidates"] is worker.network_candidates
    assert "/network_candidates" in worker.READ_OPERATIONS


def test_network_candidate_guard_refusal_does_not_return_discovery_data(worker, monkeypatch):
    def refused(*_):
        raise worker.WorkerError("NETWORK_EFFECT_GUARD_LOST", 409)
    monkeypatch.setattr(worker, "_run", refused)
    with pytest.raises(worker.WorkerError, match="NETWORK_EFFECT_GUARD_LOST"):
        worker.network_candidates({}, "public_research", "example.invalid")
