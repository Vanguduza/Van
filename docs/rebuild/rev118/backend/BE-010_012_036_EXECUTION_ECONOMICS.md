# BE-010 / BE-012 / BE-036 candidate economics corrections

This is source implementation evidence, not unit completion, statistical qualification, a new grant or a claim of profit.

## Corrected accounting

New `tca/2.0.0` measurements reconcile to signed `(fill - decision reference) * actual filled quantity * contract value + explicit net fees`. Favorable fills and rebates retain their negative cost sign. Spread remains diagnostic and is not added again. The decomposition includes decision-to-arrival, arrival-to-submission and submission-to-fill movements. Filled quantity, contract value and reference notional are retained so normalization can be checked independently. Invalid/nonfinite values, an untyped direction, or use of requested instead of filled quantity are refused. Existing ledger events are not rewritten or reinterpreted as new measurements.

## Joint planning constraints

Participation is floored to the venue lot step before slice count is computed. Every ordinary and final slice must satisfy minimum lot, step, participation and maximum count together. Quantity 200 / displayed depth 10 / participation 0.25 requires more than eight children and is refused. A cap below the venue minimum is refused. Rounding the final slice above participation is refused. Feasible plans preserve the entire quantized quantity.

A plan is not proof of fresh/replenished liquidity. The current single-command router still refuses multi-child styles; it does not reuse one displayed book as new liquidity. A complete qualified child-order scheduling protocol remains BE-010 work. Protective-exit urgency cannot be passed to the new-entry router to bypass these constraints. Style refusals become normal RouterError results, and the router independently checks sealed style quantity against approved quantized quantity.

## Learning estimate

The former weighted mixture of conditional medians was not a mean execution-cost estimate, and default zero costs could promote an unmeasured template. Execution evidence now records each complete objective cost or explicit missingness. Any missing required objective prevents scoring that stream. Partial fills require an explicit complete objective cost including the residual benchmark. The estimate is the arithmetic mean over the complete objective stream, recorded with estimator `MEAN_COMPLETE_OBJECTIVE_COST/1` and policy version `execution-policy/1.1.0`.

This descriptive estimate does not establish causality, distinguish all flukes, issue a policy qualification or establish net profitability. Existing defensive learning remains separate. Durable corrected observations, independently qualified cohorts, provider/model epoch controls and the actual positive learned-snapshot-to-selector loop remain source implementation work under BE-003/012/036 and their verification units. No in-memory unit sample threshold is treated as that qualification.

## Verification

`trading/tests/test_execution_economics_invariants.py` uses direct signed accounting, tail-cost and missingness oracles, infeasible/feasible lot matrices, and actual order-router rejection before adapter submission. The accounting and missing-data defects were reproduced before correction (logs hashed in the receipt). Final full trading suite: 1,576 passed, 2 skipped, 3 warnings. Existing risk, kill-switch, recovery, protection and authority checks remain active.
