# What is retained, changed, and held — Opus consolidation

Pinned Opus working head `a39f241b0135cf92cc5a6b9a28af226aa294603d`; main `8eb1889822fc8a83f219977c15340172e16acd91`. Source code is retained in the working branch and immutable Git references. The downloadable pack does not redistribute the complete repository. `tools/collect_source_evidence.py` regenerates the source ledger from an authorized checkout.

| Admission | Capability | Treatment | Backend / qualification owner |
|---|---|---|---|
| ADP-01 | Opus product/authority decisions, visual design and original feature set | ADOPT_REQUIREMENTS | PRE-001, PRE-002 |
| ADP-02 | Deterministic generation, duplicate and missing-producer checks | ADAPT_GENERATOR_KEEP_VALIDATION_PATTERNS | PRE-002 |
| ADP-03 | Typed transition allowlist, 159 approved edges and 35 proof types | ADAPT_READINESS_KEEP_EXACT_GUARDS | PRE-002, BE-002, BE-017 |
| ADP-04 | Immutable evidence builder and clean-input refusal | ADOPT_AFTER_EXACT_SOURCE_REVIEW | PRE-002, PRE-003 |
| ADP-05 | Incremental ledger verification | ADAPT_WITH_INTEGRITY_QUALIFICATION | BE-003 |
| ADP-06 | Relative slippage and instrument-aware bounds | ADAPT_METADATA_AND_POLICY_BINDING | BE-008, BE-009, BE-010 |
| ADP-07 | No-widening tick quantisation | ADAPT_PRE_APPROVAL_NUMERIC_CONTRACT | BE-008, BE-009, BE-010 |
| ADP-08 | Strategy entry type through allocator/policy/router and venue refusal | ADAPT_REMOVE_UNAUTHORIZED_COERCION | BE-010 |
| ADP-09 | Pending order model, reservation, thesis and TCA integration | KEEP_MODEL_CORRECT_CRITICAL_RESIDUALS | BE-010, BE-012, BE-019 |
| ADP-10 | Persistent cooldown, probation and signed reset infrastructure | KEEP_ACCEPTED_VALUES_ADAPT_RUNTIME_BINDING | BE-002, BE-009, BE-013 |
| ADP-11 | Test-time clock fix | ADOPT_TEST_RELIABILITY_FIX | BE-009, BQ-007 |
| ADP-12 | Historical strategy experiment harness and per-trade data | PRESERVE_RESEARCH_NOT_PROMOTION_PROOF | BE-035, BE-036 |
| ADP-13 | Continuous strategy development OD37 | ADOPT_AND_COMPLETE_ON_EXISTING_VATI | BE-036 |
| ADP-14 | Native chart spike | QUARANTINE_UNTIL_POST_BG_FRONTEND_CONTRACT | FE-007, FE-008 |
| ADP-15 | Earlier atomic account registry fix | REFERENCE_CANDIDATE_NOT_PROVIDER_ACCOUNT_SERVICE | BE-004, BE-005 |
| ADP-16 | PR93 owner-core, legacy behaviour and complete source atlas | PRESERVE_BY_FUNCTION_NOT_BLANKET_MERGE | PRE-001, BE-001 |
| ADP-17 | Muse/receipts/JEV/cognitive/Android/site/studio branch candidates | PRESERVE_CANDIDATES_REQUIRE_LIVE_REVALIDATION | PRE-001, BE-024, BE-025, BE-026, BE-034 |
| ADP-18 | Forecast, research lifecycle and prediction-market addendum | INTEGRATE_INTO_SINGLE_CANONICAL_GRAPH | BE-035, BE-036, BE-032, BG-001 |
| ADP-19 | Whole-product backend-first parent and per-screen design | ADOPT_WITH_NEW_SOURCE_AND_REQUIREMENT_RECONCILIATION | PRE-002, BG-001, UX-003 |
| ADP-20 | B1 total scope and B4 evidence closure rather than waiver | ADOPT_GATED_CLOSURE_POLICY | PRE-002, PRE-003, BG-001 |

The 105-file source delta was independently enumerated on the VM. This is not a claim of a complete line-by-line semantic audit of every changed file or every candidate PR. Untested or unreviewed components remain explicit PRE-001/BE-001 admission obligations. A component may be preserved without its current defect being accepted.

## Source precedence
Latest explicit owner scope → exact source/evidence → retained product semantics → canonical contracts and graph → historical examples. The new schedule does not retroactively approve old implementation activity or source changes.
