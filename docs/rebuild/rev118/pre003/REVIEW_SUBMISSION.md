# PRE-003 independent-review submission — VAN Rev1.18

Prepared by the lead (Opus 5.5) on 2026-10-21 for the **independent** F15 reviewer. This is a submission, not a certificate. The lead has not issued, and cannot issue, F15, PRE-001/PRE-002 acceptance or an owner signature.

## 1. What is being certified, and by whom

**Contract (VAN package).** PRE-003 exit: "Independent verifier issues current project-scoped F15; all preparation blockers closed; owner signature valid. No Android or production readiness claim." The merged obligation adds: "Trusted issuer verifies exact source/scope and owner signature. A generated JSON PASS, hash or this pack checker cannot issue F15." Master §17 makes F15 the last of F0–F15; no actor may issue its own independent certificate.

**Issuer (DIAL native, read from source at dial-development-system `origin/master` 204f2f3b).**

| Element | Concrete mechanism | Source (blob) |
|---|---|---|
| Certifier | `agent-system/bin/predevelopment-forensic-gate.mjs --project <slug>`, run on the DIAL control host (`DIAL_CONTROL_HOME`) | `ec3e5116` |
| Standard | `agent-system/registries/FORENSIC_DEVELOPMENT_STANDARD.json` (`status: LOCKED`, `certificate_status: FORENSIC_BUILD_READY`, project certificate source `PROJECT_SCOPED_DEVELOPMENT_PACK`) | `eaf04c6d` |
| Gate rules F0–F15 | `agent-system/orchestration/development-pack-gates.mjs`. F15 passes only if every applicable F0–F14 gate is PASS, `forensic_predevelopment.preparation_blockers` is empty, `runtime_qualification_separated === true` and `certificate_binding_defined === true` | `534dc8dc` |
| Inputs | Registered project (`<control_home>/operations/project-registry.json`) and its pack at `<control_home>/projects/<slug>/development-pack/pack.json`. Fails closed on standard missing or unlocked, project unregistered, `pack.project.project_id` ≠ registry id, repository HEAD ≠ `pack.artifacts.baseline.repository_sha`, a missing governing doc, or a blocked gate | same |
| Output | A certificate object whose `fingerprint` is SHA-256 over its core (project, standard, pack hash, repository SHAs, gate states, blockers). **This is a deterministic hash, not a cryptographic signature**; the code checks no signature | same |
| Owner signature | Not checked by the DDS certifier. Required by the VAN contract (PRE-003 exit; OQ-05 "exact product/lock signature for formal predevelopment"). The package prepares `plan/PROPOSED_SCOPE_LOCK.json` with `signature: null`, `status: PREPARED_PENDING_OWNER_SIGNATURE`, stating that "the existing trusted owner signature/promotion process" establishes authority. No other signature format is specified, so this submission invents none | package |

**Review procedure implied by those sources:**
1. Register `van` on the control host if absent. VAN is a seed project in `UNIVERSAL_PROJECT_REGISTRY.json` with `repository.mode` = dedicated, so it is not auto-seeded as a monorepo entry.
2. The independent reviewer populates the VAN project pack's forensic fields from evidence they have checked themselves (§3), setting `baseline.repository_sha` to the exact commit under review.
3. The owner signs the scope lock through the existing trusted owner process.
4. Run the certifier. Only a `FORENSIC_BUILD_READY` certificate for the current baseline counts; any later commit makes it stale (`PROJECT_BASELINE_STALE`).

## 2. Exact identities

| Item | Value |
|---|---|
| Repository / branch under review | `Vanguduza/Van` `ccr-9e07e1af-8mgz1p` (pin the commit containing this file with `git rev-parse`) |
| Source candidate (consolidation) | `b02075f327ea8180ab6d269eba358cf8c5479878` |
| Rev1.18 package tree / archive SHA-256 | `ac0226a22a95f51642cfeb37b3709b40f7cacf10` / `6c7c7c1cb4fbd4748c0d63ceb2add9bd460778b66fb3b2302e16de09ac3a57a8` |
| Blueprint delivery commit | `3c3379bd791f7bda7ab66c21bba550d6077ba853` (package byte-identical) |
| Rebuild evidence file hashes | `SUBMISSION_MANIFEST.json`; verify with `python3 tools/rebuild/manifest.py check` |
| DDS source-contract pin used by VAN tests | `64d6b7158c723b7700e5b53175ea8048d4e92d00` (predates the Artemis adapter move; see PRE-001 dispositions) |

## 3. Evidence offered (re-derivable)

| Claim | Command | Last observed |
|---|---|---|
| Archive, package and receipt identity | `sha256sum <zip>`; `git diff --quiet 3c3379bd HEAD -- <package>` | match |
| Documentary package checks | the ten commands in the owner prompt | all exit 0 (26/26, 79/79, 47/47, 36/36, 35/35, 900 members) |
| Consolidation inputs and branch preservation | `python3 tools/consolidation/verify.py` | zero findings |
| PRE-001 inventory, dispositions and classification | `python3 tools/rebuild/pre001.py check` (needs an unshallowed clone and fetched `refs/pull/*`) | no drift; refs 0 open, overlap 0 open, 0/2,131 unclassified, 5 trace findings (AP-001) |
| PRE-001 oracle strength | `python3 tools/rebuild/pre001.py selftest` | 15/15 induced failures rejected |
| AP-001 omission and patch | `python3 tools/rebuild/ap001.py check` / `selftest` | 5 omissions detected; patched view clean (1,610→1,624); 9/9 |
| Cited baseline behaviour | `pre001/TEST_EVIDENCE.json` | 292 + 47 (+1 after installing rsync) + 9 passed; Android JVM tests not rerun here |
| Rebuild oracle regression | `pytest tests/rebuild` | 5 passed |

## 4. Unresolved findings the reviewer must decide

1. **AP-001**: five gate units (BQ-003, BQ-004, QA-002, QA-003, REL-002) have no acceptance in the admitted package. PRE-001 stays OPEN until AP-001 is admitted or otherwise resolved. **Preparation blocker.**
2. **Project identity**: the package's `project_id` is `16f2f43a-8d8b-4f18-a6ac-5bd8df620414`, while the DDS registry id is `van`. The certifier fails on mismatch. Native readback was impossible from this session (no Global DIAL/Oracle tool). **Preparation blocker.**
3. **Independent challenge** of all 324 requirements, 93 features, 171 atoms and 349 actions (all graded pending independent review or admission). PRE-002 cannot exit without it.
4. **Owner signature** on the scope lock (OQ-05) and the remaining owner questions by gate (`pre002/OWNER_DECISION_REGISTER.json`).
5. **Observations for owning units** (not F15 blockers unless the reviewer rules otherwise): OBS-001 debug-build app-wide cleartext (BE-002); OBS-002 idempotency stale-claim retake relies on mission dedup (BE-003); OBS-003 no positive "approval resumes the same browser task" test (BE-028); OBS-004 committed SQLite schema snapshot (BE-003).
6. **Inferred dispositions**: PR-22, PR-40/41/43/44 and the ConnectedRoute row rest on PR titles and sequence rather than line-level proof (`basis: INFERRED`). The reviewer may require deeper evidence.
7. **Main admission** (Project Truth trusted base, PR #94, then PR #104) is separate from F15 but blocks merging any of this. See `../ADMISSION_STEPS.md`.

## 5. Explicit non-claims

- No application code was changed.
- No Rev1.18 acceptance identity was executed; all 1,610 remain NOT_RUN.
- No deployment, provider, device, financial or live effect occurred.
- No certificate, signature, independent review or regrading of the package was produced.
