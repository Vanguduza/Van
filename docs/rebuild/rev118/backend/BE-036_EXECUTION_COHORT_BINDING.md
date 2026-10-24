# Native execution and research cohort binding

Candidate source only; original programme and acceptance gates retained.

Six valid counterexamples exposed two provenance defects: BacktestEngine admitted hooks labelled DEMO, LIMITED_LIVE or LIVE (including a hook relabelled after construction), and a real Paper service configured with a live policy inherited that live evidence cohort. Backtests without hooks also left no execution-cohort binding in risk history. A policy's financial permission ceiling is not proof of actual execution provenance.

The source now binds the actual adapter and explicit research purpose independently of that policy ceiling. BacktestEngine requires BACKTEST hooks both before construction effects and again before running. DecisionCycle verifies the hook against the native execution binding. Paper supplies DEMO facts, or SHADOW for a non-sending runtime; explicit historical studies supply their own research cohort. Both actual service builders use this binding.

Risk records seal the producer's execution-cohort schema, kind and environment alongside the original risk input. Account-scoped replay reads that original binding rather than relabelling research from its policy. Malformed bindings, unknown kinds and simulated LIVE claims remain unresolved. Known research history is excluded from a live cohort without inventing an account-history fault. Legacy records retain their existing explicit reconciliation behavior.

The old integration test that used a historical engine to trigger a DEMO demotion now exercises the actual Paper DecisionCycle, preserving its weighted sample minimum, genuine close, bounded adjustment, capsule retirement and deterministic replay assertions. Historical research still produces health observations at weight 0.3 and execution facts at weight zero, including after restart.

The first full run records 2,228 passes and one failure in the new PostgreSQL fixture's cleanup: it called a nonexistent account-service close method after its cohort assertion passed. That failure is retained. Correcting cleanup yields a passing actual PostgreSQL control. Eight source faults are caught after passing controls, including the actual book builder, with original bytes restored and private fixtures removed. A fresh exact-commit qualification run is required before claiming a clean full pass. No external MT5/native account identity, provider settlement, entire-unit acceptance or profitability is established here.
