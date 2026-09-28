#!/usr/bin/env python3
"""OpenMuse→VAN convergence repository certification.

This is a repository proof only. It deliberately does not probe Google, the Browser Stream
Host, the S24, Hermes, or the computer-worker host. Those are external qualification rows
in the canonical matrix and runtime qualification matrix.

The harness exists to stop two opposite truth failures:
* code landed while the matrix still says PLANNED; and
* a matrix says COMPLETE while a required file/invariant/test disappeared.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
from typing import Any

MATRIX = Path("docs/project-state/OPENMUSE_VAN_CONVERGENCE_MATRIX_REV_1.json")
PROVENANCE = Path("docs/project-state/OPENMUSE_VAN_UPSTREAM_PROVENANCE_REV_1.json")
PACK = Path("docs/OPENMUSE_VAN_CONVERGENCE_DEVELOPMENT_PACK_REV_1.md")

UPSTREAM_SHA = "34b15bc80340e582fb8c25573646cfb0bbc5184d"
REQUIRED = {f"OMV-{n:03d}" for n in range(1, 10)}
OPTIONAL = {"OMV-010"}

MARKERS: dict[str, tuple[tuple[str, str], ...]] = {
    "OMV-001": (
        ("backend/van_gateway/documents/service.py", "async def propose_fill("),
        ("backend/van_gateway/documents/pdf.py", "PDF_XFA_UNSUPPORTED"),
        ("backend/tests/test_document_fabric.py", "test_document_fill_proposal_is_source_digest_bound"),
        ("android/app/src/main/java/com/dial/van/command/work/DocumentRoute.kt", "fun DocumentRoute("),
        ("backend/van_gateway/ops/backup.py", "BackupPart.DOCUMENTS"),
    ),
    "OMV-002": (
        ("backend/van_gateway/computer_use/worker.py", "COMPUTER_QUALIFICATION_IMAGE_DRIFT"),
        ("backend/van_gateway/computer_use/lease.py", "COMPUTER_WORKER_LOST_LEASE"),
        ("backend/tests/test_computer_worker.py", "test_not_ready_worker_refuses_before_operation_row_exists"),
        ("deploy/van-computer-worker/qualify.sh", "workspace did not survive container recreation"),
    ),
    "OMV-003": (
        ("backend/van_gateway/goals/service.py", "async def due_watches("),
        ("backend/van_gateway/goals/watch_runner.py", "class WatchRunner"),
        ("backend/tests/test_goals_watches.py", "test_scheduler_runner_reads_public_watch_without_agent_loop"),
        ("backend/van_gateway/app.py", 'ScheduledJob("owner.watches"'),
    ),
    "OMV-004": (
        ("backend/van_gateway/suggestions/service.py", "fresh_owner_prompt"),
        ("backend/van_gateway/runtime_api.py", '@router.post("/suggestions")'),
        ("hermes/mcp/owner_runtime_stdio.mjs", "name: 'suggestion_create'"),
        ("backend/tests/test_suggestions.py", "assert \"execution_id\" not in result"),
        ("backend/tests/test_runtime_hermes_surface.py", "test_suggestion_create_requires_evidence_and_never_executes"),
        ("android/app/src/main/java/com/dial/van/command/work/ConvergenceRoute.kt", "convergenceSuggestionDecision"),
    ),
    "OMV-005": (
        ("backend/van_gateway/artifacts/models.py", "class OwnerArtifact"),
        ("backend/van_gateway/artifacts/service.py", "canonical_source_digest"),
        ("backend/tests/test_owner_artifacts.py", "test_artifact_projection_is_digest_bound_and_queryable"),
        ("android/app/src/main/java/com/dial/van/command/work/ConvergenceRoute.kt", 'SectionHeader("Generated results"'),
    ),
    "OMV-006": (
        ("backend/van_gateway/conversations/service.py", "async def queue_followup("),
        ("backend/van_gateway/conversations/api.py", '"/{thread_id}/followups"'),
        ("backend/tests/test_conversation_store.py", "test_followup_queue_never_executes_by_itself"),
        ("android/app/src/main/java/com/dial/van/command/work/ConversationThreadRoute.kt", "fun ConversationThreadRoute("),
    ),
    "OMV-007": (
        ("backend/van_gateway/google/transport.py", "In-Reply-To:"),
        ("backend/van_gateway/google/transport.py", "gmail_attachment_get"),
        ("backend/van_gateway/google/transport.py", "expected_version"),
        ("backend/tests/test_google_openmuse_depth.py", "test_gmail_reply_draft_binds_threading_headers"),
        ("backend/tests/test_google_openmuse_depth.py", "test_filled_document_output_is_attached_to_reviewed_reply"),
        ("backend/tests/test_extra_apis.py", "test_google_filled_pdf_reply_round_trip_is_action_bound"),
        ("backend/tests/test_extra_apis.py", "expected_raw_sha256"),
        ("backend/tests/test_google_openmuse_depth.py", "test_stale_calendar_version_is_definite_rejection_not_unknown"),
    ),
    "OMV-008": (
        ("services/browser_control_agent/egress_proxy.py", "class ExactIpEgressProxy"),
        ("services/browser_control_agent/agent.py", "validate_public_url_syntax"),
        ("deploy/van-browser-stream/qualify.sh", 'record "egress_refuses_private"'),
        ("services/browser_control_agent/tests/test_egress_proxy.py", "test_resolver_rejects_hostname_if_any_dns_answer_is_private"),
    ),
    "OMV-009": (
        ("backend/tests/test_openmuse_regressions.py", "test_terminal_reviewed_action_never_reverts_to_pending_on_replay"),
        ("backend/tests/test_browser_subagent.py", "BUDGET_EXHAUSTED"),
        ("backend/tests/test_computer_worker.py", "test_stale_worker_cannot_publish_completion"),
        ("backend/tests/test_goals_watches.py", "failure_streak"),
    ),
}


def _read(root: Path, relative: str | Path) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(str(relative))
    return path.read_text(encoding="utf-8")


def evaluate(root: Path, matrix_override: dict[str, Any] | None = None) -> dict[str, Any]:
    issues: list[str] = []
    matrix = matrix_override or json.loads(_read(root, MATRIX))
    provenance = json.loads(_read(root, PROVENANCE))

    upstream = matrix.get("upstream") or {}
    if upstream.get("sha") != UPSTREAM_SHA:
        issues.append("matrix_upstream_sha_drift")
    if upstream.get("license") != "MIT":
        issues.append("matrix_upstream_license_not_mit")
    if provenance.get("upstream_sha") != UPSTREAM_SHA:
        issues.append("provenance_upstream_sha_drift")
    if provenance.get("license") != "MIT":
        issues.append("provenance_license_not_mit")

    packages = matrix.get("packages") or []
    by_id = {str(p.get("id")): p for p in packages}
    if set(by_id) != REQUIRED | OPTIONAL:
        issues.append("package_id_set_mismatch")
    for package_id in sorted(REQUIRED):
        package = by_id.get(package_id)
        if not package:
            continue
        if package.get("repository_state") != "REPOSITORY_COMPLETE":
            issues.append(f"{package_id}:not_repository_complete")
        if package.get("live_state") == "LIVE_CERTIFIED":
            issues.append(f"{package_id}:matrix_may_not_self_promote_live")
        evidence = package.get("evidence") or []
        if not evidence:
            issues.append(f"{package_id}:missing_evidence_list")
        for rel in evidence:
            if not (root / str(rel)).is_file():
                issues.append(f"{package_id}:missing_evidence:{rel}")

    optional = by_id.get("OMV-010") or {}
    if optional.get("required") is not False:
        issues.append("OMV-010:must_remain_optional")
    if optional.get("repository_state") not in {"OPTIONAL_NOT_IMPLEMENTED", "REPOSITORY_COMPLETE"}:
        issues.append("OMV-010:invalid_optional_state")

    forbidden = set(matrix.get("forbidden") or [])
    expected_forbidden = {
        "peer_openmuse_agent", "copilotkit_intelligence_as_truth", "second_attention_plane",
        "payment_automation", "browser_input_bypass", "memory_authority_replacement",
    }
    if forbidden != expected_forbidden:
        issues.append("forbidden_boundary_set_drift")

    for package_id, markers in MARKERS.items():
        for rel, marker in markers:
            try:
                text = _read(root, rel)
            except FileNotFoundError:
                issues.append(f"{package_id}:marker_file_missing:{rel}")
                continue
            if marker not in text:
                issues.append(f"{package_id}:marker_missing:{rel}:{marker}")

    db = _read(root, "backend/van_gateway/storage/db.py")
    version = re.search(r"SCHEMA_VERSION\s*=\s*(\d+)", db)
    if version is None or int(version.group(1)) < 33:
        issues.append("schema_version_before_33")
    if "33: MIGRATION_33" not in db or "conversation_followups" not in db:
        issues.append("conversation_followup_migration_missing")

    security = _read(root, "docs/SECURITY_POLICY.md")
    if "Hermes profile `van` is the sole agent runtime" not in security:
        issues.append("sole_agent_runtime_invariant_missing")

    computer = _read(root, "backend/van_gateway/computer_use/fabric.py")
    try:
        module = ast.parse(computer)
        operation_type = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "OperationType"
        )
        declared_operations = {
            target.id
            for node in operation_type.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
    except (SyntaxError, StopIteration):
        issues.append("computer_operation_type_enum_unreadable")
        declared_operations = set()
    for forbidden_operation in ("RUN_ARBITRARY", "EXECUTE_SHELL", "EVAL_CODE"):
        if forbidden_operation in declared_operations:
            issues.append(f"computer_forbidden_operation:{forbidden_operation}")

    browser_unit = _read(root, "deploy/van-browser-stream/systemd/van-browser-chromium.service")
    for flag in (
        "--proxy-server=http://127.0.0.1:${VAN_BROWSER_EGRESS_PORT}",
        "--proxy-bypass-list=<-loopback>",
        "--disable-quic",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ):
        if flag not in browser_unit:
            issues.append(f"browser_proxy_flag_missing:{flag}")

    pack = _read(root, PACK)
    if "OpenMuse-derived code may sit below VAN authority, never above it." not in pack:
        issues.append("pack_subordinate_authority_rule_missing")

    return {
        "schema_version": 1,
        "kind": "OPENMUSE_VAN_CONVERGENCE_REPOSITORY_CERTIFICATION",
        "upstream_sha": UPSTREAM_SHA,
        "required_packages": sorted(REQUIRED),
        "optional_packages": sorted(OPTIONAL),
        "repository_complete": not issues,
        "issues": issues,
        "external_live_gates": sorted({
            gate
            for package in packages
            for gate in (package.get("external_gates") or [])
        }),
    }


def _git_head(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    report = evaluate(root)
    report["git_head"] = _git_head(root)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        destination = root / args.output
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if args.check and not report["repository_complete"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
