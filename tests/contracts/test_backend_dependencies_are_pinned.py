"""GAP-F-017 — the backend dependency set must be deterministic, not floating.

`backend/requirements.txt` used `>=` for ten of its eleven lines while the trading VM
(`deploy/van-trading-core/requirements-vm.txt`) is exact-pinned throughout. Two installs of
the same commit could resolve to different dependency versions, so CI and a certified host
could silently diverge on the exact bytes running in production.

`backend/requirements.lock` is the fix: every line in it is `==`-pinned, and it is what
`tools/runtime/install_van_gateway_service.sh`, `tools/bootstrap_backend.sh`/`.ps1` and
this repository's CI actually install from. `requirements.txt` stays the human-readable
spec. This file is the contract that keeps the two from drifting apart: every package the
spec names must be locked, and the lock itself must never regress into a floating bound.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "backend" / "requirements.txt"
LOCK = ROOT / "backend" / "requirements.lock"

#: PEP 503 normalization: case-insensitive, `-`/`_`/`.` are interchangeable.
_NORMALIZE_RE = re.compile(r"[-_.]+")


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("-", name).strip().lower()


def _lock_lines() -> list[str]:
    lines = []
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _requirements_package_names() -> list[str]:
    names = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # A package name, optionally with an `[extra]` marker, followed by a version
        # specifier. `uvicorn[standard]>=0.32.0` -> `uvicorn`.
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", stripped)
        assert match, f"unparseable requirements.txt line: {stripped!r}"
        names.append(match.group(1))
    return names


def test_the_lock_file_exists_and_is_not_empty():
    assert LOCK.is_file(), "backend/requirements.lock must exist (GAP-F-017)"
    assert _lock_lines(), "backend/requirements.lock has no pinned packages"


def test_every_lock_line_is_exact_pinned():
    """`==`, never `>=`, `~=`, a bare name, or a second unpinned dependency on the line."""
    for line in _lock_lines():
        match = re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[^,;\s]+$", line)
        assert match, (
            f"backend/requirements.lock line is not exact-pinned: {line!r}. "
            "Every line must be `name==version` with nothing floating."
        )


def test_every_requirements_package_appears_in_the_lock():
    """The spec and the lock must name the same packages, or an install from the lock
    would silently drop something `requirements.txt` says the gateway needs."""
    locked = {_normalize(line.split("==", 1)[0]) for line in _lock_lines()}
    for name in _requirements_package_names():
        assert _normalize(name) in locked, (
            f"{name!r} is in backend/requirements.txt but not pinned in "
            "backend/requirements.lock"
        )


def test_the_lock_has_no_duplicate_packages():
    """Two pins for the same package is ambiguous about which one actually installs."""
    seen: dict[str, str] = {}
    for line in _lock_lines():
        name = _normalize(line.split("==", 1)[0])
        assert name not in seen, (
            f"backend/requirements.lock pins {name!r} twice: {seen[name]!r} and {line!r}"
        )
        seen[name] = line


def test_the_installers_use_the_lock_not_the_floating_spec():
    """GAP-F-017's other half: a lock file nothing installs from fixes nothing."""
    install_script = (
        ROOT / "tools" / "runtime" / "install_van_gateway_service.sh"
    ).read_text(encoding="utf-8")
    assert "pip install --quiet -r" in install_script
    assert "requirements.lock" in install_script
    assert "cp \"$ROOT/backend/requirements.lock\"" in install_script

    bootstrap_sh = (ROOT / "tools" / "bootstrap_backend.sh").read_text(encoding="utf-8")
    assert "pip install -r requirements.lock" in bootstrap_sh

    bootstrap_ps1 = (ROOT / "tools" / "bootstrap_backend.ps1").read_text(encoding="utf-8")
    assert "pip install -r requirements.lock" in bootstrap_ps1

    ci = (ROOT / ".github" / "workflows" / "van-ci.yml").read_text(encoding="utf-8")
    assert "pip install -r requirements.lock" in ci
