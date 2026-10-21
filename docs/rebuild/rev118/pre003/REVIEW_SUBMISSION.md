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
| PRE-001 oracle strength | `python3 tools/rebuild/pre001.py selftest` | 20/20 induced failures rejected (incl. 5 symbol-verification cases) |
| Symbol-level preservation | `pre001/SYMBOL_DISPOSITIONS.json` checked into `pre001/SYMBOL_VERIFICATION.json` by `pre001.py generate` (AST-qualified Python names, kind-aware Kotlin) | 116/116 verified; cross-repo moves cite DDS `2964c6ec` |
| AP-001 omission and patch | `python3 tools/rebuild/ap001.py check` / `selftest` (generic: gate-coverage regression against the admitted plan, new non-ancestor listings, co-listings without owner addition, unspecified fields) | 5 omissions detected; patched view clean (1,610→1,624); 13/13 |
| AP-001 admission dry run | `python3 tools/rebuild/ap001_dryrun.py <copy>` | all 10 package checks exit 0 on the amended copy; 19 files change (`pre002/AP-001/DRYRUN_RESULT.json`) |
| Cited baseline behaviour | `pre001/TEST_EVIDENCE.json` | 292 + 47 (+1 after installing rsync) + 9 passed; Artemis contracts 38/38 with the DDS sibling; Android JVM harness 1,273/1,273 (JVM only, not instrumentation or handset) |
| Rebuild oracle regression | `pytest tests/rebuild` | 7 passed |
| F15, reviewer, signature and identity requirements | `pre003/F15_AND_IDENTITY_REQUIREMENTS.md` | read from DDS source; native state not readable here |
| Observation obligations | `obligations/OBLIGATIONS.json` | OBL-001…005, author-prepared |
| Requirement challenge dossiers | `python3 tools/rebuild/pre002_dossiers.py check` / `selftest` | 324 dossiers, no drift; 11/11 |

## 4. Unresolved findings the reviewer must decide

1. **AP-001**: five gate units (BQ-003, BQ-004, QA-002, QA-003, REL-002) have no acceptance in the admitted package. PRE-001 stays OPEN until AP-001 is admitted or otherwise resolved. **Preparation blocker.**
2. **Project identity**: the package label is `16f2f43a-8d8b-4f18-a6ac-5bd8df620414`; the DDS registry assigns `project_id = previous?.project_id || slug` (expected `van`). Mapping defined (pack uses the registry id, UUID kept as an alias), pending native readback of `operations/project-registry.json`. See `F15_AND_IDENTITY_REQUIREMENTS.md` §2. **Preparation blocker.**
3. **Independent challenge** of all 324 requirements, 93 features, 171 atoms and 349 actions (all graded pending independent review or admission). PRE-002 cannot exit without it. Author-prepared dossiers for the 324 requirements are in `../pre002/challenge/` (`SUMMARY.md` first); they are inputs to the challenge, not the challenge.
4. **Owner signature** on the scope lock (OQ-05) and the remaining owner questions by gate (`pre002/OWNER_DECISION_REGISTER.json`).
5. **Observation obligations** (not F15 blockers unless the reviewer rules otherwise), now testable contracts in `obligations/OBLIGATIONS.json`: OBL-001 debug cleartext to every host (BE-002/REL-001); OBL-002 stale-claim retake with an unhandled unique-index race (BE-003); OBL-003 positive approval-resume path untested (**BE-025**, corrected from BE-028); OBL-004 importing `van_gateway.app` writes `data/` beside the tracked snapshot (root cause reproduced; BE-003); OBL-005 Android instrumentation and handset evidence.
6. **Dispositions**: no `INFERRED` basis remains. PR-22 is compared line by line with PR-23 (185/186 lines, the difference being the ColumnScope fix); PR-40/41/43/44 and ConnectedRoute are read from their diffs.
7. **Main admission** (Project Truth trusted base, PR #94, then PR #104) is separate from F15 but blocks merging any of this. PR #104's CI on `b02075f3` is red in four jobs; diagnosis and proposed fixes are in `../ADMISSION_STEPS.md`.
8. **OQ-05 mechanism**: the owner must choose which existing signed record carries scope-lock approval (`F15_AND_IDENTITY_REQUIREMENTS.md` §5).

## 5. Explicit non-claims

- No application code was changed.
- No Rev1.18 acceptance identity was executed; all 1,610 remain NOT_RUN.
- No deployment, provider, device, financial or live effect occurred.
- No certificate, signature, independent review or regrading of the package was produced.
