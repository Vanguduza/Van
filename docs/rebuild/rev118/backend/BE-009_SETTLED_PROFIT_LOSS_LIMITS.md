# Settled profit and loss-limit recovery

Candidate source for BE-009. This change prevents an estimated gain from releasing a financial risk restriction; it does not qualify a live provider, strategy or profitable system.

The real cycle reproduced three settled losses being reset to zero by a finite price-derived gain whose own stored review said `fees_final=false` and `cash_reconciled=false`. The account runtime had the same problem. Its scalar fallback additionally reset the loss counter on a flat close. Restart reconstruction repeated the optimistic reset from the immature stored review.

The shared governor now requires explicit `profit_final=True` to reset losses or probation after a positive result. Both production close paths derive that value from the same native maturity observation they persist in the review, with strict boolean finality flags, a recognized net-PnL convention, native settlement source/environment and currency checks. The account fallback follows the same rule; zero preserves its counter. Known losses still count conservatively. Cold reconstruction uses the recorded native eligibility rather than treating every positive number as settled cash.

The only implemented native economic-finality producer remains deterministic paper settlement. Its genuine order, complete cash close and reconciliation provide the positive control. Additional providers need actual admitted financial-finality producers; a new source label or truthy string cannot make one. No provider maturity is invented and no estimated review, price or cash record is deleted. Estimates remain available for appropriately labelled analysis.

The tests exercise live cycle, account governor and scalar paths, cold replay, a real paper order/cash-close positive control, malformed or missing finality flags, unadmitted source/environment, currency/basis labels and non-boolean release claims. Initial counterexamples and the initial misplaced-helper patch failure are retained in the source receipt. The direct governor unit's genuinely settled positive input now opts in explicitly; its risk-reduction and recovery assertions remain.

This packet addresses loss-limit release only. Native provider finality/corrections, learning-health admission of mature results, immutable episode provenance, explicit retrospective studies, physical account/worker identity and the full original programme remain. Source test counts do not execute or admit the frozen 1,610 acceptance contracts. See `../receipts/SETTLED_PROFIT_LOSS_LIMITS_SOURCE_20261023.json` for measured validation and scope.
