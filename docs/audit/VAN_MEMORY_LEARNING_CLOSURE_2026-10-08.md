# Owner memory controls and observed learning closure

Repository implementation evidence, 2026-10-08. The focused backend run passed **116 tests**; its [raw log](validation/memory-learning-closure-final-2026-10-08.log) and [source receipt](VAN_MEMORY_LEARNING_VALIDATION_2026-10-08.json) are local evidence. No deployment, provider effect or handset acceptance is claimed.

## Per-record memory controls

The owner can inspect paginated records, read one exact record, export a screened bounded representation, and obtain an immutable A4 erasure plan for every store in the existing twelve-store forgettable inventory. Credentials, device keys, grants, work history and audit are outside this inventory. Record URLs contain a stable hash of the complete primary key, including composite vocabulary and intent-link keys; private owner words are not encoded in paths.

| Owner route | Contract |
| --- | --- |
| `GET /v1/context/records?store=...&limit=50&cursor=0` | Snapshot-consistent page; total, next offset and explicit pagination limits. Refresh after writes because offsets may move. |
| `GET /v1/context/records/{store}/{record_id}` | Exact identity, sealed revision, screened fields, source classification and available provenance. |
| `GET /v1/context/records/{store}/{record_id}/export` | Same exact screened bounded representation; the revision still commits to complete stored content. |
| `GET /v1/context/records/{store}/{record_id}/erasure-plan` | Exact A4 command, revision, affected store counts and up to 100 dependent identities per store; intentional retained work/audit disclosed. |

These read routes require the current admitted hardware-bound owner identity. Missing records return 404; invalid store, identity or pagination returns 422. Responses are not cached. Unsupported provenance remains `UNCLASSIFIED`; a read or declaration never grants execution authority.

Erasure uses `forget owner-derived memory record <store> <mr_sha256> <revision_sha256>` through the existing command and fresh biometric A4 approval flow. The revision seals the selected row and all existing dependent content. A changed row or new dependent link refuses the approved command instead of silently expanding its effect. Deletion, hash-only witness and context revision commit atomically after current device, authority, expiry and scope checks. Independent readback verifies exactly captured identities are absent while unrelated rows remain.

Intent deletion removes its existing incoming/outgoing edges and mission links. Cognitive assertion deletion removes growth records explicitly linked by `assertion:<id>` so an erased adaptation cannot continue to influence behavior. Unselected assertions/growth remain. Per-record vocabulary and collaboration erasure removes only the selected owner-declaration witness. Historical decisions, work and audit intentionally remain distinct from erased derived memory.

## Evidence-bound producers

`GET /v1/understanding/learning/producers` reports each producer independently with `READY`, `NO_DATA`, `PARTIAL` or `DEGRADED`, bounded observation/comparison counts, snapshot digest and actual references. Unreadable data yields unknown counts and a fixed safe degraded explanation. No background daemon or running-service claim is inferred from this read-time producer.

The existing `/v1/understanding/decisions` and `/v1/external-reality` projections now contain actual bounded pattern candidates and structured comparisons. At least three distinct observed owner choices in the same typed task/action/project context are required for a pattern. A mission's owner-presence requirement is insufficient evidence: legacy approval fingerprints must match a durable owner-approved command seal. Actual owner-answer fingerprints must match the retained immutable choice, note, mission and answer timestamp. Duplicate events, generic contexts, malformed rows, stale observations and absent authority stay unmeasured. Custom choice identities remain case sensitive, so `BUY` and `buy` cannot be merged as equivalent support. Counterexamples and unknown outcomes remain visible; independently verified success requires the actual mission verification state as well as the recorded outcome. Reasons are never guessed, confidence is capped, and candidates grant no permission.

Actual authenticated owner answers write their stable fingerprint inside the same source transaction. Retries and reads do not regenerate memory; prior erasure witnesses suppress projection resurrection. A failed source transaction leaves no learning row.

Actual knowledge provider persistence produces an external observation only from an exact bounded scalar JSON claim containing subject, predicate, value and optional scope. Evidence and eligible observation commit together. Prose, sensitive claims, missing or credential-bearing references, mismatched digests, tampered content and stale sources produce no asserted disagreement. Exact claims compare only with current canonical owner declarations in the same subject/predicate/scope; original source trust is preserved, external confidence remains zero, and neither side is promoted to verified truth. Output is limited to 200 comparisons and truncation is explicit. Owner corrections resolve current disagreement; erasing a required declaration makes comparison unmeasured.

## Validation and limits

The focused suite covers real owner read routes, signed A4 approval/effect/independent readback, exact retries, stale content and expanded dependent scope refusal, retained unrelated records, composite identities, source privacy, current schema declarations, restart recovery, actual owner answer transaction and rollback, explicit forgotten-event suppression, provider projection rollback/recovery, stale/malformed evidence, counterexamples and unmeasured/degraded producer states.

This closes the corresponding source gaps in `OF-MEMORY-002` and `OF-LEARNING-003`. Actual deployed source feeds may still be empty or unbound. The registry must retain provider/deployment/physical acceptance requirements and show unavailable evidence honestly. The parent whole-workspace validation manifest determines final release qualification.
