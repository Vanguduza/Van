# BE-004 candidate: preserve configured account metadata in the actual factory

Four actual factory counterexamples reproduced paper accounts reporting USD despite a different configured currency, and an owner-ticket account reporting `zse_primary` / `zse` / `ZiG` despite a different configured alias, venue and currency.

The production factory now passes those existing fields to their native adapters. Opening balance/equity hints retain the configured account denomination. Owner-ticket verification remains false until the separate existing CSD/owner evidence is supplied, and the existing entry-authority fence remains in place. This does not invent broker verification, currency conversion, symbol-specific paper contract calibration or settlement proof.

The full trading suite passes 1,935 tests without skips using actual private PostgreSQL and pinned DDS source. The focused metadata/infra/entry suite passes 28 cases with its one PostgreSQL opt-in skipped there and exercised in the full run. All four original failures are corrected. The private fixture is stopped and removed. No UI, blueprint, live service, financial authority or whole-unit qualification is changed.

Continue the original generic account-operation and result-recovery source work. Symbol-specific paper contract valuation, account physical-identity/lease scope, provider qualification and exposure/funds-safe lifecycle remain required.
