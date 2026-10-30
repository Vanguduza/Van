# BE-025 candidate: sealed same-task browser continuation

Source implementation and fixture-backed source tests; no native qualification or unit acceptance is issued. The frozen Rev1.18 package and all programme identities remain unchanged.

## Production path

1. A real browser assignment stops at a permitted scope boundary, releases its page lease, and leaves the original task WAITING_FOR_OWNER with an OPEN escalation. Payment/irreversible boundaries remain prohibited.
2. The paired owner device reads `GET /v1/browser/tasks/{task_id}/resume-contract`. The server verifies source-device ownership, current scope, escalation lifetime, and parent mission controls. This GET grants no authority. It returns an OpenAPI ResumeContract, immutable scope digest, and exact approval command.
3. Android submits that exact command through the existing `/v1/commands` flow. Canonical A4 approval, hardware-bound owner ingress and fresh sealed parameters remain required. Advisory decisions, model text, internal-control credentials and the contract GET cannot issue the grant.
4. The local executor creates a bounded, single-use grant, durable source witness and guarded RESUME_AUTHORIZED transition in one SQLite transaction. An independent mission verifier reads the stored grant and original command/execution back. Its success means continuation authority exists; it never means the browser work is finished.
5. The production worker consumer validates that witness, current owner/device, original task/escalation/scope, verified action, expiry and parent controls. Conditional consumption permits one run. The loaded task receives only the approved temporary scope/class; the original task and decision records are preserved. Assignment/step deadlines cannot exceed the grant expiry. The existing lease, network, action-risk, verification and payment boundaries still apply.

Concurrent double consumption spends one grant. Restart before consumption retains it. A failed task transition rolls back both grant and witness. A stale advisory sync cannot overwrite a newly authorized transition. An interrupted run after consumption is refused as OUTCOME_UNKNOWN and requires reconciliation of the existing task; no effect is blindly retried.

## Frontend registry binding

These are additions to existing registry surfaces, not a new UI design or an admitted blueprint amendment:

| Canonical surface | Supplied interaction and information |
| --- | --- |
| VNX-S-WORK-05 Task Detail | Show original task state, current and requested scope, reason/evidence, expiry, and continuation availability from the contract endpoint. |
| VNX-S-WORK-14 Review Queue | Show that advisory answers and exact action authorization have different effects. |
| VNX-S-WORK-15 Approval Detail | Review the exact task/escalation/scope digest and use the existing owner A4 challenge/sign/submit flow. |
| VNX-S-WORK-09 Progress Evidence | Show authorization readiness, consumption and actual browser verification separately. Acknowledgment or authorization is not browser completion. |

Use the existing provisioned gateway origin; the handset supplies no new host, credential or service setting. This source pass adds the backend/OpenAPI contract; redesigned Android consumers remain under BG-001 and the existing frontend units.

## Source evidence and remaining acceptance

`backend/tests/test_browser_sealed_resume.py` exercises real authenticated HTTP commands, canonical owner challenges/signatures, app composition, durable state, restart, actual assignment admission and readback. Only browser/provider transport is a controlled fixture. Related lifecycle, scope, capability, descriptor and mission-control checks total 128 passes in the final focused run. The first broad run was invalidated by editing a live registry after its types were imported; it is not final qualification.

Carried acceptance identities are T-BE-025-POS/SEC/REC; none is declared independently accepted by this document. Live browser/native service proof, handset UI/Artemis evidence, full unit acceptance and recovery of an already-uncertain external effect remain separate obligations.
