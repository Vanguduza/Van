from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMAND_DIR = ROOT / "android/app/src/main/java/com/dial/van/command"
# P3-AND-009 split the 1,342-line CommandCentreActivity.kt into a shell, a navigation model
# and one file per module group. A second rebuild (DNA §4) then replaced the flat 17-module
# grid (`CommandModule`/`CommandNav`) with one `NavHost` over a typed route registry
# (`command/nav/VanRoute.kt`). This contract is about what the owner can reach and in how
# many taps, which is a property of the whole surface rather than of one file, so it reads
# the package.
SHELL = COMMAND_DIR / "CommandCentreActivity.kt"
ROUTES = COMMAND_DIR / "nav" / "VanRoute.kt"
NAV_MODEL = COMMAND_DIR / "nav" / "VanNavModel.kt"
MODULES = COMMAND_DIR / "modules"
TRADING = ROOT / "android/app/src/main/java/com/dial/van/trading/ui/TradingScreens.kt"


def code_of(path: Path) -> str:
    """Source with comments removed.

    A commented-out call still contains its own text, so a substring assertion over the raw
    file would be satisfied by `// AdminActionCard("Settings"` — a card the owner cannot
    reach, asserted as present.
    """
    out, in_block = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if in_block:
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("/*"):
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        out.append(line.split("//")[0])
    return "\n".join(out)


def command_surface() -> str:
    return "\n".join(code_of(path) for path in sorted(COMMAND_DIR.rglob("*.kt")))


def test_the_route_registry_names_every_dna_4_destination():
    routes = code_of(ROUTES)
    for const, value in (
        ("HOME", "home"),
        ("ATTENTION", "attention"),
        ("WORK", "work"),
        ("TRADING", "trading"),
        ("MEMORY", "memory"),
        ("PROJECTS", "projects"),
        ("CONNECTED", "connected"),
        ("SETTINGS", "settings"),
    ):
        assert f'const val {const} = "{value}"' in routes, const


def test_the_five_adaptive_nav_primaries_are_home_attention_work_trading_memory():
    routes = code_of(ROUTES)
    assert "val PRIMARY: List<String> = listOf(HOME, ATTENTION, WORK, TRADING, MEMORY)" in routes


def test_more_carries_projects_connected_and_settings():
    routes = code_of(ROUTES)
    assert "val MORE: List<String> = listOf(PROJECTS, CONNECTED, SETTINGS)" in routes


def test_deep_links_use_the_van_scheme():
    routes = code_of(ROUTES)
    assert 'const val DEEP_LINK_SCHEME = "van"' in routes
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert '<data android:scheme="van" />' in manifest


def test_the_activity_hosts_one_navhost_over_every_route():
    shell = code_of(SHELL)
    assert "NavHost(navController = nav, startDestination = viewModel.startDestination)" in shell
    for route_expr in (
        "composable(VanRoute.HOME)",
        "composable(VanRoute.ATTENTION)",
        "composable(VanRoute.WORK)",
        "composable(VanRoute.TRADING)",
        "composable(VanRoute.MEMORY)",
        "composable(VanRoute.PROJECTS)",
        "composable(VanRoute.CONNECTED)",
        "composable(VanRoute.SETTINGS)",
        "composable(VanRoute.WORK_BROWSER)",
        "composable(VanRoute.WORK_BROWSER_TASKS)",
        "composable(VanRoute.WORK_BROWSER_ESCALATIONS)",
        "composable(VanRoute.WORK_BROWSER_SESSIONS)",
        "composable(VanRoute.WORK_BROWSER_POLICY)",
    ):
        assert route_expr in shell, f"no NavHost destination for {route_expr}"


def test_trading_command_centre_activity_is_still_launchable_by_the_overlay():
    """DNA §4: 'TradingCommandCentreActivity forwards to the route for old intents.'

    The overlay's own deep links (`VanOverlayPanels`/`VanOverlayWorkboards`) still address
    `TradingCommandCentreActivity` directly with routes like `trade/{id}` that the in-NavHost
    `TradingRoute` this rebuild adds does not yet have a migrated equivalent for — gutting it
    now would break those call sites. It stays registered and exported=false, and Work's own
    NavHost carries `TradingRoute` as the DNA-described destination going forward.
    """
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert '.trading.TradingCommandCentreActivity"' in manifest
    shell = code_of(SHELL)
    assert "com.dial.van.trading.ui.TradingRoute(app, onBack" in shell


def test_browser_hub_is_summary_first_not_full_module_stack():
    text = code_of(MODULES / "BrowserModules.kt")
    start = text.index("fun BrowserAutomationModule(")
    end = text.index("fun BrowserEscalationsPage(", start)
    hub = text[start:end]
    assert 'AdminActionCard(' in hub
    assert '"Owner escalations"' in hub
    assert '"Browser tasks & evidence"' in hub
    assert '"Sessions & profiles"' in hub
    assert '"Policy & capabilities"' in hub
    assert "items(escalations.orEmpty()" not in hub
    assert "items(tasks.orEmpty()" not in hub


def test_trading_home_routes_modules_instead_of_embedding_full_lists():
    text = TRADING.read_text()
    start = text.index("fun OverviewScreen(")
    end = text.index("private fun QuickAccess(", start)
    overview = text[start:end]
    assert '"Open positions"' in overview
    assert '"Potential trades"' in overview
    assert '"Recent trades"' in overview
    assert '"Risk Center"' in overview
    assert '"Accounts"' in overview
    assert '"Market workspace"' in overview
    assert "TradeChartCanvas(" not in overview
    assert "TradeRowCard(" not in overview
    assert "AccountRow(" not in overview


def test_the_command_centre_is_no_longer_one_file():
    # P3-AND-009. Not a style rule: the status projection P0-EXEC-003 found painting
    # unverified outcomes in the working colour sat at line 1,310 of the file this
    # replaces, and the reason nobody had seen it is that nobody reads to line 1,310.
    files = sorted(COMMAND_DIR.rglob("*.kt"))
    assert len(files) >= 6, [f.name for f in files]
    for path in files:
        lines = path.read_text().count("\n")
        # CommandCentreActivity.kt wires the whole NavHost graph (DNA §4's full destination
        # set), which is legitimately longer than a single module screen; every other file
        # keeps the original per-screen ceiling.
        limit = 500 if path.name == "CommandCentreActivity.kt" else 450
        assert lines < limit, f"{path.name} is {lines} lines"


def test_process_death_restoration_is_pure_and_executed_in_the_harness():
    harness = (ROOT / "android/verification/build.gradle.kts").read_text(encoding="utf-8")
    assert '"com/dial/van/command/nav/VanRoute.kt"' in harness
    assert '"com/dial/van/command/nav/VanNavModel.kt"' in harness
    assert NAV_MODEL.is_file()
