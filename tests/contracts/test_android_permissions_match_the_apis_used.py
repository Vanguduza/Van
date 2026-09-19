"""P1-AND-014 — an Android API that needs a permission, called without declaring it.

`VanApplication.startConnectivityMonitor` registers a `ConnectivityManager` network
callback and the manifest did not declare `ACCESS_NETWORK_STATE`. Lint calls this an error
because the call throws at runtime — and here the call was wrapped in a bare
`runCatching { }`, so it did not throw anything anyone would see. It failed silently, which
means the offline queue's replay-on-connectivity-recovery (the whole of P3-AND-006) never
fired, and nothing anywhere said so.

`:app:lintDebug` catches this and now runs on the branch. This is the cheaper half, and it
is deliberately about the *family* rather than the one call: a permission-gated API used
without its manifest entry is a class of defect, and the class is what a guard should cover.

It is a static guardrail, not a substitute for lint. `VanApplication` cannot be constructed
without Android, so nothing here executes the production path.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main"
MANIFEST = APP / "AndroidManifest.xml"

#: Permission-gated APIs the app uses, and what each requires.
#:
#: Deliberately a small table of calls actually present rather than a copy of the platform:
#: an entry for an API the app does not call would guard nothing, and one for an API it does
#: call is worth having. Each key is matched against the source with word boundaries.
PERMISSION_FOR_API: dict[str, str] = {
    "registerNetworkCallback": "android.permission.ACCESS_NETWORK_STATE",
    "getActiveNetwork": "android.permission.ACCESS_NETWORK_STATE",
    "getNetworkCapabilities": "android.permission.ACCESS_NETWORK_STATE",
    "AudioRecord": "android.permission.RECORD_AUDIO",
    "startForegroundService": "android.permission.FOREGROUND_SERVICE",
    "BiometricPrompt": "android.permission.USE_BIOMETRIC",
}


def _declared_permissions() -> set[str]:
    return set(re.findall(r'uses-permission android:name="([^"]+)"', MANIFEST.read_text()))


def _sources() -> dict[Path, str]:
    out = {}
    for path in sorted(APP.rglob("*.kt")):
        source = path.read_text(encoding="utf-8")
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        out[path] = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
    return out


def test_every_permission_gated_api_the_app_calls_is_declared():
    declared = _declared_permissions()
    sources = _sources()
    missing: list[str] = []
    for api, permission in PERMISSION_FOR_API.items():
        callers = [
            path.relative_to(APP)
            for path, text in sources.items()
            if re.search(rf"\b{re.escape(api)}\b", text)
        ]
        if callers and permission not in declared:
            missing.append(f"{api} is called in {callers[0]} and needs {permission}")
    assert missing == [], "\n".join(missing)


def test_access_network_state_is_declared():
    """Named on its own because it is the one that was missing, and because its absence is
    silent rather than loud: the queue simply never drains."""
    assert "android.permission.ACCESS_NETWORK_STATE" in _declared_permissions()


def test_the_connectivity_registration_reports_its_own_failure():
    """A bare `runCatching { }` around the registration is what made this invisible.

    The degraded registry exists so VAN says which parts of itself are not working. A
    capability that quietly does not exist is worse than one that fails loudly, and this is
    the call where the difference was the entire finding.
    """
    source = _sources()[APP / "java/com/dial/van/VanApplication.kt"]
    monitor = source[source.index("private fun startConnectivityMonitor"):]
    monitor = monitor[: monitor.index("\n    fun ")] if "\n    fun " in monitor else monitor
    # All three, because any one alone is satisfiable without the others. Asserting only
    # the two uses let a mutation that dropped the binding pass: `registered.isFailure`
    # was still in the source, referring to nothing. The compiler would have caught that
    # one, which is the point — a static check must not depend on the compiler to make it
    # honest, or it is measuring the wrong thing.
    assert "val registered = runCatching {" in monitor, "the result is not bound at all"
    assert "registered.isFailure" in monitor, "the registration result is discarded again"
    assert "markBroken" in monitor, "a failed registration is not reported anywhere"


def test_the_table_only_names_permissions_the_manifest_could_declare():
    """A typo in a permission name would make this test pass by guarding nothing."""
    for permission in set(PERMISSION_FOR_API.values()):
        assert permission.startswith("android.permission."), permission


def test_lint_runs_in_ci_because_this_check_is_only_the_cheap_half():
    """The authority for this class of defect is lint, which knows the whole platform."""
    workflow = (ROOT / ".github" / "workflows" / "van-ci.yml").read_text(encoding="utf-8")
    assert ":app:lintDebug" in workflow
