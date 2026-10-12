"""Pure, no-host-mutation qualification for Muse zram recovery."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "van-trading-core" / "muse_zram_relief.py"
spec = importlib.util.spec_from_file_location("muse_zram_relief", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_swap_names_accept_column_extensions():
    assert module.swap_names("/dev/zram0 partition 2G 1.8G 150 UUID LABEL\n/dev/zram1 partition 2G 0B 150") == {
        "/dev/zram0", "/dev/zram1"
    }


def test_swap_names_empty():
    assert module.swap_names("") == set()


def test_active_device_never_runs_initialization(monkeypatch):
    monkeypatch.setattr(module, "verify_existing", lambda dev: True)
    monkeypatch.setattr(module, "run", lambda *a: (_ for _ in ()).throw(AssertionError("unexpected write")))
    module.ensure_device("/dev/zram0", {"/dev/zram0"})


def test_active_missing_device_fails_closed(monkeypatch):
    monkeypatch.setattr(module, "verify_existing", lambda dev: False)
    try:
        module.ensure_device("/dev/zram0", {"/dev/zram0"})
    except module.ZramRefusal as exc:
        assert "active_zram_missing" in str(exc)
    else:
        raise AssertionError("must refuse inconsistent active device")


def test_check_mode_is_read_only(monkeypatch):
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module, "observe_swaps", lambda: set(module.DEVICES))
    monkeypatch.setattr(module, "verify_existing", lambda dev: True)
    monkeypatch.setattr(module, "run", lambda *a: (_ for _ in ()).throw(AssertionError("must not initialize")))
    assert module.main(["--check"]) == 0


def test_unauthorized_arguments_fail_closed(monkeypatch):
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    try:
        module.main(["--reset"])
    except module.ZramRefusal:
        pass
    else:
        raise AssertionError("unexpected reset accepted")
