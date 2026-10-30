# Native outbox delivery claim

Candidate source for BE-003 and BE-010. Two real independent SQLite bridge connections reproduced delivery of one original command to two consumers. The same race was executed through two locally authenticated HMAC HTTP poll applications. Both returned the same original command ID.

`BridgeQueue.take_pending` now claims the complete selected batch under a database write transaction before returning it. Instance locks still protect each connection; the database arbitrates across instances. Parsing or pre-commit failure rolls the batch back. A successful commit whose acknowledgement is lost leaves the batch TAKEN and cannot authorize a second delivery. No external or broker IO occurs in the claim transaction.

23 relevant bridge, original-claim, stop and explicit-boolean protocol tests pass. They include actual failure before commit and loss of its successful reply. Restoring the old method is caught after a passing control; source bytes were restored and the mutation journal removed. See [the source receipt](../receipts/NATIVE_DELIVERY_CLAIM_SOURCE_20261023.json). The complete 2,118 trading suite belongs to the preceding commit, not this change.

This establishes one database delivery claim; it does not establish that a terminal executed it. Original unknown outcomes remain held and require readback/adjudication. Native worker identity/mode/epoch/deadline checks, precision, actual pending-order types, cold prepared setup, economic finality and all original product obligations remain. No deployed provider, unit or S24 acceptance is issued.
