from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMAND_DIR = ROOT / "android/app/src/main/java/com/dial/van/command"
# P3-AND-009 split the 1,342-line CommandCentreActivity.kt into a shell, a navigation
# model and one file per module group. This contract is about what the owner can reach
# and in how many taps, which is a property of the whole surface rather than of one file,
# so it reads the package.
SHELL = COMMAND_DIR / "CommandCentreActivity.kt"
NAV = COMMAND_DIR / "CommandCentreNav.kt"
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


def test_command_centre_uses_compact_primary_tabs_and_dashboard_drilldowns():
    text = command_surface()
    assert "horizontalScroll" not in text
    assert "rememberScrollState" not in text
    # The primary tab list moved out of the Activity and into CommandNav, where it is
    # executed by android/verification rather than only inspected here.
    assert "val PRIMARY: List<CommandModule> = listOf(" in code_of(NAV)
    assert "CommandNav.PRIMARY.forEach" in code_of(SHELL)
    for module in ("OVERVIEW", "CHAT", "TASKS", "ACTIVITY"):
        assert f"CommandModule.{module}" in code_of(NAV)
    for detail in (
        "BROWSER_TASKS",
        "BROWSER_ESCALATIONS",
        "BROWSER_SESSIONS",
        "BROWSER_POLICY",
    ):
        assert f"CommandModule.{detail}" in text
    assert 'AdminActionCard("Connections"' in text
    assert 'AdminActionCard("Settings"' in text
    # P2-UX-001 renamed this header out of VAN's vocabulary and into the owner's.
    assert 'DashboardPageHeader("Things VAN is waiting on you for"' in text
    assert 'DashboardPageHeader("Browser tasks & evidence"' in text
    assert 'DashboardPageHeader("Sessions & profiles"' in text
    assert 'DashboardPageHeader("Policy & capabilities"' in text


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
        assert lines < 450, f"{path.name} is {lines} lines"
