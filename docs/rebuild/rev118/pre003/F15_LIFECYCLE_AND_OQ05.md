# F15 certificate lifecycle and the OQ-05 signing mechanism (traced from DDS source)

Source: `Vanguduza/dial-development-system` `origin/master` `204f2f3b`: `agent-system/bin/predevelopment-forensic-gate.mjs`, `agent-system/orchestration/{task-execution-envelope,development-pack-compiler,integration-admission,root-authority-evidence,memory-admission}.mjs`, `agent-system/hooks/pre-tool-guard.mjs`, `agent-system/registries/FORENSIC_DEVELOPMENT_STANDARD.json`, and the governing guide `docs/dial/final-audit/06_DEVELOPMENT_SYSTEM/PRD_TO_DETERMINISTIC_DEVELOPMENT_PACK_PROJECT_PREPARATION_GUIDE_REV_2.md` (§19, §22, §25, §26). Read from code, not observed on the control host. Author-prepared; not a certificate.

## 1. What the certificate binds

`evaluatePredevelopmentForensicReadiness` builds a certificate core and fingerprints it with SHA-256 (no signature). It binds:

| Field | Value |
|---|---|
| `repository.observed_sha` | `git rev-parse HEAD` in the **registered `repo_dir`** on the control host |
| `repository.expected_sha` | `pack.artifacts.baseline.repository_sha` |
| `development_pack.content_sha256` | SHA-256 of the whole pack JSON (all F0–F14 evidence, identity, blockers) |
| `standard_blob` | git blob of `FORENSIC_DEVELOPMENT_STANDARD.json` in the DDS checkout |
| `gates`, `preparation_blockers`, `project_id`, `runtime_qualification` | as evaluated |

**Package digest:** the certificate does not bind the VAN package directly. It binds it only through the pack's content hash, so the pack's F0/F2 artifacts must record the package tree and archive digest (`ac0226a2…` / `6c7c7c1c…`, or the AP-001-amended Rev1.18.1 digest `8eb76af5…` from `pre002/AP-001/CANDIDATE_VERIFICATION.json`). Recommendation: put them in F0 (`exact baseline: Product Truth revision/hash`, guide §4).

## 2. Where it is stored

The certifier **does not persist** the certificate. It is recomputed on demand from `<DIAL_CONTROL_HOME>/projects/<slug>/development-pack/pack.json`, whose revisions are kept in pack history and `events/development-pack.jsonl`. The certificate hash and fingerprint are copied into each task execution envelope (`predevelopment_certificate_hash`, `predevelopment_fingerprint`), which the control plane stores.

## 3. How issuance avoids invalidating its own baseline

The pack and every certificate input live in the control home, **outside** the certified repository, so certifying writes nothing to `repo_dir`. The VAN-side consequence is that **nothing may be committed to the registered `repo_dir` between populating the pack and tasks branching**. Certification receipts recorded in the VAN repository would move HEAD and make the certificate `PROJECT_BASELINE_STALE`. Receipts belong in the control home, or in a later commit that is followed by an explicit rebaseline.

## 4. What forces reissue

Any of these changes the certificate or fails it closed:
- the HEAD of the registered `repo_dir` moves (any commit, merge, pull or checkout) → `PROJECT_BASELINE_STALE`;
- pack content changes → new `content_sha256` → new fingerprint; envelopes then fail `FORENSIC_CERTIFICATE_CHANGED` / `FORENSIC_PREDEVELOPMENT_CHANGED`;
- standard version or blob changes → `FORENSIC_STANDARD_CHANGED`;
- project identity changes → `FORENSIC_PROJECT_CHANGED` / `PROJECT_IDENTITY_MISMATCH`;
- any F0–F14 gate or preparation blocker changes;
- VAN additionally: a relevant source, policy or scope amendment invalidates affected receipts (AP-001 admission changes the package).

## 5. Relation to authorized development afterwards

The contract is **not** a permanent freeze:
- Guide §26: normal development requires `PREDEVELOPMENT_FORENSIC_GATE = GREEN`, execution-fabric gate green, VEKL binding current and task envelope current.
- Guide §22: an existing project receives a forensic audit "before the next material development wave". Certification is per development wave.

Mechanically, from the code:
1. A task envelope is created only while the gate is GREEN, so `repo_dir` HEAD must equal the baseline.
2. Tasks execute in Orca worktrees on assignment branches, so the registered `repo_dir` HEAD does not move while they work.
3. `pre-tool-guard` and `integration-admission` re-check the envelope before guarded tool use and before merge.
4. After a merge, the next envelope requires the registered `repo_dir` to still be at the certified baseline. Once that checkout advances to the merged head, the certificate is stale.
5. The only code path that moves the baseline is `rebaselineDevelopmentPack`. It **resets every artifact to `initialArtifacts(project)`** (maturity DRAFT, `build_ready: false`), so a new wave needs the F0–F14 evidence repopulated and F15 re-run.

**Finding (code as written):** no code carries still-valid evidence forward across a rebaseline. Each wave re-certifies from an empty pack. This is an operating cost, not a prohibition. Whether a wave is one unit or a batch of dependency-ordered units is decided when the registered checkout is advanced; this document does not choose it.

## 6. Does merging the consolidation change the certified identity?

- The **project identity** (`project_id`) is unchanged by merging.
- The **baseline SHA** does change: PR #94, PR #104 and this evidence branch each move `main`.

So F15 must be computed at the post-merge commit. Recommended order:
1. Adopt PR #94 and merge PR #104 and this branch through admission.
2. Admit AP-001 (Rev1.18.1) or reject it.
3. Freeze `main` at that commit.
4. Populate the pack against that SHA, recording the package digest in F0.
5. Run the certifier.
6. Branch the first wave from that SHA, with no intervening commits to the registered checkout.

## 7. OQ-05: the supported signing mechanism

The existing estate signing path is `verifyRootAuthorityEvidence` (`root-authority-evidence.mjs`):
- records are issued by `ESTATE_ROOT_BROKER` and Ed25519-signed over canonical JSON with the key at `/etc/dial-control/estate-owner-approval.pub`;
- they are stored root-protected at `/var/lib/dial-estate-authority/evidence/<sha256>.json`;
- they are time-bounded and checked against caller-supplied bindings.

The one owner-authorization record kind already defined is **`DDS_OWNER_SOURCE_AUTHORIZATION_V1`**. `memory-admission.mjs` verifies it with these bindings:
- `project_id`;
- `authorization_ref`, a `docs/project-state/authorizations/auth-*.json` file at repository HEAD;
- `authorization_sha256`, over that file's bytes;
- `owner_instruction_sha256`.

The referenced file must have `authority: OWNER_EXPLICIT`, `revoked: false`, a matching `project`, and a `base_sha` that is an ancestor of HEAD.

**Recommendation (owner decides):** carry the scope-lock approval with this existing mechanism, with no new signature scheme.
1. The owner gives an explicit instruction approving the scope lock. It names the scope-lock file SHA-256, the package tree/archive digest (Rev1.18 or Rev1.18.1) and the reviewed repository SHA.
2. That instruction is recorded verbatim as a Project Truth authorization record (append-only intake commit). Unlike VAN's existing records, it must include `base_sha`, which DDS verification requires.
3. The owner's estate-root signer issues a `DDS_OWNER_SOURCE_AUTHORIZATION_V1` evidence record binding `project_id=van`, the record path, its SHA-256 and the instruction SHA-256.
4. The F15 reviewer verifies it with `verifyRootAuthorityEvidence(..., recordKind: 'DDS_OWNER_SOURCE_AUTHORIZATION_V1', bindings)`.

Caveats:
- DDS code currently consumes this record kind only for memory admission. Using it for scope-lock approval is a recommendation the owner adopts, and the PRE-003 verifier must call the check explicitly. The certifier does not.
- The lead cannot issue or simulate this record. Signing requires the estate-root signer.

## 8. Independent reviewer eligibility (unchanged)

An approval counts only with a root-signed `DDS_REVIEWER_IDENTITY_V1` binding project, checkpoint, review job, reviewer harness, reviewed SHA, receipt hash, provider, model and native action (`review-fabric.mjs`). The author harness or a renamed same worker is not independent, so this session's subagents and second conversations are ineligible.
