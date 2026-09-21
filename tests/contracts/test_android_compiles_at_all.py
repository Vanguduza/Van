"""P0-AND-012 — the Android app did not compile, and nothing here could see it.

Four Kotlin errors, on the branch since the Gate 10 split. `CommandCentreViewModel` was
public and exposed the internal `CommandModule` in three signatures, and
`VanGatewayClient.tradingAccountAction` called `toByteArray` on a `JsonObject` that
`AccountOnboarding.requestBody` returns — so the trading account-action path had never
compiled either.

Nothing in this repository could detect it. The Android Gradle Plugin cannot be fetched in
the development container, `android/verification` compiles only the pure decision files
(neither of these qualifies: one needs `SavedStateHandle`, the other
`android.content.Context`), and CI had never run on this branch. The first CI run that ever
reached the Android job found it in three minutes.

The real guard is that CI now runs on claude/** and compiles the app. These tests are the
cheaper half: the visibility error is statically checkable, so it is caught before a push
rather than three minutes into a runner. They are architectural guardrails and they do not
replace the build — a compiler is the only thing that can say the app compiles.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main"

#: Kotlin keywords that may precede a declaration and are not part of its visibility.
_MODIFIERS = r"(?:override\s+|open\s+|abstract\s+|final\s+|suspend\s+|inline\s+|data\s+|sealed\s+|value\s+|annotation\s+|companion\s+|lateinit\s+|const\s+)*"


def _kotlin_files() -> list[Path]:
    return sorted(APP.rglob("*.kt"))


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//", 1)[0] for line in source.splitlines())


def _internal_types() -> dict[str, Path]:
    """Every type declared `internal`, and where."""
    found: dict[str, Path] = {}
    pattern = re.compile(
        rf"^internal\s+{_MODIFIERS}(?:class|interface|object|enum\s+class)\s+(\w+)", re.M
    )
    for path in _kotlin_files():
        for match in pattern.finditer(_strip_comments(path.read_text(encoding="utf-8"))):
            found[match.group(1)] = path
    return found


_DECLARES = r"(?:val|var|fun|class|interface|object|enum\s+class)\b"
_TYPE_DECL = rf"^(?:private\s+|internal\s+|public\s+)?{_MODIFIERS}(?:class|interface|object|enum\s+class)\b"
_FUN_DECL = rf"^(?:private\s+|internal\s+|public\s+)?{_MODIFIERS}fun\b"


def _public_declarations(source: str) -> list[str]:
    """Every declaration whose effective visibility is public.

    Three things have to be right, and the first version of this check got two of them
    wrong — it passed while the app did not compile.

    The enclosing *visibility* matters: a member of an `internal` type is internal whatever
    its own modifier says.

    The enclosing *kind* matters just as much: everything inside a top-level `fun` is a
    local, not API, and flagging those produced false positives on the composable that
    holds `val model: CommandCentreViewModel`.

    And members are indented, so looking only at column zero misses the case this exists
    for: `val selected: StateFlow<CommandModule>` is public, indented, and is exactly what
    the compiler rejected.
    """
    out: list[str] = []
    enclosing_is_public = True
    enclosing_is_a_type = False
    depth = 0
    for raw in _strip_comments(source).splitlines():
        line = raw
        if not line.strip():
            depth += line.count("{") - line.count("}")
            continue
        own_visibility = re.match(r"^\s*(private|internal|protected)\b", line)

        if depth == 0:
            if re.match(_TYPE_DECL, line):
                enclosing_is_a_type = True
                enclosing_is_public = own_visibility is None
            elif re.match(_FUN_DECL, line) or re.match(rf"^{_MODIFIERS}(?:val|var)\b", line):
                enclosing_is_a_type = False
                enclosing_is_public = own_visibility is None

        # Depth is what separates a member from a local. A type body is depth 1, so its
        # members are API; anything deeper is inside a function body and is not. Without
        # this, `val initial = CommandModule.fromId(...)` inside a method of a public
        # Activity reads as a public property, which it is not.
        is_member = depth <= 1 and (depth == 0 or enclosing_is_a_type)

        if not own_visibility and is_member and re.search(
            rf"^\s*{_MODIFIERS}{_DECLARES}", line
        ) and (depth == 0 or enclosing_is_public):
            out.append(line)

        depth += line.count("{") - line.count("}")
    return out


def test_no_public_declaration_exposes_an_internal_type():
    """The error that kept the app from compiling, as a check that runs in a second.

    Kotlin rejects a public signature naming an internal type, and it is an easy mistake to
    make when a file is split: `CommandModule` became internal in the Gate 10 refactor and
    the view model that names it did not.
    """
    internal = _internal_types()
    assert internal, "no internal types found; the scan is not looking at the app"

    offences: list[str] = []
    for path in _kotlin_files():
        for declaration in _public_declarations(path.read_text(encoding="utf-8")):
            for name, declared_in in internal.items():
                # A file may name its own internal types freely.
                if declared_in == path:
                    continue
                if re.search(rf"\b{re.escape(name)}\b", declaration):
                    offences.append(
                        f"{path.relative_to(APP)}: public `{declaration.strip()[:90]}` "
                        f"exposes internal {name}"
                    )
    assert offences == [], "\n".join(offences)


def test_the_trading_account_body_is_serialised_before_it_is_written():
    """The second error, pinned at the call site.

    `AccountOnboarding.requestBody` returns a JsonObject. The client wrote
    `body.toByteArray(...)`, which does not exist on one — so every build failed here, and
    the fix is `toString()` rather than changing what requestBody returns.
    """
    client = _strip_comments(
        (APP / "java/com/dial/van/gateway/VanGatewayClient.kt").read_text(encoding="utf-8")
    )
    assert "body.toString().toByteArray(" in client
    assert "body.toByteArray(" not in client


def test_request_body_still_returns_a_json_object():
    """If requestBody ever returns a String, the test above is checking a fiction."""
    onboarding = _strip_comments(
        (APP / "java/com/dial/van/trading/AccountOnboarding.kt").read_text(encoding="utf-8")
    )
    assert re.search(r"fun requestBody\([^)]*\)\s*:\s*JsonObject", onboarding, re.S)


def test_the_verification_harness_does_not_claim_to_compile_these_files():
    """Honesty about what the local harness covers.

    `android/verification` compiles the app's *pure* files on the JVM. Neither file in this
    finding qualifies — one needs SavedStateHandle, the other android.content.Context — so
    the harness passing has never been evidence that the app compiles, and a reader should
    not infer that it was.
    """
    harness = (ROOT / "android" / "verification" / "build.gradle.kts").read_text(
        encoding="utf-8"
    )
    assert "CommandCentreViewModel.kt" not in harness
    assert "VanGatewayClient.kt" not in harness


def test_ci_builds_the_app_on_this_branch():
    """The guard that actually proves the app compiles, and that it runs here.

    These static checks catch one error class cheaply. Only a compiler can say the app
    builds, so the workflow must both run on this branch and assemble the app.
    """
    workflow = (ROOT / ".github" / "workflows" / "van-ci.yml").read_text(encoding="utf-8")
    assert "'claude/**'" in workflow, "CI does not run on the certification branch"
    assert ":app:assembleDebug" in workflow, "CI does not build the app"
