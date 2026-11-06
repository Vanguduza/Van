# F15, reviewer, owner-signature and identity requirements (read from source)

Sources: `Vanguduza/dial-development-system` at the VAN test pin `64d6b715` and at `origin/master` `204f2f3b`, plus VAN Rev1.18 package tree `ac0226a2`. Gate rules (`development-pack-gates.mjs` `534dc8dc`) and the standard (`FORENSIC_DEVELOPMENT_STANDARD.json` `eaf04c6d`) are byte-identical at both DDS revisions. The certifier CLI differs only in requiring a registered project on `master` (`getRegisteredProject` instead of `getProject`). Use the `master` behaviour.

## 1. Native entrypoints actually reachable from this session

| Entrypoint | Result |
|---|---|
| Typed `dial-oracle-control` / `dial_*` tools | Not present in this session's tool inventory |
| `dial-oracle-status` MCP (DDS `.mcp.json`) | Reads `$DIAL_CONTROL_HOME/missions/...`, otherwise the git mirror branch `oracle-runtime-status`. That branch was readable at `ed4a88a`, observed **2026-09-30T04:01:35Z** (stale): project `dial` only, mission PAUSED, development BLOCKED. It contains no VAN registry or pack data |
| DIAL control home (`/var/lib/dial-control`), estate authority (`/var/lib/dial-estate-authority`) | Host paths on the DIAL control host; not available in this container |
| Desktop Commander device | Available, but the package forbids using the physical desktop as a substitute runtime. Not used |

**Consequence:** the registered VAN project, its development pack and F15 inputs **cannot be read** from here. Every statement below about them is derived from source code, not observed state.

## 2. Project identity: `van` versus `16f2f43a-8d8b-4f18-a6ac-5bd8df620414`

- **Certifier comparison** (`predevelopment-forensic-gate.mjs`): `project = getRegisteredProject(slug)`; `projectId = project.project_id || project.slug`; fails with `PROJECT_IDENTITY_MISMATCH` unless `pack.project.project_id === projectId`.
- **Registry assignment** (`project-registry.mjs`, `registerProject`): `project_id = previous?.project_id || (slug === 'dial' ? 'dial-development-system' : slug)`. VAN is seed project `van` in `UNIVERSAL_PROJECT_REGISTRY.json` (dedicated repository, so not auto-seeded as a monorepo entry). A first registration therefore yields `project_id = 'van'`. A pre-existing record could carry another id; the slug pattern `^[a-z0-9][a-z0-9._:-]{0,220}$` would accept a lowercase UUID.
- **UUID provenance:** it first appears in VAN history on 2026-10-18 (`a0366b1d`, `a1411829`, `e0d13e99`, "stage Rev1.14 … for Muse"), only inside review-input documents. It is absent from all DDS history and every runtime source root. The Rev1.15 audit recorded it as "retained as supplied, not newly attested".
- **Determination:** these are two namespaces, the DDS registry project id and a package-level project label of unattested origin. They become an invalid mismatch only if the UUID is written as `pack.project.project_id` for a registry entry whose id is `van`, or the reverse. **Required mapping:** the VAN development pack must use the registry's actual `project_id` as observed on the control host (expected `van`) and may carry the UUID as an alias with its provenance. No identifier should be renamed. If the control host shows a record whose `project_id` is the UUID, the mapping inverts and the package stays as is.
- **Status:** `MAPPING_DEFINED_PENDING_NATIVE_READBACK`. The single action needed is to read `operations/project-registry.json` for slug `van` on the control host.

## 3. What F15 actually requires

**Certificate (DDS):** `FORENSIC_BUILD_READY` only if all of the following hold:
1. The standard is present and `LOCKED`.
2. The project is registered.
3. The pack exists at `projects/<slug>/development-pack/pack.json`.
4. The identity matches (§2).
5. The repository HEAD of the registered `repo_dir` equals `pack.artifacts.baseline.repository_sha`.
6. Governing documents are present.
7. Every applicable F0–F14 is PASS.
8. `forensic_predevelopment.preparation_blockers` is empty.
9. `runtime_qualification_separated === true` and `certificate_binding_defined === true`.

The certificate's `fingerprint` is SHA-256 over its core. **It is not a signature.**

**F0–F14 evidence fields** (all in `pack.artifacts.forensic_predevelopment` plus the legacy pack gates):

| Gate | Requirement |
|---|---|
| F0 | `owner_intent_falsifiable`, `scope_exclusions_explicit` + Product Truth gate |
| F1 | `shared_authorities_mapped`, `verification_obligations_mapped` + unit gate |
| F2 | `requirement_to_unit_traceability_complete` + feature/screen/realization gates |
| F3 | authority.{requester, policy_owner, execution_authority, credential_boundaries, audit_events}_mapped |
| F4 | state_persistence.{canonical_state_owners, persistence_mechanisms, restart_process_death, idempotency, conflict_strategy, retention_deletion_revocation}_defined |
| F5 | causal_paths: `paths_proven == material_behaviors_total > 0`, `unreachable_required_behaviors == 0`, production callers, authority checks, reconciliation, observable postconditions proven |
| F6 | research.{build_vs_adopt_recorded, license_security_reviewed, unsupported_assumptions_recorded} |
| F7 | architecture.{no_duplicate_authority, no_parallel_canonical_state, identity_error_event_models_coherent, lifecycle_dataflow_coherent} |
| F8 | failure.{timeouts, retry_limits, idempotency_verified, restart_recovery, stale_state_handling, escalation} |
| F9 | security.{credential_ownership, secret_storage, trust_boundaries, input_validation_injection_defense, least_privilege, egress_boundaries, revocation_path, audit_path, replay_defense} |
| F10 | verification.{reachability_evidence, failure_injection, runtime_gates_separated, owner_acceptance_separated} |
| F11 | adversarial.{review_complete, mock_only, unreachable, presentational_only, false_success, dead_or_orphaned, restart_stale_state}_checked |
| F12 | symbiotic loop fields (applies: VAN is agentic/trading) |
| F13 | reachability.{production_registration, production_callers, real_state_binding, lifecycle_startup_or_na, observable_postconditions}_proven |
| F14 | anti_gap.{mutation_executed, critical_breakage_detected, canonical_tree_guard, authority_bypass_guard, caller_disconnect_guard, live_binding_guard_or_na} |

The DDS gate code reads these as booleans. Their **truth** depends on whoever writes the pack, which is why the VAN contract adds independent verification and an owner signature on top of the certificate.

## 4. Who may review, and which reviewer identities are trusted

`review-fabric.mjs` counts an approval only when all of these hold:
- the receipt verdict is `APPROVE`;
- it carries `native_action_id`, `resolved_model` and `provider_family`;
- a root-signed `DDS_REVIEWER_IDENTITY_V1` record (issuer `ESTATE_ROOT_BROKER`, Ed25519 over canonical JSON, public key `/etc/dial-control/estate-owner-approval.pub`, root-owned storage, unexpired) binds project, checkpoint id/hash, review job, reviewer harness, reviewed repository SHA, receipt hash, provider, model, native action and observed turn identity;
- each reviewer harness and native action is counted at most once;
- a signed `DDS_REVIEW_COMPLETION_MANIFEST_V1` closes the checkpoint.

Quorum is `required_independent_reviews` (default 1), with two provider families if `provider_diversity_required`. CRITICAL or HIGH findings or `REQUEST_CHANGES` yield `REVIEWED_CHANGES_REQUIRED`. Analysis requests require `author_harness !== reviewer_harness`. The DDS rule text says: "author or renamed same worker is not an independent reviewer". A subagent or second conversation launched by this lead has no estate-root identity record and shares the author harness, so **it is not eligible**. No eligible reviewer is reachable from this session.

## 5. Owner signature (OQ-05)

- **VAN contract:** PRE-003 requires a valid owner signature. `plan/PROPOSED_SCOPE_LOCK.json` is `PREPARED_PENDING_OWNER_SIGNATURE` with `signature: null`, deferring to "the existing trusted owner signature/promotion process". No record format is defined in the package.
- **DDS:** the only owner-signed root-evidence kind in code is `DDS_OWNER_SOURCE_AUTHORIZATION_V1`, verified with the same estate-root Ed25519 key and used for memory admission. The F15 certifier itself checks no owner signature.
- **Decision required (owner):** which existing signed mechanism carries the scope-lock approval, for example an estate-root owner-authorization record binding the scope-lock file hashes, package tree `ac0226a2` (or the AP-001-amended tree) and the reviewed repository SHA. This document does not choose it and claims no signature.

## 6. Baseline binding and invalidation

- Certificate validity requires observed HEAD == `baseline.repository_sha`. **Any later commit to the registered repository makes it stale** (`PROJECT_BASELINE_STALE`).
- Task envelopes carry standard id/version, certificate hash and preparation fingerprint. A changed fingerprint refuses execution (guide §25; `TASK_ENVELOPE_FORENSIC_FINGERPRINT_STALE`).
- Review receipts bind `reviewed_repository_sha`; root evidence has `expires_at`; `stale_certificate_invalidation_required: true`.
- The VAN package adds: "a relevant source, policy or scope amendment invalidates affected receipts" (AP-001 admission changes the package tree, so the review must target the amended tree).
- **Recommended F15 baseline:** freeze one commit after AP-001 is admitted and PR #104 (plus this evidence) reaches the admitted base, then certify that exact SHA in that exact registered `repo_dir`. Evidence produced against `33c6e818` or later transient heads must be re-verified (`pre001.py check`, `ap001.py check`, `manifest.py check`) at the frozen SHA.
