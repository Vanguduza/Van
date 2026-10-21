"""Review I minor 5 — run the van-browser-core Stagehand worker and ask it, not its source.

Before the fix the worker, in its production state on van-browser-core, still served
``POST /act`` (answering ``STAGEHAND_ACTION_INVALID`` rather than ``NOT_FOUND``), and
``/health.runtime_version`` was the constant ``"4.1.0"`` whatever package was installed —
so the placement gate's version check could never fail. These tests start the real
``stagehand_service.mjs`` against stub ``@browserbasehq/stagehand`` / ``zod`` packages (no
network, no browser, no model) and read what it actually serves.

Skipped when ``node`` is not installed; the source-level contracts in
``test_van_browser_core_zone.py`` still run.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "deploy" / "van-browser-core" / "browser" / "stagehand_service.mjs"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stub_packages(root: Path, stagehand_version: str) -> None:
    sh = root / "node_modules" / "@browserbasehq" / "stagehand"
    (sh / "dist").mkdir(parents=True)
    # The entry lives in a nested dir with its own nameless package.json, as real builds do,
    # so the worker has to find the package's own metadata rather than the nearest file.
    (sh / "package.json").write_text(json.dumps({
        "name": "@browserbasehq/stagehand", "version": stagehand_version,
        "type": "module", "main": "dist/index.js",
    }), encoding="utf-8")
    (sh / "dist" / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
    (sh / "dist" / "index.js").write_text(
        "export class Stagehand { static async create() { return { act: async () => {}, close: async () => {} }; } }\n"
        "export const localBrowser = { connect: async () => ({}) };\n",
        encoding="utf-8",
    )
    zod = root / "node_modules" / "zod"
    zod.mkdir(parents=True)
    (zod / "package.json").write_text(json.dumps({"name": "zod", "version": "0.0.0-stub", "type": "module",
                                                  "main": "index.js"}), encoding="utf-8")
    (zod / "index.js").write_text("export const z = {};\n", encoding="utf-8")


class _Worker:
    def __init__(self, tmp_path: Path, *, stagehand_version: str = "4.1.0", dev_only: bool = False) -> None:
        _stub_packages(tmp_path, stagehand_version)
        script = tmp_path / "stagehand_service.mjs"
        shutil.copyfile(WORKER, script)
        self.port = _free_port()
        env = {k: v for k, v in os.environ.items() if not k.startswith("VAN_")}
        env.update(VAN_TRUST_ZONE="van-browser-core", VAN_STAGEHAND_PORT=str(self.port),
                   VAN_BROWSER_SECRET_ROOT=str(tmp_path / "secrets"))
        if dev_only:
            env["VAN_BROWSER_HISTORICAL_DEV_ONLY"] = "1"
        self.proc = subprocess.Popen([NODE, str(script)], cwd=tmp_path, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while True:
            try:
                self.health = self.get("/health")[1]
                return
            except (urllib.error.URLError, ConnectionError):
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    out = self.proc.stdout.read().decode() if self.proc.stdout else ""
                    self.close()
                    raise AssertionError(f"worker did not start: {out}")
                time.sleep(0.1)

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def get(self, path: str) -> tuple[int, dict]:
        return self._request("GET", path)

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        return self._request("POST", path, body)

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


@pytest.fixture
def worker_factory(tmp_path):
    started: list[_Worker] = []

    def make(**kwargs) -> _Worker:
        sub = tmp_path / f"w{len(started)}"
        sub.mkdir()
        w = _Worker(sub, **kwargs)
        started.append(w)
        return w

    yield make
    for w in started:
        w.close()


def test_production_state_does_not_serve_act(worker_factory):
    w = worker_factory()
    assert w.health["production_state"] == "VAN_BROWSER_CORE_PENDING_GATES"
    assert w.health["act_endpoint_enabled"] is False
    assert w.post("/act", {}) == (404, {"error": "NOT_FOUND"})
    assert w.post("/act", {"action": {"method": "click", "selector": "#x"}}) == (404, {"error": "NOT_FOUND"})
    # The other refusals are unchanged.
    assert w.post("/agent", {}) == (409, {"error": "DIRECT_STAGEHAND_AGENT_LOOP_FORBIDDEN"})


def test_development_only_placement_is_the_only_one_that_serves_act(worker_factory):
    w = worker_factory(dev_only=True)
    assert w.health["production_state"] == "DEV_ONLY_NOT_PRODUCTION"
    assert w.health["act_endpoint_enabled"] is True
    status, body = w.post("/act", {})
    assert status != 404 and body == {"error": "STAGEHAND_ACTION_INVALID"}


def test_health_reports_the_installed_package_version(worker_factory):
    w = worker_factory(stagehand_version="4.1.0")
    assert w.health["runtime_version"] == "4.1.0"
    assert w.health["runtime_version_source"] == "installed-package-metadata"
    assert w.health["expected_runtime_version"] == "4.1.0"


def test_a_different_installed_version_is_reported_and_fails_placement(worker_factory, tmp_path):
    w = worker_factory(stagehand_version="4.2.0-alpha-ad2bf12e")
    assert w.health["runtime_version"] == "4.2.0-alpha-ad2bf12e"

    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from van_gateway.automation.placement import stagehand_production_enabled
        from van_gateway.config import Settings
    finally:
        sys.path.pop(0)
    pki = {}
    for field in ("browser_core_ca_file", "browser_core_client_cert_file", "browser_core_client_key_file"):
        f = tmp_path / field
        f.write_text("x", encoding="utf-8")
        pki[field] = str(f)
    s = Settings(browser_enabled=True, browser_stagehand_zone="van-browser-core",
                 browser_stagehand_base_url="https://10.77.0.6:9443/stagehand", **pki)
    assert stagehand_production_enabled(s, worker_health=w.health) == (False, "STAGEHAND_RUNTIME_VERSION_MISMATCH")
    # The same health, claiming 4.1.0 from the metadata, would get past the version check —
    # so the check is live, not structurally unsatisfiable.
    passed = dict(w.health, runtime_version="4.1.0")
    assert stagehand_production_enabled(s, worker_health=passed)[1] != "STAGEHAND_RUNTIME_VERSION_MISMATCH"
