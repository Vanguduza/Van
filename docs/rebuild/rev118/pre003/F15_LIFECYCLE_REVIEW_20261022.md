# F15 lifecycle and scope-lock approval: continuation review

This corrects and extends the author-prepared 21 October note. It is source analysis, not native readback, independent admission or a certificate. DDS source inspected: `204f2f3b4e19243fb4593d4e7f48dfa332cbef22`. Fetching its Git objects did not change the local DDS working checkout at the source-contract pin `64d6b7158c723b7700e5b53175ea8048d4e92d00`.

## Identity

The certifier compares the native registry's `project.project_id || project.slug` with `pack.project.project_id`. It does **not** compare `CANONICAL_AUTHORITY.json` directly. Therefore package UUID `16f2f43a-8d8b-4f18-a6ac-5bd8df620414` and native slug `van` can coexist if an explicit mapping identifies the same project and the native pack carries the registered identity. A mismatch has not been observed. Native registry/pack readback remains required before issuing evidence; renaming a package identifier to match a slug is unjustified.

## Certificate lifecycle

1. Settle the reviewed trusted-base/source integration and both amendment decisions first. The cumulative candidate has 1,632 acceptance identities; its admission is still pending. The source and selected package must each be pinned in the native pack.
2. Populate and independently review the pack against that exact registered repository baseline. The owner scope-lock approval is a separate requirement.
3. The certifier computes the fingerprint without writing the application repository. It binds native project identity, expected/observed repository SHA, pack hash, standard blob and gate outcomes. Store receipts in the control home, outside the certified checkout.
4. Task envelopes bind this certificate and fingerprint. Work on assignment branches can advance while the registered baseline remains unchanged. The envelope checker recomputes the registered baseline's certificate and also checks project-truth, unit, graph and technical-stack fingerprints for the candidate work.
5. Before integration, the actual `integration-admission.mjs` checks the current envelope, leases, deterministic result, candidate tip, execution receipt, independent exact-head review, security findings, PR and Zuul result. The candidate's own implementation commit does not itself have to equal the original registered baseline.
6. After an admitted merge advances the registered checkout, the existing pack is stale. `rebaselineDevelopmentPack` creates a new revision/history entry and calls `initialArtifacts(project)`, setting maturity to DRAFT and build_ready false. It does **not** automatically carry prior evidence into the new pack as current proof.
7. Rebaseline and re-establish the relevant F0–F15 evidence for that new baseline before issuing subsequent envelopes. Prior immutable pack history can support review, but reuse must be explicitly checked against the new source/scope. Old certificates and envelopes cannot silently become valid for the new baseline.

This is an evidence refresh requirement at integration boundaries, not a permanent prohibition on implementation commits. Existing concurrent envelopes tied to an older baseline may become stale after another wave merges and must follow the native revalidation/reissue process. There is no observed automatic evidence-preserving rebaseline implementation in the inspected path. Before parallel development, the native operator must establish the actual integration/revalidation policy; keeping the registered checkout artificially stale would hide integrated reality.

Do not invoke rebaseline merely to inspect state: it writes a new native pack revision and resets its evidence. Read-only evaluation and the prepared native readback are sufficient for diagnosis.

## Scope-lock approval semantics

The existing `verifyRootAuthorityEvidence` verifies an Ed25519 estate-root signature, protected storage, record kind, validity interval and every supplied binding. It is a general verification primitive, not a scope-lock policy.

The inspected consumer of `DDS_OWNER_SOURCE_AUTHORIZATION_V1` is memory admission. It binds project_id, authorization_ref, authorization_sha256 and owner_instruction_sha256; the referenced authorization must have an ancestor base_sha. It does **not** itself bind a scope_lock_sha256 field or interpret the approval's purpose. The F15 certifier does not call that source-authorization consumer. Consequently an existing source-change authorization is insufficient proof of scope-lock approval.

Recommended next action: use the estate's existing owner signing mechanism only after the native reviewer identifies a supported scope-approval consumer. If none exists, propose a small explicit adapter using the existing root verifier. The adapter must bind canonical native identity, exact scope-lock path/digest/revision, selected package digest, reviewed baseline and the owner instruction's explicit approval purpose. It must reject a source-change authorization with no scope approval, a different lock/package/project, stale or revoked evidence, invalid signatures and an unrelated instruction. This is a proposed contract requirement, not an invented deployed signing format.

Neither a chat authorization receipt nor a fingerprint substitutes for that approval. No historical authorization record was edited to add base_sha or a new meaning.

## Actual access in this continuation

The available tool catalog exposes cloud environment tools and no DIAL, Commander, Oracle or Artemis entrypoint. Runtime metadata reports no secret bindings or outbound identities. No remote host route was attempted without a configured binding. The previous Claude session's Commander rejection is historical evidence, not a new rejection in this session.

GitHub Git and ordinary repository/PR/Actions read operations work through the managed integration. Repository secret administration and DDS deploy-key listing return HTTP 403 `Resource not accessible by integration`, despite the repository metadata's admin permission flags. Those flags do not establish permission to perform these API operations. No credential was created, extracted, or broadened.
