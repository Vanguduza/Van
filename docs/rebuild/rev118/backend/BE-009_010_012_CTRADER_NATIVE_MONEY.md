# Native cTrader quantity and account money

The adapter rounded every native fill to two lot decimal places. A native quantity of `10000` with a `10000000` lot size became zero instead of `0.001`; `0.015` could become `0.02`. Position and execution quantities now preserve the actual native ratio. Outgoing volume still follows the venue's own minimum and step rules.

Account equity previously added a local quote calculation to balance. Without a cached quote, an open losing position contributed zero. For an account whose deposit currency differed from the symbol quote currency, the calculation also added amounts in different currencies.

The adapter now reads `ProtoOAGetPositionUnrealizedPnLReq/Res` from the existing, hash-pinned native protocol. That response defines net PnL in the account deposit currency and supplies its own money exponent. Net PnL includes the native mark's costs; its contract excludes potential closing commission. This is current marked equity, not settled profit or evidence eligible for self-optimization.

Account identity, integer money fields and decimal exponents must be valid. The native position and PnL identities must agree without duplicates; missing, foreign, malformed or unavailable observations refuse a verified account state. An explicitly empty native position/PnL set is a known zero. No cached quote or default USD value substitutes for this source.

The separate balance and PnL reads are not an atomic broker snapshot. The adapter reads the native trader again and refuses a visible balance, precision or deposit-asset change across the observation. Position-set drift also requires a refresh. These checks do not certify an atomic remote snapshot or remove the final native execution/risk fences.

The original defects reproduced fourteen failures with one positive control. Three additional tests reproduced funds changing during the observation. A framed native-protocol test independently exercises negative PnL and a sub-centilot position. Its first fixture omitted the required native `swap` field; that invalid instrument attempt is retained separately from the corrected execution.

The source receipt records focused and full trading results, actual isolated PostgreSQL cleanup, seven passing controls with seven assertion-detected faults, pinned protocol hashes and restored source hashes. Candidate milestones belong to BE-009/010/012; no complete unit, broker, financial, deployment, profitability or handset acceptance is issued. Native close/stop/entry uncertainty, real-provider settled money/finality, late corrections and the complete original programme remain obligations.
