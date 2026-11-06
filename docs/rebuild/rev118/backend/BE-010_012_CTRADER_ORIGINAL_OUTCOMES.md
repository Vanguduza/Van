# cTrader original execution and protection outcomes

The original adapter converted a lost entry reply into a rejection, let lost stop/close replies escape without a typed outcome, and reported partial close events as filled. It could substitute the requested close volume for an absent native quantity, accept another account/order's close event, or claim protection from another position's fields. Twenty-two valid counterexamples and two positive controls reproduced these behaviors against the money-corrected source.

Entry, stop and close reply/event loss now produces `UNKNOWN`, with no invented protective confirmation. The existing durable original-command/exit journal remains the recovery authority; this adapter performs no automatic retry. Explicit native request errors remain rejections. Accepted entries remain distinct from observed fills.

Close events bind to the account, original native close-order ID and position, and must identify a closing order. An immediately filled response is consumed directly; a later event must match the admitted order. Missing, foreign, malformed, excessive or nonfinite money/quantity observations remain unknown. Actual partial quantities remain exact and the receipt stays partial. `FILLED` means the requested close order filled; it does not mean the entire position is flat when the owner requested only a partial close.

Entry fills require native quantity, price, symbol, order and position identity rather than substituting the requested price or coercing booleans/strings into quantity. Requests above the native maximum are refused before dispatch. Native stop acknowledgement alone is insufficient: the adapter reads the position and confirms the requested stop before claiming protection. Unknown stops preserve the existing router's rollback and safety holds.

An actual partial close remains a known partial close even if remaining protection is malformed or belongs to another position. Its protection flag stays false. The adapter does not discard a known partial fill to manufacture a successful flat position.

Source verification includes existing framed-protocol trading controls, focused adverse outcomes, a full private-PostgreSQL trading run and eleven passing controls with eleven assertion-detected faults, restored afterward. The first fault-report reader incorrectly expected pytest's XML to include a `type` attribute; the actual assertion was already detected, and the reader was corrected to validate pytest's assertion message. Both attempts are retained in the receipt.

These are BE-010/012 candidate milestones. Real broker operations, provider settled/corrected financial maturity, native session/deadline/epoch/risk envelopes, integration gates and handset acceptance remain separate original obligations. No whole-unit or profitable-strategy certificate is issued.
