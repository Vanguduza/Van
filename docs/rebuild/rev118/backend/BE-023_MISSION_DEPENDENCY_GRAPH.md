# Truthful mission dependency graph

The activity API previously discarded dependency IDs, retry policy and verification contracts. Direct service calls could attach a nonexistent or foreign-mission dependency. The wire now preserves these declared contracts, and admission validates dependency identity and scope in the same write transaction that inserts work. A mission becoming terminal during admission wins over the attempted insertion. Undeclared body fields are refused.

`GET /v1/missions/{mission_id}/graph` is an owner read through the existing mission authentication boundary. One SQLite snapshot supplies mission state, activities, owner-visible stage evidence and available browser/automation executor observations. Reading or arranging a graph never starts, completes or authorizes work. Partial and unverifiable executor outcomes remain explicit alongside their activity lifecycle state.

Node IDs are the original activity IDs. Edge IDs derive from mission and dependency identities, independently of layout and query ordering. The projection reports legacy cycles, missing dependencies and conflicting claims to the same executor reference. Invalid graphs have no critical path. Corrupt historical facts return unavailable, and explicit node/edge/evidence limits refuse oversized responses without silently dropping work.

The reported critical path is the longest dependency chain under an explicit dependency-count metric. It is not a time or completion estimate; `estimated_duration_ms` is null. Timed scheduling, project-wide task CRUD, provider task intervention and native service acceptance remain original BE-023/024 work. This increment does not declare those units complete or replace native development-project truth.

Executed source evidence and deliberate faults are recorded in `receipts/MISSION_DEPENDENCY_GRAPH_SOURCE_20261023.json`. The existing mission registry receives the backend contract; its redesigned Android consumer remains behind the original frontend gate.
