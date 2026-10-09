# OWNER DECISION 2026-09-30 — OWNER_DERIVED treatment of the remaining files, and ledger enforcement

Status: OWNER ANSWER RECORDED VERBATIM.

Channel: owner answer in Claude Code session `session_01ELKqm4GCPmPvF3ggKkgB1J`, 2026-09-30.
No device, biometric or cryptographic signature is claimed. This is not signed-ingress evidence
(owner decisions 2026-09-29 section 2 keep `SIGNED_INGRESS_PENDING`).

Related records:
- `docs/decisions/OWNER-DECISION-20260930-BROWSER-TASK-SCOPE.md` (Programme B branch only): the
  same session's earlier answers A and B. Answer B created
  `auth-20260930-owner-derived-programme-b-browser-deploy`.
- `docs/project-state/MISSION_PROVENANCE_MEMORY_FABRIC_JEV_20260929.md`: the mission-level owner
  authorization for Programme A (`auth-20260929-owner-memory-fabric-rev1-2`) and Programme B
  (`auth-20260929-owner-jev-openmuse-convergence-r1`). Both of those records live in DDS, not VAN.

## 1. The questions put to the owner

1. Unit G6c reported 69 files touched by Programme B commits `a16f7cb..fbe5502e` that the
   OWNER_DERIVED browser/deploy authorization does not cover (the Jev transplant `jev/*`,
   `trading/`, `hermes/`, `android/`, `tools/`, `storage/db.py`, `config.py`, `verification/*`,
   `deploy/van-browser-stream`, `deploy/van-trading-core`, ...). Should they get the same
   OWNER_DERIVED treatment?
2. VAN's `docs/project-state/LOCAL_CHANGE_LEDGER.jsonl` is not enforced by any checker (DDS has
   `scripts/project_truth_local.py`). Should enforcement be added?

## 2. Owner answer (verbatim)

> Yes to owner derived treatment and  enforce van's ledger

The double space is the owner's and is preserved.

sha256 (UTF-8, exact characters between the quotes, no newline):
`1fb51f92482bc51e4c6d7fc1ef508b3070a56c0d024dd773927367162ce72dfb`

The integrator's scratch note containing the question and this answer had sha256
`a63bfa948256013bd8fec8d469b8c387b5478daa4d7051b27237dfceb7e094e5` when this record was written.

## 3. What is decided

- **OWNER_DERIVED treatment.** The 69 files are recorded under `OWNER_DERIVED` authority whose
  parents are this answer and the Programme B mission authorization
  (`auth-20260929-owner-jev-openmuse-convergence-r1`). Record:
  `auth-20260930-owner-derived-programme-b-remaining` (Programme B branch). It lists 73 files:
  the 69, plus 4 paths the range deleted when it moved `deploy/van-trading-core/browser/` to
  `deploy/van-browser-core/browser/`. The list of 69 was built with `git log --name-only`,
  whose rename detection reports only the new path of a move; the ledger digest uses
  `--no-renames`, under which the deleted old paths are changed files too.
- **Ledger enforcement.** VAN's ledger is enforced by `tools/ci/project_truth_ledger.py`, the
  `.githooks/` hooks and a pull-request CI job. Record:
  `auth-20260930-owner-van-ledger-enforcement` (both programme branches).

## 4. How unit G7 applied it to Programme A — integrator reading, not a further decision

The first question named only Programme B. Applying enforcement to the Programme A branch meant
every Programme A commit after its baseline needed a covering authorization, and VAN had none.
The Programme A mission authorization (`auth-20260929-owner-memory-fabric-rev1-2`, DDS) records
only an excerpt of the owner's message, and its `owner_instruction_sha256`
(`deed94bc…`) is not the sha256 of that excerpt (`509542f7…`), so the owner instruction is not
recorded verbatim with a reproducible digest. The Programme A record is therefore
`OWNER_DERIVED` under this answer plus the mission authorization, not `OWNER_EXPLICIT`:
`auth-20260930-owner-derived-programme-a-memory-fabric` (Programme A branch).

## 5. Limits

- No signature of any kind is claimed.
- The OWNER_DERIVED records cover only the listed files in the listed commit ranges. They may
  not redefine product, business, security, legal, money/custody, locked-provider or
  owner-control intent. They are not reusable and open no production activation gate.
- This answer does not confirm the integrator's interpretation of the 2026-09-30 browser-scope
  answer (the section 3 reading in `OWNER-DECISION-20260930-BROWSER-TASK-SCOPE.md`).
- Commits between the last ledger change (`9237c88b`, 2026-09-18) and each enforcement baseline
  have no rows. They are recorded as an unenforced gap in
  `registries/project_truth_ledger_baselines.json`; no rows were fabricated for them.
