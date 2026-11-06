# DIAL Hermes–Orca Symbiotic Multi-Harness Development Fabric
## PRD → Deterministic Development Pack — Rev 2 (Consolidation Route)
### Repository-grounded audit of Rev 1 and the recommended path to make it canonical

**Pack ID:** `DIAL-HERMES-ORCA-MULTI-HARNESS-DDP-R2`
**Supersedes as working draft:** `DIAL-HERMES-ORCA-MULTI-HARNESS-DDP-R1` (retained verbatim beside this file as provenance, sha256 `818c26e75cd4499829b0797740c3d5eb5fdc39dcbf86a2fce99886f2cb2481ae`)
**Prepared:** 2026-09-23 on branch `claude/plan-audit-review-p8i1uc`, base `master@1405daaa4b21b9ae35374282b191475e5bcc3ff6`
**Project:** `dial-development-system` (classification `DEVELOPMENT_SYSTEM`, per the universal project registry in the PR #54 lineage)
**Governing standards:** FFDRM-R1 / PRD-DDP-R2 (`DEC-045`), universal Development Pack (`DEC-044`), external-reference policy (`DEC-039`, PR #54 lineage), DIAL/DDE independence (`DEC-043`), AEF/HCX (`DEC-028`), runtime lock and fallback (`DEC-021`, `DEC-022`), Project Truth protocol.

| State | Value |
|---|---|
| Blueprint state | `REPOSITORY_GROUNDED_CONSOLIDATION_PROPOSAL` |
| Owner intent | Rev 1 is the intended canonical setup (owner instruction, 2026-09-23) |
| Canonical decisions written | **none** — §7 lists the decisions that must be locked, with recommendations |
| FORENSIC_BUILD_READY / BUILD_READY / RUNTIME_QUALIFIED / PRODUCTION_QUALIFIED / OWNER_ACCEPTED | `false` / `false` / `false` / `false` / `false` |

> **Superseded in part (2026-09-23):** owner decisions recorded in Rev 3 (`…_REV_3_OWNER_DECIDED.md`) replace this file's recommendations OD-1 (Astra identified), OD-2 (Orca = `stablyai/orca`), OD-3 (Orca mandatory, one integrated code path, with no native fallback path) and OD-4 (VAN design finalised in DIAL). Rev 2's evidence, findings and Checkpoint 0 procedure still apply.

> This document does not change a registry, decision or gate. It establishes how Rev 1 is best achieved against what the repository actually contains, corrects the Rev 1 statements that repository evidence contradicts, and replaces Rev 1's DU list and implementation order with a consolidated one. Where this file and Rev 1 disagree, this file carries the repository evidence; where they agree, Rev 1's wording stands.

---

# 0. Verdict

**Consolidate, do not rebuild.** Rev 1's architecture is sound and matches the direction of DIAL's locked decisions. But Rev 1 was written as if most of the fabric were new. Probing the three lineages shows most of it already exists, and some of Rev 1 contradicts decisions already locked:

- **Already implemented, reuse as-is or with small extensions:** Task Execution Envelope, HCX, worktree leases and fencing, token compute governor, execution receipts, SPMRF (both lineages, nearly identical), OpenViking projection including the exact `viking://` namespace Rev 1 specifies, ARTEMIS behind `dial_android_testing`, Review Fabric, repository-understanding snapshots, state-aware housekeeping, the Development Pack compiler with FFDRM F0–F15, the project registry that classifies VAN and DDE, and the Antigravity adapter.
- **Genuinely new:** machine-driven Stage Graph dispatch, ActiveWorkGraph read model, ExecutionIntent, progress events, CommanderAuthorityLease (expiry/revocation), host placement governor, the Orca adapter and workspace binding, and the VAN development surfaces.
- **Contradictions in Rev 1 that must be corrected before it can be canonical:** 7 blocking items (§2), including the lineage map, the DDE coupling, the "Compute Governor" name collision, Orca's criticality, and an unnamed Orca upstream.

The single largest risk is not Orca. It is **Checkpoint 0**: the two retained lineages do not merge cleanly (37 conflicting files), and both assign `DEC-039` to different decisions. Everything else waits on that.

---

# 1. Evidence baseline (re-derivable)

Every number below comes from a command run on 2026-09-23 against `origin` refs. Lineage aliases: `A = origin/gpt/netcup-hermes-control-integrated-20260921` (PR #45 head `c517b127`), `B = origin/gpt/ffdrm-development-system-rebase-20260922` (PR #54 head `ae9e5d52`).

| # | Claim | Command | Result |
|---|---|---|---|
| E1 | master SHA matches Rev 1 | `git rev-parse origin/master` | `1405daaa…` ✔ |
| E2 | PR #54 is stacked on PR #50, not master | PR #54 `base.ref` | `gpt/dial-all-work-consolidation-20260922` (PR #50, open) |
| E3 | PR #50 content is inside PR #54, not PR #45 | `git merge-base --is-ancestor` | PR50⊂PR54 **yes**; PR50⊂PR45 **no** |
| E4 | Lineage size | `git rev-list --count master..X`; `git diff --shortstat master...X` | A: 9 commits, 171 files; B: 359 commits, 305 files |
| E5 | Lineages overlap | `comm -12` of changed-file lists | **112** files changed in both |
| E6 | Lineages conflict | `git merge-tree --write-tree A B` (and `B A`) | exit 1, **37** conflicted files (10 `agent-system/orchestration`, 8 `deploy/netcup`, 4 registries, 3 project-state, 3 workflows, 3 `deploy/oracle`, 2 bootstrap, `package.json`, `vitest.config.ts`, one test, `estate-topology.json`) |
| E7 | Decision-ID collision | `DECISION_LOG.json` in A and B | A `DEC-039` = *state-aware housekeeping*; B `DEC-039` = *external repositories are reference/inspiration only*. B also holds `DEC-040..045` |
| E8 | Cost of renumbering | `git grep -l DEC-039` | A: **2** files; B: **44** files |
| E9 | Concept presence | `git grep -Il <term>` per ref | SPMRF master 0 / A 18 / B 11; OpenViking 0/12/0; ARTEMIS 0/19/0; FFDRM 0/0/19; Stage Graph, ActiveWorkGraph, ExecutionIntent, CommanderAuthorityLease: **0 everywhere** |
| E10 | SPMRF divergence between lineages | `git diff --stat A B -- shared-project-memory.mjs shared-context-resolver.mjs …` | **36 lines** (A adds `TEST_EVIDENCE` and the OpenViking hook in the resolver) |
| E11 | Rev 1 OpenViking namespace already exists | `git grep viking:// A` | `openviking-shared-context.mjs:76` builds `viking://user/<user>/memories/dial-projects/<project>` |
| E12 | SPMRF admission authorities already exist | `shared-project-memory.mjs:28` (A) | `OWNER_EXPLICIT`, `VERIFIED_SYSTEM`, `HERMES_RECONCILED` |
| E13 | Leases/fencing already exist on master | `worker-lease-manager.mjs` exports | `issueWorktreeLease`, `assertWorktreeLease`, `closeWorktreeLease`, `revokeTaskLeases` |
| E14 | "Compute governor" already means something | `compute-governor.mjs` (master, `DEC-028`) | reserves/settles **inference token** capacity, not host placement |
| E15 | Commander authority has no lease | `grep expires_at\|lease_id\|revocation` in A `hermes-commander-*.mjs` | no matches; authority is capability-surface only (`COMMANDER_NOT_FULL_CAPABILITY`) |
| E16 | Orca's current canonical status | `REV5_1_BOOTSTRAP_POLICY.json` (A and B) | Orca is `conditional_required_gap_closure`; failure semantics `"orca": "fallback to native Commander/worktree path"` |
| E17 | Current manager lock | `agent-system/orchestration/README.md:8-13` | `gpt-5.6-sol` → `claude-sonnet-5` → `NO_HERMES_RUNTIME_AVAILABLE`; Fable/Opus explicitly may not be inserted |
| E18 | Fable pinning limitation | `claude-code-probe.mjs:180` | "Claude Code exposes models through interactive /model only… does not pin Fable 5 vs Fable 5.1" |
| E19 | Model names in Rev 1 chain | `git grep` master/A/B | `GPT-6`, `gpt-6`, `Opus 5.5`: **0** hits. `Astra`: only vehicle-catalogue names |
| E20 | Next-work selection today | `mission-controller.mjs:24` (B) | manager is *told in prose* to "continue exactly one dependency-safe, contract-first packet from the active DIAL development programme" — no machine-readable READY set |
| E21 | Mission states today | `mission-controller.mjs` (B) | `QUEUED`, `RUNNING`, `WAITING_RUNTIME`, `FAILED`, `COMPLETED` |
| E22 | VAN is a separate project | `UNIVERSAL_PROJECT_REGISTRY.json` (B) | `van` = `APPLICATION_PROJECT`; `dde` = `INDEPENDENT_DEVELOPMENT_SYSTEM_PROJECT` |
| E23 | Harness registry | `HARNESS_CAPABILITY_REGISTRY.json` (master) | `codex-sol-worker`, `claude-sonnet-worker`, `claude-sonnet-worker-secondary`, `stitch-design-provider`, `antigravity-worker` |
| E24 | Estate topology | `deploy/hybrid/estate-topology.json` (A) | also carries transient `old-dial-hermes-control` at `10.77.0.5`, with a retirement precondition on zero-touch certification |
| E25 | "Orca" is ambiguous upstream | web search 2026-09-23 (Context7 and Exa MCPs failed to connect this session) | at least `stablyai/orca`, `nwparker/orca`, `orca-cli/orca` exist, each describing parallel agents in git worktrees |
| E26 | Oracle gate right now | Oracle snapshot, 2026-09-23T16:06Z | mission `PAUSED`; gate `DEVELOPMENT_BLOCKED`, failed check `qualified_control_plane_unchanged`; Sol `ACCOUNT_LIMITED`, Sonnet `HEALTHY` |
| E27 | Other open lineages touching the same surface | PR list, `comm -12` | PR #55 (VAN Rive on Dial Control): 6 files, 3 overlap A, 3 overlap B. PR #51 (brand pack) open. PR #57 ("clean integrate", closed unmerged) was an earlier attempt at the same integration |

Not measured in this session: Orca's actual control API, licence file hash, telemetry/auto-update behaviour; whether any Fable/Astra/GPT-6/Opus-5.5 route is callable non-interactively. These are listed as open research in §7 and §8, not assumed.

---

# 2. Audit findings

Severity: **B** blocks canonical adoption; **M** must be fixed in Rev 2 before implementation; **L** is an improvement.

| ID | Sev | Rev 1 § | Finding | Evidence | Resolution in Rev 2 |
|---|---|---|---|---|---|
| F-01 | B | 01.2, 01.3 | The lineage map is incomplete. PR #54 is not "against master"; it carries all of PR #50 (the retained-work consolidation of PRs #46–#49: universal development system, VEKL motion, logo, Hermes local MCP). PR #55 and #51 are also open and unmentioned. | E2, E3, E27 | §4 Checkpoint 0 reconciles **master + PR #54 (⊃ PR #50) + PR #45 (⊃ PR #56)** and runs an inclusion check against #51, #55 and closed-unmerged #57. |
| F-02 | B | 01.3 | Reconciliation is presented as a checkpoint with no procedure. It is a 37-file conflict with a decision-ID collision. | E6, E7 | §4 gives the merge order, the conflict classes and how to resolve each. |
| F-03 | B | whole doc | `DEC-039` names two different locked decisions. Any new decision numbered after either lineage will collide again. | E7, E8 | Renumber PR #45's housekeeping decision to the next free ID (`DEC-046`): 2 referencing files against 44. Add a registry uniqueness test (§6 mutation M-22). |
| F-04 | B | 13, 25 | "DDE/runtime binding" and "FDEP/DDE" make DDE part of DIAL's frontend path. `DEC-043` (locked) says DIAL must fail certification if any required capability depends on DDE, and uses a DIAL-native production binding. | E22; DEC-043 | Replace DDE with the DIAL-native frontend production binding everywhere. Remove DDE from the tool registry (§25). |
| F-05 | B | 07, 23, 26 | Rev 1 makes Orca the execution plane ("no new Orca sessions" when unavailable). Current canon lists Orca as conditional, falling back to the native Commander/worktree path. As written, an Orca outage stops all development. | E16 | Orca is an **executor substrate** chosen per task. `worker-lease-manager` + native worktree stays the always-available baseline. Orca failure → `DEGRADED`, new work routes to native (§3.4). Whether to keep this is owner decision OD-3. |
| F-06 | B | 07, 27 | Orca is never identified. At least three upstream projects share the name, and the §07.3 adapter operations presume a control API nobody has verified. `DEC-039` (B) requires an owner adoption decision for any third-party runtime dependency. | E25; DEC-039 (B) | New DU `HOT-DU-017a` identifies the upstream and qualifies it; the adapter surface is **derived from the qualified upstream**, not fixed ahead of time; an adoption decision (OD-2) precedes install. |
| F-07 | B | 04.2 | The manager chain drops Sonnet 5, which is currently the **only healthy runtime** (E26). Three of its four names have no route evidence (E19), and Fable cannot yet be pinned non-interactively (E18). `DEC-021`'s development-ready fallback is defined against exact Sonnet 5, so dropping it silently breaks that gate. | E17–E19, E26 | OD-1: keep an exact, qualified terminal fallback (recommend `claude-sonnet-5`) before `NO_HERMES_MANAGER_RUNTIME`; amend `DEC-021`/`DEC-022` in the same decision; each slot is an exact ID with live probe evidence or it is absent. |
| F-08 | M | 20 | "Compute Governor" already exists and means token reservation (`DEC-028`). Rev 1 reuses the name for host placement. Two meanings of one name is how authority duplicates. | E14 | Rename Rev 1 §20 to **Placement Governor** (`placement-governor.mjs`). It runs before `reserveCompute`; neither replaces the other. |
| F-09 | M | 05, 06 | The Stage Graph compiler is specified as a new compiler. `DEC-044`/`DEC-045` require the Development Pack to be the **single** project-preparation substrate and forbid a parallel readiness system. The pack schema already has `implementation.dependency_dag_valid` and `atomic_packets_ready`. | DEC-044/045; schema | The Stage Graph is a **compiled artifact of the Development Pack** (`stage_plan`), produced by `development-pack-compiler.mjs`, invalidated by `invalidateDevelopmentPack`/`rebaselineDevelopmentPack`. It does not recompute readiness. |
| F-10 | M | 06, 17 | The real gap Rev 1 fixes is not stated: today the manager picks work by reading prose (E20). | E20 | State it as the purpose of Checkpoint 2: mission-controller dispatch reads `READY` nodes from the compiled `stage_plan` and the manager may only choose among them (HOT-PT-007 becomes enforceable). |
| F-11 | M | 06 | Rev 1's 11 stage/task states don't map to the 5 mission states that exist. | E21 | §3.2 gives the mapping; the Stage Graph states are the task-node states and mission states stay as dispatch/job states. |
| F-12 | M | 16, 28 | VAN is a separate `APPLICATION_PROJECT`. DU-009/010 (VAN screens) cannot be built in `dial-new` under this pack. | E22 | DIAL delivers a read-only **Development Projection API** contract (HOT-DU-008). VAN screens move to VAN's own Development Pack as `VAN-DEV-*` units that consume it. |
| F-13 | M | 09.4 | SPMRF memory admission authorities (`HERMES_RECONCILED`, `VERIFIED_SYSTEM`) sit beside Project Truth authority classes (`OWNER_*`) without saying how they relate. A reader could take "admitted memory" as Project Truth authority. | E12; PROJECT_TRUTH_PROTOCOL | Add: SPMRF admission admits **memory**, never Project Truth. Only `OWNER_*` authorization records write Project Truth. Mutation M-23 enforces it. |
| F-14 | M | 03 | Topology omits `old-dial-hermes-control` (10.77.0.5) and its retirement precondition. | E24 | Add it as `TRANSIENT_MIGRATION_SOURCE`, hard-excluded from placement like `oracle-admin`. |
| F-15 | M | 36, whole | Every control-plane change (Orca, adapters, dispatch) fails the Oracle check `qualified_control_plane_unchanged`, which is already failing. Rev 1 has no requalification step, so each checkpoint would leave development blocked. | E26; `development-unblock.mjs:86` | Each checkpoint that touches the control plane ends with an explicit **Oracle requalification window** (owner/Oracle action), and changes are batched per checkpoint to minimise windows. |
| F-16 | M | 10.3–10.4 | CommanderAuthorityLease is correctly identified as new, but Rev 1 doesn't say it extends `hermes-commander-authority.mjs`. Built separately, it would be a second Commander authority. | E15 | Extend the existing authority decision function: `REFUSE` if no current, unexpired, unrevoked lease for principal+host+capability. |
| F-17 | M | 09.11 | ExecutionIntent is specified as a separate record. Validating it "against the envelope" means it belongs inside the envelope's lifecycle. | E13; TEE | ExecutionIntent is a signed sub-record of the Task Execution Envelope (`envelope.intent`), and the envelope's fingerprint covers it. |
| F-18 | L | 04.2 | "GPT-6 Sol" vs repo's `gpt-5.6-sol`; "VEKL 2.2" vs master's VEKL Rev 2 + `DEC-024` 2.1 amendment (2.2 arrives with `DEC-028` in B). | E17, E19 | Use exact IDs only. Friendly names go in a display column. |
| F-19 | L | 23 | The failure table is missing: stale Stage Graph compile, lease-manager unavailable, placement governor unavailable, Oracle gate blocked, decision-registry conflict. | — | Added in §5. |
| F-20 | L | 30, 31 | No E2E or mutation checks Orca-absent fallback, control-plane requalification, registry ID uniqueness, or memory→truth inversion. | — | Added in §6. |
| F-21 | L | 28 | 52 DUs are listed flat, and several are one change split in two (004/005, 009/010, 030/031, 017/018). | — | §4.2 consolidates to 47 units (41 table rows), keeping Rev 1 IDs for traceability. |

---

# 3. Consolidation map — each Rev 1 element against the repository

Disposition: **REUSE** (exists, bind to it) · **EXTEND** (exists, add fields/behaviour) · **RECONCILE** (exists in both lineages, merge) · **NEW** · **MOVE** (belongs to another project) · **CORRECT** (Rev 1 contradicts canon).

## 3.1 Map

| Rev 1 element | Existing implementation (lineage) | Disposition | Work |
|---|---|---|---|
| Hermes orchestration authority | `mission-controller.mjs`, `supervisor.mjs`, `external-orchestrator.mjs` (all; conflict in 2) | RECONCILE | Checkpoint 0 |
| Manager plane, ManagerTurnEnvelope | `hermes-runtime-router.mjs` `selectHermesRuntime`, `hermes-plan-models.mjs` (all) | EXTEND | Add envelope builder; router reads the chain from the locked decision (OD-1) instead of constants |
| Manager output contract | manager instruction is prose (E20) | NEW | Typed result validated before dispatch |
| Product Truth / Development Pack / FFDRM | `development-pack-compiler.mjs`, `development-pack-gates.mjs`, `FORENSIC_DEVELOPMENT_STANDARD.json`, `predevelopment-forensic-gate.mjs` (B) | REUSE | — |
| Stage Graph schema + compiler | `DEVELOPMENT_PACK_SCHEMA.json` `implementation.*` (B) | EXTEND | `stage_plan` artifact + `compileStagePlan()` inside the pack compiler (F-09) |
| Stage/task state store | `state-store.mjs` (all) | REUSE | Store under the project's pack |
| Plan invalidation | `invalidateDevelopmentPack`, `rebaselineDevelopmentPack` (B), `revokeTaskLeases` (master) | EXTEND | Cascade: pack invalidation → node `INVALIDATED` → leases revoked → late receipts quarantined |
| Task Execution Envelope | `task-execution-envelope.mjs` (all; B adds FFDRM binding) | EXTEND | Add `stage_plan_revision`, `intent`, `executor_substrate`, `orca_workspace_id` |
| ExecutionIntent | — | NEW (inside TEE) | F-17 |
| HCX | `harness-capability-exchange.mjs`, `hcx-worker-executor.mjs`, `HARNESS_CAPABILITY_REGISTRY.json` | EXTEND | Card field `executor_substrates: [NATIVE_WORKTREE, ORCA]` |
| Compute Governor (Rev 1 §20, host placement) | `compute-governor.mjs` is tokens (E14) | CORRECT → NEW | `placement-governor.mjs` (F-08) |
| Leases/fencing | `worker-lease-manager.mjs` (master) | REUSE | Orca binding validates against it |
| Execution receipt | `execution-receipt.mjs` | EXTEND | Add workspace/substrate identity |
| Orca adapter, registry, binding | — | NEW | Gated on OD-2 and HOT-DU-017a |
| SPMRF | `shared-project-memory.mjs`, `SHARED_PROJECT_MEMORY_FABRIC.json` (A ≈ B, 36-line diff) | RECONCILE → EXTEND | Take A's superset, then add the 12 new record types |
| OpenViking projection | `openviking-shared-context.mjs`, `HERMES_ARTEMIS_OPENVIKING_INTEGRATION.md` (A) | EXTEND | Add `current-plan/`, `active-work/`, `tooling/` sub-namespaces |
| Shared context resolver | `shared-context-resolver.mjs` (A, B; conflicting) | RECONCILE → EXTEND | Add stage-plan and workspace fingerprints |
| Repository Understanding Snapshot | `repository-understanding-snapshot.mjs` (both) | REUSE | — |
| ActiveWorkGraph | parts in leases, mission state, `chatgpt-session-registry.mjs`, `review-fabric.mjs`, `ANDROID_TESTING_PLANE.json` | NEW (read model) | Derived projection; owns no state (§3.3) |
| Progress events | — | NEW | Written as SPMRF `TASK_PROGRESS` candidates |
| Two ChatGPT sessions | `chatgpt-session-registry.mjs` (both) | REUSE | — |
| Desktop Commander authority | `hermes-commander-authority.mjs`, `hermes-commander-gateway.mjs` (both) | EXTEND | CommanderAuthorityLease (F-16) |
| ARTEMIS | `ANDROID_TESTING_PLANE.json`, `dial_android_testing`, `install-artemis-android-testing-plane.sh` (A) | REUSE | Add ActiveWorkGraph projection only |
| Review Fabric | `review-fabric.mjs`, `review-coordinator.mjs`, `read-only-review-runner.mjs` (both) | EXTEND | Accept an Orca workspace checkpoint as review target |
| Frontend path | Screen Registry × Feature Graph, Stitch provider (master) | CORRECT | Remove DDE (F-04) |
| Housekeeping | `HOUSEKEEPING_POLICY.json`, `resource-lifecycle-registry.mjs` (A; conflicting) | RECONCILE → EXTEND | Add Orca workspace as a lifecycle resource kind |
| Netcup bootstrap | `deploy/netcup/hermes-control/*` (A and B; 8 conflicting) | RECONCILE → EXTEND | Orca as a conditional bootstrap capability |
| Estate topology | `estate-topology.json` (conflicting) | RECONCILE → CORRECT | F-14 |
| VAN Development Control Centre | — (VAN is a separate project) | MOVE | F-12 |
| Antigravity worker | `providers/google/antigravity-adapter.mjs`, `antigravity-worker` card | REUSE | Add Orca substrate only if qualified |

**Tally** (counted from the table above): 30 rows. REUSE 7, EXTEND 13 (4 of them after RECONCILE), RECONCILE-only 1, RECONCILE → CORRECT 1, NEW 5, CORRECT → NEW 1, CORRECT-only 1, MOVE 1. So 22 of 30 elements (about three-quarters) are reuse, extension or reconciliation of existing code, and the new work is concentrated in dispatch, ActiveWorkGraph, placement and Orca.

## 3.2 Stage Graph as a Development Pack artifact

```text
Development Pack (project-scoped, revisioned, FFDRM-gated)
  ├─ implementation.dependency_dag
  ├─ implementation.atomic_packets
  └─ stage_plan  ← NEW compiled artifact
        fingerprint = H(pack_revision, product_truth_rev, du_dag_rev,
                        feature_graph_rev, screen_graph_rev, security_profile_rev,
                        tool_capability_rev, owner_priority_rev, compiler_rev)
```

- The compiler is a pure function of the pack. The same inputs give a byte-identical `stage_plan` (test: compile twice, compare hashes).
- The compiler never computes `FORENSIC_BUILD_READY`. It reads the certificate, and material nodes stay `BLOCKED` while it is absent or stale.
- Recompilation happens only through the pack's own invalidate/rebaseline functions.

State mapping (node state vs. mission dispatch state):

| Stage/task node | Mission job state while dispatched |
|---|---|
| `NOT_APPLICABLE`, `BLOCKED`, `READY`, `WAITING_OWNER`, `WAITING_EXTERNAL` | — (not dispatched) |
| `RUNNING` | `QUEUED` → `RUNNING`; `WAITING_RUNTIME` when no manager/worker slot is healthy |
| `VERIFYING` | `COMPLETED` (worker done) + verification jobs pending |
| `PASS` | set only by gate reconciliation, never by the job |
| `FAIL` | `FAILED`, retry budget exhausted |
| `INVALIDATED`, `SUPERSEDED` | job cancelled; late receipts quarantined |

## 3.3 ActiveWorkGraph is a read model

ActiveWorkGraph owns no state. It is rebuilt from the stores that already own each fact: leases (`worker-lease-manager`), dispatch (`mission-controller`), sessions (`chatgpt-session-registry`), reviews (`review-fabric`), Android jobs (ARTEMIS plane), research jobs (VEKL), workspaces (Orca registry), and progress (SPMRF `TASK_*`). If it is lost, it is rebuilt. If it disagrees with a source store, the source wins and the disagreement is logged. This keeps HOT-PT-001 intact: there is no second scheduler, even inside the graph everyone reads.

## 3.4 Orca as executor substrate

```text
HCX selects worker (harness × model)
  → Placement Governor admits host
  → compute-governor reserves tokens
  → worker-lease-manager issues lease + fencing token   (authoritative)
  → substrate = ORCA if card allows, Orca LIVE_QUALIFIED and healthy
                else NATIVE_WORKTREE
  → substrate creates worktree; DIAL asserts path/branch/base_sha against lease
  → worker starts inside the Task Execution Envelope
```

Orca health `DEGRADED` or `UNAVAILABLE` sends new tasks to `NATIVE_WORKTREE` and marks running Orca tasks `WAITING_EXTERNAL` for reattach. Rev 1's permission hardening (§07.6) applies to both substrates.

---

# 4. Consolidated implementation plan

## 4.1 Checkpoint 0 — canonical integration baseline (procedure)

1. **Inventory.** Freeze heads: PR #45 `c517b127`, PR #54 `ae9e5d52` (⊃ PR #50 `c81ed32f`). Record PR #51, #55 and closed-unmerged #57 for an inclusion check.
2. **Branch** `integration/hot-baseline-<date>` from master.
3. **Merge PR #54 first.** master is its ancestor, so this is conflict-free and brings the larger lineage (359 commits, all 44 `DEC-039` reference-policy citations) over unchanged.
4. **Renumber PR #45's housekeeping decision** `DEC-039 → DEC-046` on a prep commit on top of PR #45 (2 files), under an owner authorization record. Check that `DEC-046` is still free first.
5. **Merge PR #45** (merge commit, no rebase, so its history stays valid). Resolve the 37 conflicts by class:
   - *Registries* (`DECISION_LOG`, `DEVELOPMENT_UNIT_REGISTRY`, `HOUSEKEEPING_POLICY`, `SHARED_PROJECT_MEMORY_FABRIC`): union by ID; any ID with two different bodies is a finding, not a pick.
   - *Project state* (`CHANGE_LEDGER.jsonl`, `CURRENT_STATE.json`, authorization records): ledger is append-only, so take the union ordered by `recorded_at_utc`; **regenerate** `CURRENT_STATE.json` with `scripts/project_truth_local.py`, never hand-merge it.
   - *Orchestration modules* (10): take B's structure (FFDRM envelope binding) and re-apply A's additions (OpenViking, ARTEMIS, Commander, recovery). SPMRF is the easy case (E10).
   - *Deploy/bootstrap/workflows* (16): take the union of capabilities; `estate-topology.json` keeps A's `10.77.0.5` transient peer (F-14).
   - *`package.json`, `vitest.config.ts`*: union scripts and test globs, then regenerate the lockfile with npm.
6. **Retained-capability regression test.** Generate a manifest from each head: exported symbols of `agent-system/**/*.mjs`, registry top-level IDs, decision IDs, test file list, workflow names. Assert every entry is present in the integration head. Before trusting it, break it on purpose (delete one A export and watch it fail).
7. **Green:** `npm run verify`, `npm run agent:project-truth:verify-pr`, both lineages' test suites, `node agent-system/bin/v2-closure-check.mjs`.
8. **Inclusion check** against #51/#55: record for each whether it is included, left independent, or needs rebase. Don't silently absorb.
9. **Requalification window** (F-15): the Oracle/owner requalifies the control-plane fingerprint on the merged SHA.

Exit: one canonical baseline SHA that every later DU forks from; PR #45 and #54 are then merged or closed with pointers to it.

## 4.2 Consolidated Development Units

Rev 1 IDs kept; `(+NNN)` shows a Rev 1 unit merged into this row. 41 rows; the last row bundles the 7 qualification units, so 47 units against Rev 1's 52 (three new: 007a, 017a, 020a).

| DU | Unit | Disposition | Depends on |
|---|---|---|---|
| HOT-DU-001 | Canonical baseline reconciliation (§4.1), incl. `DEC-039` renumber and regression manifest | RECONCILE | — |
| HOT-DU-002 | Canonical decisions OD-1…OD-6 locked (§7) | decision | 001 |
| HOT-DU-003 | Exact manager-route discovery and live qualification, one exact ID per slot | NEW | 002 |
| HOT-DU-004 (+005) | `stage_plan` artifact in `DEVELOPMENT_PACK_SCHEMA` + `compileStagePlan()` in pack compiler, deterministic-hash test | EXTEND | 001 |
| HOT-DU-006 | Node state persistence in `state-store` + the §3.2 mapping | EXTEND | 004 |
| HOT-DU-007 | Invalidation cascade (pack → nodes → leases → receipts) | EXTEND | 006 |
| HOT-DU-007a | **Mission-controller dispatch from READY nodes**; typed ManagerTurnEnvelope in, typed manager output (Rev 1 §19) out | NEW | 006, 003 |
| HOT-DU-008 | Read-only Development Projection API (contract + DIAL implementation) | NEW | 006, 011 |
| HOT-DU-009 (+010) | → **MOVE** to VAN pack as `VAN-DEV-001..` (Home, TODO/graph, Active Agents, Workspaces, Memory, Android, Evidence, Approvals) | MOVE | 008 |
| HOT-DU-011 | ActiveWorkGraph read model (§3.3) | NEW | 006 |
| HOT-DU-012 | ExecutionIntent inside TEE | EXTEND | 001 |
| HOT-DU-013 | Progress-event contract → SPMRF `TASK_*` | NEW | 014 |
| HOT-DU-014 | SPMRF Rev 2 (12 record types; memory-vs-truth rule F-13) | EXTEND | 001 |
| HOT-DU-015 | OpenViking namespaces Rev 2 | EXTEND | 014 |
| HOT-DU-016 | Shared context resolver: stage-plan + workspace fingerprints | EXTEND | 004, 014 |
| HOT-DU-017a | **Orca upstream identification + qualification** (which project, tag, licence hash, control API reality, telemetry, auto-update, remote runtime, state backup) | research | 002 |
| HOT-DU-017 (+018) | Orca pin, install, runtime on `dial-control` as a conditional bootstrap capability | NEW | 017a, OD-2 |
| HOT-DU-019 (+020) | Orca typed adapter + workspace registry; operations **derived from 017a**, not fixed ahead of time | NEW | 017 |
| HOT-DU-021 | Orca ↔ `worker-lease-manager` binding + mismatch denial | NEW | 019 |
| HOT-DU-022 | Permission hardening (both substrates) | EXTEND | 021 |
| HOT-DU-023 | HCX `executor_substrates` + native fallback (§3.4) | EXTEND | 021, 020a |
| HOT-DU-020a | Placement Governor (F-08) incl. `oracle-admin` and `10.77.0.5` hard exclusion | NEW | 001 |
| HOT-DU-024 | Claude Code worker on Orca substrate | EXTEND | 023 |
| HOT-DU-025 | Codex worker on Orca substrate | EXTEND | 023 |
| HOT-DU-026 | Antigravity worker on Orca substrate, only if qualified | EXTEND | 023 |
| HOT-DU-027 | Future-harness enrolment procedure | EXTEND | 023 |
| HOT-DU-028 | Two-ChatGPT identity mapping, verify existing registry against Rev 1 §10 | REUSE/verify | 001 |
| HOT-DU-029 | CommanderAuthorityLease inside `hermes-commander-authority` | EXTEND | 028 |
| HOT-DU-030 (+031) | Account A and B Commander bridges under lease (one DU, two hosts) | EXTEND | 029 |
| HOT-DU-032 | Cross-account context parity | NEW test | 016, 030 |
| HOT-DU-033 | Review Fabric: workspace checkpoint as review target | EXTEND | 019 |
| HOT-DU-034 | ARTEMIS → ActiveWorkGraph projection | EXTEND | 011 |
| HOT-DU-036 | Stitch → DIAL-native production binding handoff (no DDE) | CORRECT | 001 |
| HOT-DU-037 | Stagehand/Playwright projection | EXTEND | 011 |
| HOT-DU-038 | Security-specialist gates | EXTEND | 001 |
| HOT-DU-039 | Tool/provider readiness projection (INSTALLED → INTEGRATED ladder) | NEW | 011 |
| HOT-DU-040 (+041) | Orca/session observability + crash/restart/reattach | NEW | 019 |
| HOT-DU-042 | Housekeeping: Orca workspace lifecycle kind | EXTEND | 019 |
| HOT-DU-043 | Netcup bootstrap: Orca conditional capability | EXTEND | 017 |
| HOT-DU-044 | VAN Trading Core burst-worker policy (in Placement Governor) | EXTEND | 020a |
| HOT-DU-046..052 | Cross-harness E2E, memory E2E, projection E2E, mutation suite, runtime qualification, recovery qualification, owner acceptance | as Rev 1 | all above |

HOT-DU-035 (VAN ARTEMIS surface) → `VAN-DEV-*`. HOT-DU-045 is absorbed into 020a.

## 4.3 Order

```text
C0  001 baseline ─────────────────────────────── requalify
C1  002 decisions → 003 manager qualification     (parallel: 017a Orca research)
C2  Planning spine: 004 → 006 → 007 → 007a ; 011 → 008 ; 012      requalify
C3  Memory: 014 → 013, 015 → 016 ; 028 → 029 → 030 → 032
C4  Placement + substrate: 020a ; 017 → 019 → 021 → 022 → 023    requalify
C5  Workers: 024, 025, 026, 027 ; 033 ; 040 ; 042 ; 043 ; 044
C6  Specialists: 034, 036, 037, 038, 039
C7  VAN project pack consumes 008 (separate project, own FFDRM)
C8  046 → 047 → 048 → 049
C9  050 → 051 (deploy exact merged SHA, prove recovery) → 052
```

C2 delivers most of Rev 1's value with **no Orca at all**: dispatch becomes deterministic, the manager can only choose READY nodes, and ActiveWorkGraph shows the live state. Orca then sits under an already-deterministic system, so a failed Orca qualification does not stall the programme.

---

# 5. Failure/recovery additions to Rev 1 §23

| Failure | Required response |
|---|---|
| `stage_plan` stale against pack fingerprint | No dispatch; recompile through the pack; running tasks continue to their safe boundary, results quarantined if affected |
| Stage compiler error | Keep last valid `stage_plan` read-only; no new dispatch; owner-visible blocker |
| `worker-lease-manager` unavailable | All writes denied (fail closed); reads continue |
| Placement Governor unavailable | No new placement; running work continues |
| Orca unavailable | New work routes to `NATIVE_WORKTREE`; Orca tasks `WAITING_EXTERNAL` for reattach (replaces Rev 1's row) |
| Oracle gate `DEVELOPMENT_BLOCKED` | Mission paused; owner requalification required; no local workaround |
| Decision-ID collision detected | Registry verification fails; no merge |
| ActiveWorkGraph disagrees with a source store | Source wins; rebuild; log discrepancy |
| Manager output fails schema | Turn rejected; same envelope retried once on the same slot, then next qualified slot |

---

# 6. Added E2E and mutations

**E2E**

- HOT-E2E-16 — *Orca absent:* Orca stopped mid-programme; new READY task runs on `NATIVE_WORKTREE` with identical lease/receipt evidence.
- HOT-E2E-17 — *Control-plane change:* dispatch change merged → Oracle gate reports `qualified_control_plane_unchanged=false` → no dispatch until requalified.
- HOT-E2E-18 — *Deterministic compile:* same pack compiled on two hosts → identical `stage_plan` fingerprint.
- HOT-E2E-19 — *Manager restricted to READY:* manager output naming a BLOCKED or unknown task is rejected before dispatch.

**Mutations (certification fails if any succeeds)**

- M-22 two decision records share an ID
- M-23 SPMRF `HERMES_RECONCILED` record accepted as Project Truth authority
- M-24 Placement Governor bypasses `reserveCompute`
- M-25 Orca outage blocks native-substrate dispatch
- M-26 `stage_plan` written by anything other than the pack compiler
- M-27 DDE dependency in a required DIAL capability
- M-28 ActiveWorkGraph write accepted as a source-of-truth change
- M-29 task scheduled on `10.77.0.5` (`old-dial-hermes-control`)

---

# 7. Owner decisions required (recommendations included)

These are the decisions Rev 1 needs locked. No agent can lock them. Each would become a `DEC-*` record numbered after the Checkpoint 0 renumber.

| ID | Decision | Recommendation | Why |
|---|---|---|---|
| OD-1 | Manager chain | `Fable → Astra → Sol → Opus 5.5 → Sonnet 5 → NO_HERMES_MANAGER_RUNTIME`. Each slot is an exact model ID that has passed a live, non-interactive probe; a slot without that is absent, not guessed. Sol stays `gpt-5.6-sol` until a GPT-6 Sol ID is qualified. The same decision amends `DEC-021` (fallback gate names the new terminal slot) and `DEC-022`. | Sonnet is the only healthy runtime today (E26); removing it removes the fallback `DEC-021` depends on. "Astra" has no route evidence at all (E19): the owner should say which provider/model it means. |
| OD-2 | Orca upstream and adoption | Owner picks the upstream after HOT-DU-017a reports. `stablyai/orca` is the likeliest candidate because its public description claims a remote runtime, but that is unverified. The decision is the `DEC-039` third-party adoption decision. | E25; DEC-039 (B) |
| OD-3 | Orca criticality | Conditional executor substrate with native fallback (matches current REV5.1 policy). | F-05; an Orca outage should not stop development |
| OD-4 | VAN surfaces ownership | DIAL provides the projection API; VAN builds screens in its own pack. | F-12, `APPLICATION_PROJECT` |
| OD-5 | Reconciliation order and `DEC-039` renumber | PR #54 first, PR #45 renumbered to `DEC-046` and merged on top. | E8: 2 references against 44 |
| OD-6 | Placement Governor as a new name | Adopt `Placement Governor`; `compute-governor` keeps token semantics. | F-08 |

Already settled by locked canon, so not a decision, just a correction to Rev 1: DDE removal from the frontend path (`DEC-043`); Stage Graph inside the Development Pack (`DEC-044/045`).

---

# 8. Open research (not assumed anywhere above)

1. Orca: exact upstream, release tag, licence hash, headless/remote control API (does anything like `orca_terminal_send` exist?), telemetry, auto-update switch, state location and backup, permission defaults. *Context7 and Exa were unavailable in the authoring session.*
2. Fable, Astra, Opus 5.5, GPT-6 Sol: exact IDs and whether each can be pinned non-interactively under the subscription routes the runtime lock requires.
3. Whether PR #55 (VAN Rive) belongs in the baseline or stays a VAN-project change.

---

# 9. Rev 1 sections unchanged

Rev 1 §00 (executive contract), §02 (product truths HOT-PT-001…023), §07.4–07.6, §09.1–09.2, §09.5–09.13, §10, §11, §12, §14, §15, §18, §21, §22, §24, §27, §32, §33, §37, §38 stand as written, subject to these substitutions: DDE → DIAL-native production binding; "Compute Governor" (§20) → Placement Governor; Orca failure semantics per §3.4; VAN screens per OD-4.

**END — DIAL-HERMES-ORCA-MULTI-HARNESS-DDP-R2**
