from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMAND = ROOT / "android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt"
TRADING = ROOT / "android/app/src/main/java/com/dial/van/trading/ui/TradingScreens.kt"


def test_command_centre_uses_compact_primary_tabs_and_dashboard_drilldowns():
    text = COMMAND.read_text()
    assert "horizontalScroll" not in text
    assert "rememberScrollState" not in text
    assert "val primaryModules = listOf(" in text
    for module in ("OVERVIEW", "CHAT", "TASKS", "ACTIVITY"):
        assert f"CommandModule.{module}" in text
    for detail in (
        "BROWSER_TASKS",
        "BROWSER_ESCALATIONS",
        "BROWSER_SESSIONS",
        "BROWSER_POLICY",
    ):
        assert f"CommandModule.{detail}" in text
    assert 'AdminActionCard("Connections"' in text
    assert 'AdminActionCard("Settings"' in text
    assert 'DashboardPageHeader("Owner escalations"' in text
    assert 'DashboardPageHeader("Browser tasks & evidence"' in text
    assert 'DashboardPageHeader("Sessions & profiles"' in text
    assert 'DashboardPageHeader("Policy & capabilities"' in text


def test_browser_hub_is_summary_first_not_full_module_stack():
    text = COMMAND.read_text()
    start = text.index("private fun BrowserAutomationModule(")
    end = text.index("private fun BrowserEscalationsPage(", start)
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
