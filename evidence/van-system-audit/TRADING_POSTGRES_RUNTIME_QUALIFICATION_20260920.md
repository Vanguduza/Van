# PR #49 Trading Core PostgreSQL Runtime Qualification — 2026-09-20

## Scope

This record qualifies the PostgreSQL authority primitives introduced/used by the PR #49 trading enhancement closure. It is **not** evidence that the PR branch was deployed into the live VATI service or that any venue order was submitted.

## Exact code under qualification

- Repository: `Vanguduza/Van`
- PR: #49
- Qualification SHA: `5b1fc8689d64f660ec135242995e02f94bd78497`
- Host: `van-trading-core`
- Isolated worktree: `/home/ubuntu/work/van-pr49-qual`
- Live deployed checkout was left unchanged during qualification.

## Focused runtime suite

Executed on `van-trading-core` from the isolated worktree using a temporary qualification virtual environment:

```text
trading/tests/test_account_coordinator.py
trading/tests/test_execution.py
trading/tests/test_execution_and_exits.py
trading/tests/test_account_trade_lifecycle.py
trading/tests/test_capsule_promotion_workflow.py
```

Result:

```text
93 passed, 2 warnings in 0.99s
```

The warnings were dependency deprecation warnings from FastAPI/Starlette test helpers and did not change test outcomes.

## Real PostgreSQL canary

Tool:

```text
trading/tools/qualify_postgres_runtime.py
```

The canary has a fail-safe database-name guard and refuses to run unless `current_database()` begins with `vati_pr49_qual_`.

Environment:

- temporary PostgreSQL container image: `postgres:16.10`
- bound to loopback only on Trading Core
- disposable database: `vati_pr49_qual_runtime`
- no production database credential was read or passed to the canary
- production Supabase/n8n PostgreSQL containers were not modified
- the temporary qualification container was removed after the run

Observed result:

```text
POSTGRES_CANARY_OK
database=vati_pr49_qual_runtime
lease_arbitration=GRANTED/REFUSED_HELD_BY_OTHER/TAKEOVER_EPOCH_2
submission_guard=TWO_PROCESS_ROW_LOCK_BLOCKED_TAKEOVER
crash_release=PROCESS_TERMINATION_RELEASED_ROW_LOCK
ledger_chain=OK
ledger_events=40
ledger_writers=2
```

## What this proves

### Shared lease arbitration

Two independent PostgreSQL connections contended for the same account alias. The first holder was granted the lease, the second was refused while the first lease was live, and the second acquired epoch 2 only after expiry.

### Final submission fencing

A separate OS process attempted takeover after the lease timestamp had expired while the first process held `submission_guard`. The contender remained blocked until the PostgreSQL `SELECT ... FOR UPDATE` guard released, then acquired epoch 2.

This proves that takeover cannot occur merely because wall-clock TTL expires while the guarded broker-submission critical section still owns the arbitration row lock.

### Crash release

A process was terminated while holding the submission row lock. PostgreSQL released the lock when that process/connection died, and a separate contender then acquired the next epoch.

### Hash-chain concurrency

Two independent writer processes each appended 20 `SESSION` events through `PostgresLedger`. Final verification reported a valid 40-event chain with no fork.

## What this does not prove

This qualification does **not** establish:

- live multi-symbol BarLake/MTF behavior against production feeds;
- real venue fill behavior;
- real account allocation performance;
- real ExecutionPolicy effects at a broker;
- owner activation of a wider per-strategy budget;
- independent reference-feed disagreement handling.

Those remain separately classified in the component ledger where applicable.

## Cleanup

The disposable PostgreSQL qualification container was removed after the canary. No PR #49 code was deployed over the live Trading Core application during this qualification.
