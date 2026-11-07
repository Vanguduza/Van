# BE-006 receipt — retained-incarnation history pagination (Muse, W02)

- **Repository:** `Vanguduza/Van`
- **Branch (only):** `muse/van-rev118-backend-20261107`
- **Base:** PR #105 head `e6f7e9098012140ac4033263ce8348221fe90607`
- **Branch head before this packet:** `a1efe698750183e4e0d9e6683be73b3bea267f4d`
  (`docs(muse): define executable BE-006 source-and-test packet with guarded failure paths`)
- **Packet source:** `docs/muse-handoff/BE006_IMPLEMENTATION_PACKET.md`
  (branch head `a1efe698…`, read from GitHub, not from any VM path)
- **Lease:** `lease_e8d1f977e8ab4dda926f6ee51d7ec3cf` (fencing token 739),
  MUTATING, write paths only; `trading/vati/accounts/restrictions.py` and
  `trading/tests/test_account_restrictions.py` were NOT edited (denied paths).
- **Independent reviewer:** NOT YET ASSIGNED — this packet is
  `NEEDS_INDEPENDENT_REVIEW`. No unit, gate, or release is admitted by it.

## What was implemented

`AccountRegistry.history_page(alias, *, kind="restriction"|"lifecycle", limit=25, cursor=None)`
in `trading/vati/accounts/registry.py` (+138 lines, no other source file changed):

- Read-only paginated view over the registry's already-retained history:
  `_restriction_history` for `kind="restriction"`,
  `_lifecycle_history` for `kind="lifecycle"`.
- Deterministic order `(created_at_unix, restriction_id / operation_id)`
  under one freshly re-read snapshot; a fixed snapshot never duplicates or
  skips a row.
- Opaque cursor binding alias, kind, venue, resource revision, source digest
  (canonical hash of alias/kind/revision/rows), last key, and index, with a
  canonical-hash integrity suffix. Malformed, foreign, tampered, or
  stale/recycled cursors refuse with
  `AccountRegistryError("account history cursor is malformed, foreign or stale; HOLD")`.
- Refusals (stable `AccountRegistryError`, no error swallowing): unknown or
  malformed alias, invalid kind, non-integer or out-of-range limit
  (valid 1–100), malformed/foreign/stale/expired cursor, wrong alias or
  incarnation, wrong venue scope.
- Entries are the modules' scrubbed `public_record` views only
  (`entry_permitted: false`, `mode_or_mandate_granted: false` for
  restrictions; `execution_authority: false` for lifecycles). No secrets, no
  entry/mandate grant, no balance change, no new trades, no live provider
  effect. Paging never writes: registry file bytes are unchanged by a page.
- Cold restart: digest, order, and cursor semantics derive only from
  persisted rows and the resource revision, so a fresh `AccountRegistry`
  returns byte-identical pages and cursors.
- Concurrency: pages are taken under the registry mutation lock from a
  fresh on-disk snapshot; concurrent readers walk identically and a writer
  appending history invalidates outstanding cursors (stale refusal) instead
  of mixing snapshots.

## Changed files

| File | Before (SHA-256) | After (SHA-256) |
| --- | --- | --- |
| `trading/vati/accounts/registry.py` (563 → 701 lines) | `9577f5ce652424a4b9a1284025367f1bcbe8ab402894739bc1e28b406a98a4d5` | `9819407ee171a1330634e7728b728971540813fa51f8a355e2d9f770e499ffaf` |
| `trading/tests/test_account_history_pagination.py` (new, 281 lines) | — | `6116372480e0839d3dc957c9079e0028f4aa227aca81c1709b931a8dcef967c0` |

## Tests (real, executed locally)

- Environment: isolated venv `venv-be006`, Python 3.12.3, pytest 9.2.0,
  cryptography 50.0.2. Command (from the local checkout):
  `PYTHONPATH=<checkout>/trading <venv>/bin/python -m pytest tests/test_account_history_pagination.py tests/test_account_restrictions.py tests/test_account_lifecycle.py tests/test_account_resource_versions.py tests/test_account_registry_concurrency.py tests/test_account_strategy_detachment.py -q`
- **Result: 103 passed, 0 failed, 0 skipped** — 31 new BE-006 tests
  (empty page, multi-page restriction walk, lifecycle walk, cursor replay,
  invalid limit/kind/alias, malformed/tampered/foreign/stale cursors,
  cold-restart identity, read-only + returned-entry tamper resistance,
  4-thread concurrent readers, privacy scrub + exact source-digest check)
  plus 72 pre-existing tests in the affected suites, all passing.
- Baseline before the edit: `test_account_restrictions.py` 20 passed;
  lifecycle + resource-versions + registry-concurrency 39 passed.
- Pre-existing, unrelated collection errors (NOT regressions, NOT in scope):
  `test_account_restriction_identity.py` /
  `test_account_restriction_journal.py` — `ModuleNotFoundError: fastapi`;
  `test_account_retirement_native_guards.py` — `ModuleNotFoundError: backend`
  (imports `backend.tests…` / `fastapi`, packages absent from this checkout).
- `git diff --check` clean. No PostgreSQL tests: the chosen path is the
  native file registry, not PG; no genuine PG test was claimed.

## Remaining gates (all OPEN)

BE-006 unit acceptance NOT_ISSUED until independent review of this exact
diff; native financial custody, Project Truth, DDS read key, Zuul, BQ/BG-001,
Android/S24, and production remain NOT_ADMITTED. No push/merge to protected
main, no live trading or payments. Cursor work (PR #105, public gateway /
OBL004) untouched.
