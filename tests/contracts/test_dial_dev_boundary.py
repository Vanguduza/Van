"""VAN-DEV-001 — the DIAL development projection is reached through the VAN gateway only.

DIAL VAN-DEVCC-R1 §8, contract half, in the shape of `test_artemis_console_boundary.py`:
Android source carries no DIAL address, port, credential or upstream path, and every DIAL
development call the phone makes is a `/v1/dial-dev/*` route the gateway actually serves.
The DIAL-scoped credential lives in a gateway-side token file, and the only code that reads
it is `backend/van_gateway/dial_dev/client.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
BACKEND = ROOT / "backend" / "van_gateway"
DIAL_DEV = BACKEND / "dial_dev"

sys.path.insert(0, str(ROOT / "backend"))

from van_gateway.dial_dev.config import (  # noqa: E402
    ACTIONS,
    ACTIONS_PATH,
    HUB_CHILDREN,
    PREFIX,
    UPSTREAM_PREFIX,
)


def _android_sources() -> dict[Path, str]:
    """Everything that ships in, or builds, the Android app — not only Kotlin."""
    suffixes = {".kt", ".kts", ".java", ".xml", ".json", ".properties", ".gradle"}
    return {
        path: path.read_text(encoding="utf-8", errors="ignore")
        for path in ANDROID.rglob("*")
        if path.is_file() and path.suffix in suffixes and "build" not in path.parts
    }


#: What would mean the phone is talking to DIAL, or holding what lets it.
FORBIDDEN_IN_ANDROID = (
    "10.77.0.",            # the WireGuard overlay dial-control binds to (§3)
    "dial-control",        # DIAL's host, by name
    "dial-dev.token",      # the gateway-side token file
    "VAN_DIAL_DEV_",       # the gateway's configuration surface
    "dial_dev_token",
    UPSTREAM_PREFIX + "/",  # "/v1/dev/" — DIAL's own API path
)


def _leaks(sources: dict) -> list[str]:
    return [
        f"{path}: {needle!r}"
        for path, text in sources.items()
        for needle in FORBIDDEN_IN_ANDROID
        if needle in text
    ]


def test_android_holds_no_dial_address_port_credential_or_upstream_path():
    offenders = _leaks({p.relative_to(ROOT): t for p, t in _android_sources().items()})
    assert offenders == [], "Android reaches past the gateway:\n" + "\n".join(offenders)


def test_the_scan_would_catch_a_leak():
    """A grep that cannot fail proves nothing: plant each needle and watch it be found."""
    planted = {
        f"Planted{i}.kt": f'const val X = "{needle}"' for i, needle in enumerate(FORBIDDEN_IN_ANDROID)
    }
    assert len(_leaks(planted)) == len(FORBIDDEN_IN_ANDROID)
    assert _leaks({"Clean.kt": 'const val DIAL_DEV = "/v1/dial-dev"'}) == []


def _gateway_dial_dev_paths() -> set[str]:
    reads = {
        f"{PREFIX}/projects",
        f"{PREFIX}/projects/{{}}/home",
        f"{PREFIX}/projects/{{}}/stage-plan",
        f"{PREFIX}/projects/{{}}/tasks",
        f"{PREFIX}/projects/{{}}/graph",
        f"{PREFIX}/tasks/{{}}",
        f"{PREFIX}/agents",
        f"{PREFIX}/workspaces",
        f"{PREFIX}/workspaces/{{}}",
        f"{PREFIX}/workspaces/{{}}/diff",
        f"{PREFIX}/workspaces/{{}}/terminal-tail",
        f"{PREFIX}/evidence/{{}}",
        f"{PREFIX}/infrastructure",
        f"{PREFIX}/events",
        ACTIONS_PATH,
    }
    return reads | {f"{PREFIX}/{child}" for child in HUB_CHILDREN}


def test_the_gateway_serves_exactly_the_contract_routes():
    """The Android worker is held to these; so is the gateway."""
    from van_gateway.dial_dev.api import build_dial_dev_router
    from van_gateway.dial_dev.client import DialDevClient
    from van_gateway.dial_dev.config import DialDevConfig

    router = build_dial_dev_router(
        client=DialDevClient(DialDevConfig()), config=DialDevConfig(), idempotency=None,
    )
    served = {re.sub(r"\{[^}]+\}", "{}", route.path) for route in router.routes}
    assert served == _gateway_dial_dev_paths()
    methods = {route.path: route.methods for route in router.routes}
    assert methods[ACTIONS_PATH] == {"POST"}
    assert all(m == {"GET"} for p, m in methods.items() if p != ACTIONS_PATH)


def _normalise(literal: str) -> str:
    # Kotlin string templates (`$id`, `${task.id}`) are path parameters; a query string is
    # not part of the route.
    path = literal.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*", "{}", path)
    return path.rstrip("/")


def test_every_dial_dev_path_the_phone_builds_is_one_the_gateway_serves():
    """Vacuous until the Android half lands; binding from the moment it does."""
    served = _gateway_dial_dev_paths()
    unknown = []
    for path, text in _android_sources().items():
        for literal in re.findall(r'"(/v1/dial-dev[^"]*)"', text):
            normalised = _normalise(literal)
            if normalised == PREFIX:
                continue  # a prefix constant, joined later
            if normalised not in served:
                unknown.append(f"{path.relative_to(ROOT)}: {literal}")
    assert unknown == [], "the phone builds routes the gateway does not serve:\n" + "\n".join(unknown)


def test_the_phone_never_posts_a_dial_action_without_a_proof():
    """§1 — every dev action goes through `postProved`."""
    for path, text in _android_sources().items():
        for match in re.finditer(r"(postJson|postRawAt|post)\s*\(\s*\"[^\"]*dial-dev[^\"]*actions", text):
            raise AssertionError(f"{path.relative_to(ROOT)} posts a DIAL action without a proof: {match.group(0)}")


def test_the_action_route_is_hardware_device_proofed_in_the_gateway():
    app = (BACKEND / "app.py").read_text(encoding="utf-8")
    assert "or path == DIAL_DEV_ACTIONS_PATH" in app
    assert ACTIONS_PATH == "/v1/dial-dev/actions"
    api = (DIAL_DEV / "api.py").read_text(encoding="utf-8")
    assert 'getattr(request.state, "van_device_proved", False)' in api


def test_only_the_client_reads_the_credential_and_no_van_header_goes_upstream():
    def files_containing(needle: str) -> list[str]:
        return sorted(
            str(path.relative_to(ROOT)) for path in BACKEND.rglob("*.py")
            if needle in path.read_text(encoding="utf-8")
        )

    # Configured in one place, carried in one dataclass, read in one function.
    assert files_containing("dial_dev_token_file") == [
        "backend/van_gateway/config.py",
        "backend/van_gateway/dial_dev/config.py",
    ]
    assert files_containing("Path(self.config.token_file).read_text") == [
        "backend/van_gateway/dial_dev/client.py",
    ]
    client = (DIAL_DEV / "client.py").read_text(encoding="utf-8")
    assert '"Authorization": f"Bearer {token}"' in client
    assert "X-Van-" not in client
    assert "request.headers" not in client
    assert "follow_redirects=False" in client
    assert "trust_env=False" in client


def test_the_action_vocabulary_is_the_contracts_and_nothing_else():
    assert ACTIONS == {
        "STEER_TASK", "PAUSE_TASK_SAFE", "RESUME_TASK", "REQUEST_CHECKPOINT",
        "REQUEST_REVIEW", "REVOKE_TASK", "DECIDE", "PAUSE_MISSION", "RESUME_MISSION",
        "REPRIORITISE",
    }


def test_van_forms_no_agent_loop_over_dial():
    """SECURITY_POLICY: Hermes `van` is the sole VAN agent runtime.

    The dial_dev package may read DIAL and forward typed owner actions. It must not reach
    VAN's Hermes bridge, the command orchestrator or the mission service — the moment it
    did, VAN would be planning DIAL work rather than displaying it.
    """
    for path in DIAL_DEV.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("van_gateway.hermes", "van_gateway.orchestrator",
                          "van_gateway.mission", "van_gateway.command"):
            assert forbidden not in text, f"{path.relative_to(ROOT)} imports {forbidden}"
    attention = (DIAL_DEV / "attention.py").read_text(encoding="utf-8")
    assert "client.post(" not in attention
