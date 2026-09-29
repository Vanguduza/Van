"""van-private-core trust zone (owner decision 2026-09-29 §3).

The private plane hosts the Owner Cognitive Model, owner_model_revision, the
correction/invalidation outbox, owner-private Hindsight, the owner-private OpenViking
projection and the personal-context resolver. It must not host browser automation,
Stagehand, Chromium, Jev browser execution, VATI order execution or broker adapters, and
nothing outside it may reach its stores except through a bounded authenticated API.

These tests read the repository, not a host: `deploy/van-private-core/qualify.sh` is what
checks a real machine, and no such machine exists yet (external provisioning gate).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ZONE_DIR = ROOT / "deploy" / "van-private-core"
TOPOLOGY = ZONE_DIR / "topology.json"
UNIT = ZONE_DIR / "systemd" / "van-private-core.service"
DOC = ROOT / "docs" / "project-state" / "VAN_PRIVATE_CORE_TOPOLOGY_20260929.md"

OWNER_DECISION_RESPONSIBILITIES = {
    "Owner Cognitive Model",
    "owner_model_revision",
    "correction/invalidation outbox",
    "owner-private Hindsight",
    "owner-private OpenViking projection",
    "personal-context resolver",
}

#: What the zone must not host, as the names these things actually go by in this repo.
#: Matched case-insensitively with no letter directly before or after, so "vati" does not
#: match "activation" and "deriv" does not match "derived".
FORBIDDEN_MARKERS = (
    # generic browser automation / Browser Harness / Browser Control Agent
    "van_gateway.browser", "van_gateway.automation", "van_gateway.computer_use",
    "browser_control_agent", "browser-control-agent", "browser_stream_host",
    "van-browser", "harness_service", "browser-harness", "cdp",
    # Stagehand
    "stagehand", "@browserbasehq",
    # Chromium and its drivers
    "chromium", "chrome", "playwright", "puppeteer", "headless_shell",
    # Jev browser execution (Programme B)
    "jev", "dial-jev",
    # VATI order execution and broker adapters
    "vati", "trading/vati", "execution.router", "execution/router", "broker",
    "deriv", "mt5", "metatrader", "mql5", "ctrader", "van-trading",
)

#: In-process consumers of the Owner Model's Python interface that live outside the
#: private-core modules today, inside the van-gateway process. Each is split gate G-PC-3
#: (becomes a client of the private-core API). The list may shrink; it must not grow.
IN_PROCESS_CONSUMERS_PENDING_SPLIT = {
    "backend/van_gateway/understanding/api.py",
    "backend/van_gateway/reasoning/calibration.py",
    "backend/van_gateway/evolution/vaneval.py",
}

#: Zones and packages that must never touch the private plane's stores or modules at all.
NEVER_TOUCH = (
    "trading", "services", "deploy/van-trading-core", "deploy/van-browser-stream",
    "backend/van_gateway/browser", "backend/van_gateway/automation",
    "backend/van_gateway/computer_use", "backend/van_gateway/trading",
)

SOURCE_SUFFIXES = {".py", ".mjs", ".js", ".ts", ".sh", ".sql", ".kt", ".service", ".yml",
                   ".yaml", ".tpl", ".env", ".example", ".ps1", ".mq5"}
SKIP_PARTS = {"node_modules", "__pycache__", ".git", "tests", "test", "build", ".gradle"}

PRIVATE_CORE_MODULE_PREFIXES = (
    "van_gateway.understanding.owner_model",
    "van_gateway.understanding.personal_context",
)


def topology() -> dict:
    return json.loads(TOPOLOGY.read_text(encoding="utf-8"))


def _marker_re(marker: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])" + re.escape(marker) + r"(?![a-z])", re.IGNORECASE)


def forbidden_hits(text: str) -> list[str]:
    return [m for m in FORBIDDEN_MARKERS if _marker_re(m).search(text)]


def source_files(base: Path):
    for path in base.rglob("*"):
        if not path.is_file() or SKIP_PARTS & set(path.relative_to(ROOT).parts):
            continue
        if path.suffix in SOURCE_SUFFIXES or path.name.endswith(".env.example"):
            yield path


def table_access_re(tables) -> re.Pattern[str]:
    names = "|".join(re.escape(t) for t in tables)
    return re.compile(
        r"(?:\b(?:FROM|JOIN|INTO|UPDATE|TABLE(?:\s+IF\s+NOT\s+EXISTS)?|ON)\s+(?:" + names + r")\b)"
        r"|(?:[\"'](?:" + names + r")[\"'])",
        re.IGNORECASE,
    )


# ---------------------------------------------------------------- placement


def test_topology_places_exactly_the_owner_decided_responsibilities():
    t = topology()
    assert t["zone"] == "van-private-core"
    assert {r["name"] for r in t["responsibilities"]} == OWNER_DECISION_RESPONSIBILITIES
    assert t["authority"]["authority_class"] == "OWNER_EXPLICIT"
    assert t["authority"]["signature"].startswith("NONE_CLAIMED")
    for r in t["responsibilities"]:
        for module in r["code_modules"]:
            assert (ROOT / module).is_file(), module
            assert module in t["private_core_modules"], module
        # A responsibility without code must say so, not look implemented.
        if not r["code_modules"]:
            assert r["repository_status"].startswith("PLACEMENT_ONLY"), r["id"]
    for module in t["private_core_modules"]:
        assert (ROOT / module).is_file(), module


def test_outbox_targets_are_the_declared_derived_stores():
    sys.path.insert(0, str(ROOT / "backend"))
    from van_gateway.understanding.owner_model_outbox import OutboxTarget

    declared = {r["outbox_target"] for r in topology()["responsibilities"] if "outbox_target" in r}
    assert declared == {t.value for t in OutboxTarget}


def test_ingress_is_exactly_the_private_core_app_routes():
    sys.path.insert(0, str(ROOT / "backend"))
    from van_gateway.private_core.app import PRIVATE_CORE_ROUTES

    ingress = topology()["ingress"]
    assert [tuple(r) for r in ingress["routes"]] == list(PRIVATE_CORE_ROUTES)
    unit = UNIT.read_text(encoding="utf-8")
    assert ingress["entrypoint"] in unit and "--factory" in unit
    # mutual TLS required, and never a wildcard bind
    assert "--ssl-cert-reqs 2" in unit and "--ssl-ca-certs" in unit
    assert "--host ${VAN_PRIVATE_CORE_BIND}" in unit
    assert re.search(r'ExecStartPre=.*""\|0\.0\.0\.0\|::', unit)
    env = dict(line.split("=", 1) for line in
               (ZONE_DIR / "runtime.env.example").read_text().splitlines()
               if line and not line.startswith("#"))
    assert env["VAN_PRIVATE_CORE_BIND"] not in {"0.0.0.0", "::", "[::]"}
    assert env["VAN_DATABASE_PATH"].startswith("/var/lib/van-private-core/")
    for service in ("HINDSIGHT", "OPENVIKING"):
        assert env[f"VAN_PRIVATE_{service}_BIND"] == "127.0.0.1"
        assert env[f"VAN_PRIVATE_{service}_DIR"].startswith("/var/lib/van-private-core/")


def test_the_private_core_unit_refuses_a_wildcard_bind():
    unit = UNIT.read_text(encoding="utf-8")
    [guard] = [line.split("=", 1)[1] for line in unit.splitlines()
               if line.startswith("ExecStartPre=") and "VAN_PRIVATE_CORE_BIND" in line]
    command = guard.removeprefix("/bin/sh -c ").strip("'")
    for bind, ok in (("", False), ("0.0.0.0", False), ("::", False), ("10.77.0.9", True)):
        r = subprocess.run(["sh", "-c", command], env={"VAN_PRIVATE_CORE_BIND": bind},
                           capture_output=True, text=True)
        assert (r.returncode == 0) is ok, (bind, r.stderr)


def test_nothing_else_deploys_the_private_core_service():
    hits = []
    for path in source_files(ROOT):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("deploy/van-private-core/") or rel.startswith("backend/van_gateway/private_core/"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "van_gateway.private_core" in text or "/var/lib/van-private-core" in text:
            hits.append(rel)
    assert hits == [], f"only van-private-core may run the plane or mount its store: {hits}"


# ---------------------------------------------------------------- must not host


def _zone_files():
    for path in sorted(ZONE_DIR.rglob("*")):
        if path.is_file() and path.name not in {"README.md", "topology.json"}:
            yield path


def test_zone_package_hosts_no_browser_stagehand_chromium_jev_vati_or_broker():
    assert list(_zone_files()), "zone package is empty"
    offences = {}
    for path in _zone_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.name == "qualify.sh":
            # Section 2 names the forbidden workloads in order to detect them on a host.
            head, _, rest = text.partition("# 2. ")
            _, _, tail = rest.partition("# 3. ")
            assert tail, "qualify.sh section markers moved"
            text = head + tail
        hits = forbidden_hits(text)
        if hits:
            offences[path.relative_to(ROOT).as_posix()] = hits
    # topology.json: everything except the must_not_host section, which names them.
    t = topology()
    t.pop("must_not_host")
    hits = forbidden_hits(json.dumps(t))
    if hits:
        offences["deploy/van-private-core/topology.json"] = hits
    assert offences == {}, offences


def test_zone_package_has_no_node_or_browser_runtime():
    names = {p.name for p in ZONE_DIR.rglob("*")}
    assert not names & {"package.json", "package-lock.json", "node_modules"}


def test_private_core_app_import_closure_excludes_forbidden_code():
    probe = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(ROOT / 'backend')!r})\n"
        "import van_gateway.private_core.app as m\n"
        "m.create_private_core_app\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                       cwd=str(ROOT / "backend"),
                       env={"VAN_INTERNAL_CONTROL_SCOPED_TOKENS": "", "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    modules = json.loads(r.stdout)
    bad = [m for m in modules if m.startswith((
        "van_gateway.browser", "van_gateway.automation", "van_gateway.computer_use",
        "van_gateway.trading", "van_gateway.app", "services", "vati", "playwright",
        "stagehand", "patchright", "browser_use",
    )) or "jev" in m.lower()]
    assert bad == [], bad


# ---------------------------------------------------------------- store access


def test_only_private_core_modules_touch_the_protected_tables():
    t = topology()
    allowed = set(t["private_core_modules"]) | set(t["store_definition_and_governance_modules"])
    pattern = table_access_re(t["protected_tables"])
    offenders = {}
    for path in source_files(ROOT):
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed:
            continue
        found = sorted({m.group(0) for m in pattern.finditer(
            path.read_text(encoding="utf-8", errors="ignore"))})
        if found:
            offenders[rel] = found
    assert offenders == {}, (
        "direct access to van-private-core stores outside the plane; use the "
        f"private-core API (or the Owner Model interface, pending split): {offenders}")


def test_in_process_owner_model_consumers_do_not_grow():
    t = topology()
    pattern = re.compile(
        r"van_gateway\.understanding(?:\.(?:owner_model|owner_model_outbox|personal_context"
        r"|personal_context_resolver)\b| import [^\n]*\b(?:owner_model|personal_context))")
    consumers = set()
    for path in source_files(ROOT / "backend" / "van_gateway"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in t["private_core_modules"]:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            consumers.add(rel)
    assert consumers <= IN_PROCESS_CONSUMERS_PENDING_SPLIT, sorted(
        consumers - IN_PROCESS_CONSUMERS_PENDING_SPLIT)


def test_forbidden_zones_never_reach_the_private_plane():
    t = topology()
    tables = table_access_re(t["protected_tables"])
    modules = re.compile(r"van_gateway\.(?:understanding\.(?:owner_model|personal_context)"
                         r"|private_core)|OwnerCognitiveModel|PersonalContextResolver")
    offenders = {}
    for base in NEVER_TOUCH:
        for path in source_files(ROOT / base):
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits = [m.group(0) for m in tables.finditer(text)] + modules.findall(text)
            if hits:
                offenders[path.relative_to(ROOT).as_posix()] = sorted(set(hits))
    assert offenders == {}, offenders


# ---------------------------------------------------------------- record


def test_external_gates_are_documented():
    text = DOC.read_text(encoding="utf-8")
    assert topology()["external_gates"] == DOC.relative_to(ROOT).as_posix()
    for gate in ("G-PC-1", "G-PC-2", "G-PC-3", "G-PC-4", "G-PC-5"):
        assert gate in text, gate
    assert "auth-20260929-owner-van-private-core" in text
    assert "OWNER_EXPLICIT" in text and "No device or cryptographic signature" in text


def test_qualify_script_is_valid_bash():
    subprocess.run(["bash", "-n", str(ZONE_DIR / "qualify.sh")], check=True)


@pytest.mark.parametrize("text,hit", [
    ("ExecStart=node stagehand_service.mjs", "stagehand"),
    ("After=van-browser-chromium.service", "chromium"),
    ("import vati.execution.router", "vati"),
    ("dial-jev propose", "jev"),
    ("feature activation", None),
    ("derived episodes", None),
])
def test_marker_matching_is_not_fooled_by_substrings(text, hit):
    hits = forbidden_hits(text)
    assert (hit in hits) if hit else hits == []
