# Scoped Muse security source reconciliation

Imported security source: 4cac338e6d2069b9eb61014d39541ea1387acbb5.

This consolidation preserves the 33-file gVisor, namespace, WireGuard,
proxy, bounded-state and sandbox-supervisor security package. Literal newline
sequences outside Python strings in sandbox/supervisor.py were repaired and
the actual Python source now parses.

The old branch's separate TypeSafe Jev worker, parallel Jev egress service,
Hermes gateway SSH transport, runtime activation and bootstrap defaults were
not imported. Canonical browser lease fences, network-effect guards and the
single DDS Jev integration retain authority.

Status: SOURCE_ONLY; NOT_DEPLOYED; CURRENT_CANONICAL_BROWSER_HANDOFF_UNBOUND.
The historical installer is retained for source review. It is not invoked by
the canonical bootstrap and does not establish an admitted CDP handoff.
Current Harness/Stagehand integration must preserve the existing profile,
lease, domain, network-effect, lifecycle and privacy controls before any
runtime activation. Local source tests do not establish a working regional
exit, Meta eligibility, model availability or live sandbox qualification.

This optional component's pending runtime admission does not block the
Android build or the other VAN source tests. No live network, Docker,
WireGuard, service, owner database or signing input was changed.
