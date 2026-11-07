# Muse W02 follow-up — BE-006 retained-incarnation and native-scope history pagination

**Ownership:** Muse-only implementation packet on `muse/van-rev118-backend-20261107`. Cursor is assigned public gateway/OBL004 CI reproduction; do not edit that domain.  
**Starting source:** PR #105 `e6f7e9098012140ac4033263ce8348221fe90607`; this branch additionally contains handoff documentation only.  
**Full programme instructions:** [FULL_CONTINUATION_PLAN.md](FULL_CONTINUATION_PLAN.md) and [EXECUTION_MATRIX.json](EXECUTION_MATRIX.json). Read both directly from this branch before authoring code. Preserve all original 131 units and canonical original tests.

## Mandatory environment repair
1. Establish a **real local Git working checkout** in Muse's own environment, NOT `/home/ubuntu` on another VM. Clone `https://github.com/Vanguduza/Van.git` with authorized GitHub connector/credential or a permissioned clone mechanism, checkout `muse/van-rev118-backend-20261107`, confirm `git status --short --branch` and exact HEAD, read the two handoff files from this branch. Do not assume the source exists merely because GitHub search listed it.
2. Establish a **real focused test runner** with required dependencies in an isolated environment and record pre-edit baseline outcomes/versions and `git diff --check`. Use minimal resources. Do not run native providers, credentials, or money actions.
3. Inspect `trading/vati/accounts/registry.py`, `trading/vati/accounts/resource_version.py`, `trading/vati/accounts/lifecycle.py`, `trading/vati/accounts/restrictions.py`, `trading/tests/test_account_restrictions.py`, account cash/identity original-operation consumers, and exact BE-006 contracts/receipts in `docs/rebuild/rev118/backend/` and `docs/rebuild/rev118/receipts/`. Identify the true owner, caller, store, recovery and consumer; do not rewrite a parallel ledger.

## Implement one bounded dependency-ready source packet
Expose a **source/fixture-level, read-only** paginated view of retained, historical, superseded account-incarnation/restriction or lifecycle facts, respecting the original BE-006 semantics and schema; preserve original positive business operations. The source's current `AccountRegistry` stores `_restriction_history` / `_lifecycle_history`, versioned registry state and immutable original restriction identifiers. Use whichever history is canonical after inspection, and document exact names.

Required pathways:
- **Positive:** deterministic page and opaque continuation cursor over matching account alias, native venue/contract scope and retained incarnation; no duplicate/skipped history under fixed snapshot; empty history => empty page and no next cursor.
- **Refusal:** malformed/foreign cursor, wrong account/venue/original ID, nonpositive or oversized page limit, missing/recycled incarnation, revoked current owner when the consumer requires it; explicit stable typed HOLD/refusal rather than error-swallowing.
- **Unknown/stale:** no inferred financial effect; stale or source-revision-mismatched cursor must be refused or reconciled using original source, never silently mix snapshots. An interrupted read must be replayable from the last returned token without duplicate effects.
- **Restart:** cold re-open of registry persists byte-exact original IDs, digest/order and deterministic cursor semantics; source history is data only, never a live account mandate.
- **Concurrency:** multiple readers of same history are deterministic; concurrent append/restriction renewal cannot mutate previously returned pages; demonstrate actual tests (and genuine PG tests only if the chosen path uses PG).
- **Security:** no secret fields in public view, no cross-account cursor reuse, no new entries/trades/mandates, no changing current account balance. No live provider operations.

Preserve prior tests, add adversarial tests for all above. Run focused and affected suites. Capture exact executed command, tool versions, counts/exit, failures/skips; independent reviewer must inspect exact source/test diff. If this candidate cannot be implemented in the actual environment, state precise missing capability, do not claim a patch, and perform an independent available packet only after verifying no Cursor overlap.

## Completion boundary
Packet can be labeled SOURCE_TESTED with exact real proof only. Whole BE-006, native financial custody, Project Truth, DDS read key, Zuul, BQ/BG-001, Android/S24, and production remain OPEN. No push/merge to protected main, no live trading or payments, no unqualified signing. Publish source changes to the **Muse-owned branch only if current genuine repository lease and normal hooks permit**; otherwise keep immutable patch artifact and report source hashes. Never modify Cursor's W02 two files unless original contract demands and ownership is independently reconciled. Return a concrete diff and tests, not another broad review.
