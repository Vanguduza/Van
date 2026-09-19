"""The overlay is a service with a window, not a service with an app inside it.

P3-AND-009 and Rev 3.0 s41. `FloatingOverlayService.kt` was 1,096 lines and was, at once, a
foreground service, a WindowManager client, a drag controller and the whole Compose tree.
s41 says the service is responsible for window and service lifecycle, not for all domain
state, and this file is what stops that sentence being aspirational.

None of these are style rules. The drag geometry could not be executed anywhere because it
lived in a file that imports `WindowManager`; the panels could not be named by anything
because they were private members; and nobody found any of it because nobody reads to line
900.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "android/app/src/main/java/com/dial/van/overlay"
SERVICE = OVERLAY / "FloatingOverlayService.kt"
CONTROLLER = OVERLAY / "VanOverlayController.kt"
SURFACE = OVERLAY / "VanOverlaySurface.kt"
DOCKING = OVERLAY / "EdgeDocking.kt"

# Every file in the package, so a panel cannot be moved back into the service by growing a
# different file instead.
MAX_LINES = 450


def test_no_overlay_file_is_a_god_file():
    for path in sorted(OVERLAY.glob("*.kt")):
        lines = path.read_text().count("\n")
        assert lines < MAX_LINES, f"{path.name} is {lines} lines"


def code_of(path: Path) -> str:
    """Source with comments dropped.

    A comment explaining why a coupling is gone must not read as the coupling.
    """
    out = []
    in_block = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("/*"):
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        out.append(line.split("//")[0])
    return "\n".join(out)


def test_the_service_owns_the_window_and_nothing_draws_in_it():
    text = code_of(SERVICE)
    # The service keeps what a service with a window is for.
    for owned in ("WindowManager", "startForeground", "lifecycleRegistry", "layoutParams"):
        assert owned in text, owned
    # And stops being a Compose tree. `VanGlassSurface` and `VanEmbodiment` are how VAN is
    # drawn; a service that references them is a service that has grown a UI again.
    for drawn in ("VanGlassSurface", "VanEmbodiment", "LazyColumn", "VanPresentation"):
        assert drawn not in text, f"the service draws again: {drawn}"


def test_the_surface_cannot_reach_around_its_parameters():
    # The panels used to size themselves from `resources.displayMetrics` and call
    # `startActivity` on the service. Both are the coupling that made them untestable.
    for path in (SURFACE, OVERLAY / "VanOverlayWorkboards.kt", OVERLAY / "VanOverlayPanels.kt"):
        code = code_of(path)
        for reach in ("displayMetrics", "startActivity(", "this@FloatingOverlayService"):
            assert reach not in code, f"{path.name} reaches for {reach}"


def test_the_geometry_lives_where_it_can_be_executed():
    # EdgeDocking was at the bottom of OverlayStateStore.kt, under a SharedPreferences
    # class, so the JVM harness could not compile it and none of this arithmetic ran.
    for path in (CONTROLLER, DOCKING):
        text = path.read_text()
        assert "import android." not in text, f"{path.name} imports Android and stops being executable"
        assert "import androidx." not in text, f"{path.name} imports androidx and stops being executable"

    harness = (ROOT / "android/verification/build.gradle.kts").read_text()
    for path in (CONTROLLER, DOCKING):
        assert f'"com/dial/van/overlay/{path.name}"' in harness, f"{path.name} is not in the harness"
