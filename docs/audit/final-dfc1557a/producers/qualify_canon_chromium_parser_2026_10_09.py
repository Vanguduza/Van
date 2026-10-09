"""Bounded, non-network Chromium URL parity for the three actual shared parser blocks."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path("/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09")
CHROMIUM = Path("/workspace/.onboarding/playwright/chromium-1243/chrome-linux64/chrome")
OUTPUT = Path("/workspace/van-audit/canon-chromium-parser-real-browser-2026-10-09.json")
FILES = {
    "gateway": "backend/van_gateway/browser/task_scope.py",
    "harness": "deploy/van-browser-core/browser/harness_service.py",
    "egress_proxy": "deploy/van-browser-core/browser/egress_proxy.py",
}
BEGIN = "# --- VAN shared URL scope rule: begin"
END = "# --- VAN shared URL scope rule: end ---"
FIXTURE = ROOT / "backend/tests/fixtures/task_scope/url_vectors.v1.json"
BOUNDARIES = [
    ("/docs/a.b", "/docs/a%2Eb", "TASK_SCOPE_PAGE_PATH_OUTSIDE"),
    ("/docs/a%2Eb", "/docs/a%2Eb", None),
    ("/docs/a%2Eb", "/docs/a.b", "TASK_SCOPE_PAGE_PATH_OUTSIDE"),
    ("/docs/a%2Eb", "/docs/a%2Eb/next", None),
    ("/docs/a%2Eb", "/docs/a%2Ebc", "TASK_SCOPE_PAGE_PATH_OUTSIDE"),
    ("/docs/a%2eb", "/docs/a%2Eb", "TASK_SCOPE_PAGE_PATH_OUTSIDE"),
    ("/docs/", "/docs/%2e%2e%2fcheckout", "TASK_SCOPE_PAGE_PATH_AMBIGUOUS"),
    ("/docs/", "/docs/%2e%2e/checkout", "TASK_SCOPE_PAGE_PATH_OUTSIDE"),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_blocks() -> dict[str, str]:
    result = {}
    for side, relative in FILES.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert text.count(BEGIN) == text.count(END) == 1
        result[side] = text[text.index(BEGIN):text.index(END) + len(END)]
    assert len(set(result.values())) == 1
    return result


def main() -> None:
    blocks = read_blocks()
    fixture_bytes = FIXTURE.read_bytes()
    vectors = json.loads(fixture_bytes)
    modules = {}
    for side, block in blocks.items():
        namespace = {}
        exec(compile(block, str(ROOT / FILES[side]), "exec"), namespace)
        modules[side] = namespace
    observations = []
    boundary_observations = []
    parse_js = """([i,b]) => {
        const u = b === null ? new URL(i) : new URL(i,b);
        return {origin: u.protocol + '//' + u.hostname.replace(/\\.$/, '') +
          (u.port ? ':' + u.port : ''), path: u.pathname};
    }"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(CHROMIUM), args=["--no-sandbox"])
        chromium_version = browser.version
        page = browser.new_page()
        for index, vector in enumerate(vectors["vectors"]):
            parsed_by_side = {}
            violation_by_side = {}
            for side, module in modules.items():
                parsed = module["_vs_parse"](vector["input"], vector["base"])
                actual = None if parsed is None else {"origin": module["_vs_origin"](parsed), "path": parsed[3]}
                assert actual == vector["parsed"], (side, index, actual, vector)
                parsed_by_side[side] = actual
                violation = module["_vs_scope_violation"](vectors["scope_entries"], vector["input"], "PAGE", vector["base"])
                assert violation == vector["violation_docs_scope"], (side, index, violation, vector)
                violation_by_side[side] = violation
            chromium = None
            if vector["parsed"] is not None:
                chromium = page.evaluate(parse_js, [vector["input"], vector["base"]])
                assert chromium == vector["parsed"], (index, chromium, vector)
            observations.append({"index": index, "input": vector["input"], "base": vector["base"],
                                 "chromium_actual": chromium, "parsed_by_side": parsed_by_side,
                                 "violation_by_side": violation_by_side})
        origin = "https://docs.example.com"
        for prefix, path, expected in BOUNDARIES:
            chromium = page.evaluate(parse_js, [origin + path, None])
            sides = {}
            for side, module in modules.items():
                parsed = module["_vs_parse"](origin + path)
                actual = {"origin": module["_vs_origin"](parsed), "path": parsed[3]}
                assert actual == chromium, (side, path, actual, chromium)
                violation = module["_vs_scope_violation"]([{"origin": origin, "path_prefix": prefix}], origin + path)
                assert violation == expected, (side, prefix, path, violation, expected)
                sides[side] = {"parsed": actual, "violation": violation}
            boundary_observations.append({"prefix": prefix, "input": origin + path, "expected_violation": expected,
                                          "chromium_actual": chromium, "sides": sides})
        browser.close()
    assert read_blocks() == blocks
    assert FIXTURE.read_bytes() == fixture_bytes
    report = {
        "schema": "van.audit.chromium_parser_parity.v1",
        "result": "PASS",
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_head_is_qualified_commit": False,
        "scope": "Uncommitted bounded parser candidate; shared blocks extracted from actual three runtime files.",
        "chromium_version": chromium_version,
        "chromium_executable_sha256": digest(CHROMIUM.read_bytes()),
        "shared_blocks": {side: {"file": path, "sha256": digest(blocks[side].encode())} for side, path in FILES.items()},
        "blocks_byte_identical": True,
        "blocks_and_fixture_unchanged_during_check": True,
        "fixture_sha256": digest(fixture_bytes),
        "fixture_vector_count": len(observations),
        "actual_chromium_fixture_parse_count": sum(row["chromium_actual"] is not None for row in observations),
        "exact_prefix_boundary_count": len(boundary_observations),
        "runtime_sides": len(modules),
        "host_handset_calls": 0,
        "browser_network_navigation_calls": 0,
        "vector_observations": observations,
        "boundary_observations": boundary_observations,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("result", "chromium_version", "fixture_vector_count",
                                                  "actual_chromium_fixture_parse_count", "exact_prefix_boundary_count",
                                                  "runtime_sides")}))
    print(json.dumps({"receipt": str(OUTPUT), "sha256": digest(OUTPUT.read_bytes())}))


if __name__ == "__main__":
    main()
