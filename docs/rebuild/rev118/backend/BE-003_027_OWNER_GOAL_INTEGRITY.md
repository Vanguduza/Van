# Owner-goal state and published contracts

An owner goal remains a long-lived desired outcome, distinct from a mission execution. This packet repairs the existing owner-goal service and publishes typed response schemas for its goal/watch endpoints. It creates no new frontend and grants no mission, browser or financial execution authority.

Goal creation and its complete milestone list commit together. A failed later milestone insert leaves no partial goal or earlier milestone. Required titles, watch targets and milestone names cannot silently become blank records; supplied names are normalized before persistence. Numeric watch thresholds reject booleans rather than interpreting `true` as a price of one.

Goal patches read and write under the same transaction, so an independent edit to a field omitted from a patch survives. A single goal's fields, milestones and mission links use one read snapshot. A filtered list and all its returned goal details share that snapshot, including when an owner changes status concurrently.

Milestone updates and new mission links update the parent goal's change timestamp in the same transaction. A failed parent update cannot commit a changed milestone or link. Repeating an existing link does not add a duplicate or invent a newer change timestamp. New links require a genuine existing mission; the link does not create, start, pause, complete or otherwise change that mission. Existing legacy references are retained rather than silently removed.

The existing `Goal`, `Watch` and observation-result models now describe the actual owner responses in OpenAPI. Registry regeneration preserves all existing feature, function, surface and endpoint identities while refreshing these schemas and source citations. Android consumer redesign remains behind BG-001. Goal creation still uses the existing create contract; this packet does not claim original-request recovery for every owner CRUD operation or completion of the wider memory/privacy/goal unit.

Evidence: `receipts/OWNER_GOAL_INTEGRITY_SOURCE_20261023.json`. It includes thirteen reproduced pre-fix failures, controlled independent SQLite writes, real transaction rollback, paired gateway lifecycle/validation checks, complete source-registry checks and eleven deliberate fault/control pairs. The inherited goal test now links a real stored mission instead of treating an invented ID as a successful positive case. No whole-unit, native, deployment, production or handset acceptance is issued.
