# DIAL Hermes–Orca Symbiotic Multi-Harness Development Fabric
## PRD → Deterministic Development Pack — Rev 3 (Owner-Decided Canonical Candidate)

**Pack ID:** `DIAL-HERMES-ORCA-MULTI-HARNESS-DDP-R3`
**Builds on:** Rev 1 (owner blueprint, provenance) and Rev 2 (repository-grounded consolidation audit). Rev 2's evidence (E1–E27), findings (F-01–F-21), Checkpoint 0 procedure and consolidation map stand, except where this file records an owner decision that replaces a Rev 2 recommendation.
**Prepared:** 2026-09-23, branch `claude/plan-audit-review-p8i1uc`, DIAL base `master@1405daaa`, VAN reference `Vanguduza/van@61d86cd`, Orca reference `stablyai/orca@dac82f61` (main, `package.json` 1.4.197; newest stable tag observed `v1.4.209`).

| State | Value |
|---|---|
| Blueprint state | `OWNER_DECIDED_CANONICAL_CANDIDATE` |
| Registry decisions written | `DEC-048`…`DEC-059` registered 2026-09-25 under `auth-20260925-owner-fable-estate-convergence-mission`; see §9 for the id-to-item mapping |
| FORENSIC_BUILD_READY / RUNTIME_QUALIFIED / PRODUCTION_QUALIFIED / OWNER_ACCEPTED | `false` / `false` / `false` / `false` |

---

# 0. Owner decisions recorded (2026-09-23)

| ID | Owner decision | Replaces |
|---|---|---|
| OD-A | **Orca is the "Orca AI" agent development environment**: many AI coding agents managed from one workspace, each in its own isolated Git worktree, supporting Claude Code, Codex, Gemini CLI, OpenCode and more. | Rev 2 OD-2 (upstream unidentified) |
| OD-B | **Orca is not optional.** DIAL runs a **deterministic, self-hosted** setup in which Orca and the existing DIAL worktree/lease system are integrated and complement each other, each supplying its best features, resulting in **one DIAL development-system code path**. | Rev 2 OD-3 (conditional substrate with native fallback) and Rev 2 §3.4 |
| OD-C | **VAN development screens are built in the VAN project**, but their **design and logic are finalised in DIAL** (this pack). DIAL may read the VAN repository for deterministic planning and informed design. | Rev 2 OD-4 |
| OD-D | **"Astra" is OpenAI's flagship GPT-6 Astra model from the ChatGPT Pro subscription.** (corrected by owner the same day from "GPT Astra") | Rev 2 OD-1 (Astra unidentified) |
| OD-E | **Sonnet 5 is the final manager fallback** before `NO_HERMES_MANAGER_RUNTIME`. | Rev 3 open item OD-1b |
| OD-F | **Orca tracks the latest stable release.** Made deterministic by resolve-then-pin (§1). | Rev 3 §1 "tag chosen at qualification" |
| OD-G | **ARTEMIS is DIAL's Android app testing harness, not a VAN integration.** VAN only hosts an owner console onto it. | Rev 1 wording "VAN ARTEMIS surface" (HOT-DU-035) |

Still open (procedural, carried from Rev 2):

- **OD-5** reconciliation order and `DEC-039 → DEC-046` renumber (procedural; Rev 2 §4.1).
- **OD-6** "Placement Governor" name (Rev 2 F-08).

---

# 1. Orca identity (evidence for OD-A)

The owner's reference image shows the "ORCA AI" mark with the text "Manage multiple AI coding agents from one workspace… Each agent can work in its own isolated Git worktree." Three GitHub projects use the name. The evidence points to one:

| Candidate | Evidence | Match |
|---|---|---|
| `stablyai/orca` | MIT; built by Stably AI (Y Combinator); covered as "Orca AI" by third-party reviews; ≈43k stars reported; site onorca.dev; supports Claude Code, Codex, OpenCode, Antigravity, Hermes Agent and "any CLI agent"; built-in `gemini` agent launch profile present in source (`src/shared/tui-agent-permissions.ts`) | **Selected** |
| `nwparker/orca` | Earlier README text identical to stablyai's ("next-gen IDE for working with a fleet of parallel agents") | Same product lineage, not the maintained home |
| `orca-cli/orca` | Go binary, 4 stars, "interfaces may shift before v1.0" | Rejected: not the widely covered "Orca AI" |

**Version rule — latest stable, resolved then pinned (OD-F).** DIAL runs the latest stable Orca release. Doing that deterministically means "latest" is **resolved once per convergence and then pinned**, never fetched live:

1. **Resolve.** List release tags, keep only `vMAJOR.MINOR.PATCH` (drop `-rc`, `-beta` and non-version tags such as `_gh-attach-assets`), and take the highest by version sort. On 2026-09-23 that is **`v1.4.209`**.
2. **Lock.** Download that tag's Linux AppImage from its **tag URL**, compute its SHA-256, and write `{tag, sha256, resolved_at}` to `ops/development-bootstrap/supply-chain/PINS.json`. Every host installs from the lock, so all hosts run byte-identical Orca.
3. **Never** install from `releases/latest/download/…`. Orca's own headless guide uses that URL, but it can change between download and verification and breaks reproducibility.
4. **Advance.** A scheduled check detects a newer stable tag and opens a pin-bump change. The candidate runs the Orca qualification set (CLI parity §4.2, fences §2.3/§2.4, daemon scope §3.2 step 7, mutations §8). Pass → promote, using the §3.3 upgrade path. Fail → stay on the current pin and raise an owner-visible blocker.

So DIAL stays on the latest release that has passed qualification, typically within one cycle of each Orca release.

Source basis: repository files read at `stablyai/orca@dac82f61` (`README.md`, `docs/reference/headless-linux-server.md`, `docs/reference/orcad-operations.md`, `src/cli/specs/*.ts`, `src/shared/tui-agent-permissions.ts`, `src/shared/tui-agent-launch-defaults.ts`) plus public web descriptions. This is reference evidence under `DEC-039`; adoption is authorised by OD-A/OD-B and becomes a registered dependency decision in §9.

---

# 2. One integrated execution fabric — who does what

The seam falls cleanly because the two systems don't overlap where it matters. Evidence: DIAL's `worker-lease-manager.mjs` is **purely logical**; `issueWorktreeLease` takes a `worktreePath` and never runs `git worktree add`. Orca's `orca worktree create` **physically creates** checkouts and owns terminals. Neither needs to give anything up.

## 2.1 Responsibility split

| Capability | Owner | Why that side |
|---|---|---|
| What may run next (Stage Graph READY set, manager selection) | **Hermes/DIAL** | Single orchestration authority (HOT-PT-001) |
| Worker selection (harness × model) | **DIAL HCX** | Capability cards, independence rules |
| Host placement | **DIAL Placement Governor** | `oracle-admin`, `10.77.0.5` exclusion; VAN burst policy |
| Token capacity | **DIAL `compute-governor`** | `DEC-028` |
| Write authority: path scopes, TTL, fencing token, revocation | **DIAL `worker-lease-manager`** | Already implemented, per-tool enforced |
| Per-tool enforcement (envelope, lease, fence, VEKL activation, network) | **DIAL `pre-tool-guard`** | Runs identically inside an Orca terminal |
| Physical worktree creation and removal, repo registry, branch bookkeeping | **Orca** | `orca worktree create/rm/list/show`, parent/child lineage |
| Persistent PTYs that survive runtime restart and client disconnect | **Orca** | Detached terminal daemon in its own systemd scope (`orcad-operations.md`) |
| Agent launch, per-agent status, transcript capture, session search | **Orca** | Hook-reported agent status store; PTY transcript capture |
| Live diff and review views, file open/diff | **Orca** | `orca file diff`, desktop UI |
| Remote execution hosts over SSH | **Orca**, admitted by DIAL | `--host`, `environment` model; host must be DIAL-admitted first |
| Owner live view of workspaces and terminals | **Orca desktop client** over WireGuard + SSH forward for deep terminal/diff work; **VAN** (phone) for status and governed actions | Orca gives the richest terminal view; VAN carries Hermes authority. Orca mobile pairing is unavailable under the loopback bind (§3.1) |
| Checkpoints, receipts, SPMRF memory, review admission, gates | **DIAL** | Evidence authority |
| Housekeeping (deletion eligibility) | **DIAL** decides; **Orca** executes `worktree rm` | `DEC-046` (renumbered housekeeping) proofs first |
| Android device/emulator testing | **DIAL ARTEMIS** | HOT-PT-011; Orca `emulator *` commands disabled |
| Browser automation | **DIAL Stagehand/Playwright** | Orca browser commands disabled for workers |
| Multi-agent coordination, task boards, gates | **Hermes/DIAL** | Orca `orchestration *` coordinator disabled |
| Automations, Linear sync, artifact sharing, skill install/share | **none** (disabled) | Second scheduler, second tracker, egress, second skill authority |

## 2.2 Orca features that are disabled, and why

Orca ships features that would each create a second authority or an egress path. The deterministic setup turns them off, and a settings-drift probe (§3.4) keeps them off.

| Orca feature (CLI group) | Conflicts with | Setting |
|---|---|---|
| `orchestration` (coordinator, dispatch, task/gate/worker boards) | Hermes as sole orchestrator; HOT-PT-009 | coordinator never started; any run present = drift |
| `automations` | Stage Graph dispatch | disabled |
| `linear` | Stage Graph / VAN TODO as the only task view | disabled, no credentials |
| `skills install/update/share` | VEKL governs skills; no mutable-upstream activation | disabled; only VEKL-admitted pins |
| `artifacts share/unshare` | egress, secret boundary | disabled |
| `computer *` (desktop automation) | Desktop Commander under CommanderAuthorityLease | disabled |
| `emulator *` | ARTEMIS | disabled |
| browser commands | Stagehand/Playwright specialists | disabled for workers |
| cloud relay / pairing through Orca cloud | self-hosted, private network only | `ORCA_CLOUD_*` unset; egress deny |
| telemetry, diagnostics upload | no external data flow | `ORCA_TELEMETRY_DISABLED=1`, `ORCA_DIAGNOSTICS_DISABLED=1` |
| **Default agent permission bypass** | HOT-PT-010 | see §2.3 |

## 2.3 Permission defaults — the critical correction

Orca's shipped defaults launch agents **with permission bypass on**. `src/shared/tui-agent-launch-defaults.ts` sets `DEFAULT_TUI_AGENT_ARGS = YOLO_TUI_AGENT_ARGS`, which includes:

```text
claude      --dangerously-skip-permissions
codex       --dangerously-bypass-approvals-and-sandbox
gemini      --yolo
antigravity --dangerously-skip-permissions
hermes      --yolo
```

A default install therefore violates HOT-PT-010 on every agent. The integrated setup:

1. sets Orca's agent permission mode to **manual** for every agent. Orca's own code notes that an empty stored value "owns the key and so beats that default";
2. **never uses Orca's agent launcher defaults**. DIAL starts every worker with `orca terminal create --worktree <id> --command "<dial-orca-launch …>"`, and the DIAL launcher supplies the exact, allow-listed harness arguments;
3. fails qualification if any live worker command line contains a bypass flag (mutation M-O1).

## 2.4 Worker fencing inside Orca terminals

Orca injects `ORCA_AGENT_HOOK_TOKEN`, `ORCA_TERMINAL_HANDLE`, `ORCA_WORKTREE_ID`, `ORCA_WORKTREE_PATH` and `ORCA_CLI_COMMAND` into agent terminals, and its README says "Agents drive Orca too". Unfenced, a worker could create worktrees or type into another agent's terminal, bypassing the DIAL lease.

Fence:

- `dial-orca-launch` keeps the hook variables that feed Orca's **status** display, and removes `ORCA_CLI_COMMAND` from the worker environment.
- DIAL `pre-tool-guard` gains an **Orca rule**: shell commands invoking `orca`/`orca-ide` are denied except the read-only `agent-context`, `worktree current`, `worktree show --worktree active` and `status`.
- Harnesses without DIAL hooks (Codex, Antigravity) get the same rule through their own policy mechanism. Each harness must **prove** the fence under mutation M-O2 before it is enrolled on Orca. A harness that cannot is not enrolled.

---

# 3. Deterministic self-hosted deployment (Dial Control)

## 3.1 Topology

```text
dial-control (10.77.0.1, Netcup)
  systemd: orca.service  (User=orca, linger enabled)
    orcad / `orca serve --json --bind 127.0.0.1 --port 6768`
    terminal daemon → own scope: orca-daemon-<nonce>.scope  (PTYs survive service restart)
  data root: /var/lib/orca (ORCA_USER_DATA), 0700, owned by orca
  install:   /opt/orca/<tag>/ root-owned, read+exec only for orca
  DIAL:      orca-adapter (typed, the only caller with runtime credentials)
             worker-lease-manager, pre-tool-guard, HCX, Placement Governor
remote execution hosts (Orca SSH hosts) — only DIAL-admitted:
  van-trading-core (10.77.0.4)  burst policy
  never: oracle-admin (10.77.0.2), old-dial-hermes-control (10.77.0.5)
owner clients:
  VAN app (phone)      → VAN backend → DIAL Development Projection API (WireGuard) → typed Hermes controls
  Orca desktop client  → WireGuard → SSH local port-forward → 127.0.0.1:6768   (deep terminal/diff work)
```

Orca binds **loopback only**. Orca's own docs: default `127.0.0.1`, the bind is pinned, and "a client reaches a remote orcad over an SSH local port-forward… the pairing credential travels over SSH". Orca's cloud relay is not used. The same docs say a **mobile pairing offer is refused while the bind is pinned to loopback** (`network_exposure_failed`). Orca's mobile app is therefore deliberately not an owner surface. **VAN is the owner's mobile development surface** (§6), and it carries Hermes authority, which Orca's app would not.

## 3.2 Pinned install (bootstrap, idempotent)

1. Read the locked latest-stable **tag** and AppImage **SHA-256** from `ops/development-bootstrap/supply-chain/PINS.json` (§1 version rule). Download from the tag URL and refuse on SHA mismatch.
2. Install prerequisites from Orca's headless guide for the host's release, since package names differ between Ubuntu 22.04 and 24.04 (`t64` suffix).
3. Extract once (`--appimage-extract`) into `/opt/orca/<tag>/`, `chmod -R a+rX`, root-owned, so the service user cannot replace binaries. This also removes the self-update path.
4. Create system user `orca`, `loginctl enable-linger orca`, so the terminal daemon gets its own scope.
5. Write the pinned **settings file** (permission mode manual, disabled groups per §2.2) and environment (`ORCA_USER_DATA`, `ORCA_TELEMETRY_DISABLED=1`, `ORCA_DIAGNOSTICS_DISABLED=1`, `LIBGL_ALWAYS_SOFTWARE=1`, no `ORCA_CLOUD_*`).
6. systemd unit: `ExecStart=/opt/orca/<tag>/AppRun serve --json --bind 127.0.0.1 --port 6768`, `Restart=on-failure`, `RestartPreventExitStatus=78` (Orca's configuration-fault code: do not restart), generous `TimeoutStartSec` (cold daemon launch "can take tens of seconds").
7. Readiness: DIAL health probe consumes the single `orca_server_ready` JSON line and `orca status --json`, and records `runtimeId`, `boundEndpoint`, version and `health.terminalDaemon.cgroupUnit`. **Health is `QUALIFIED` only if `cgroupUnit` names an `orca-daemon-*.scope`**, which proves terminals survive restarts.
8. Capability ladder per Rev 1 §26: `INSTALLED → AUTHENTICATED → LIVE_QUALIFIED → ORCHESTRATED → INTEGRATED`.

## 3.3 Upgrade and rollback

Upgrade is a pack change, not a background event: new tag + SHA in `PINS.json` → qualification on the candidate → **terminal census** (`sudo -Hu orca …/orca-ide terminal list --json` must be untruncated with explicit `hostScope`; any `unverifiable` result defers) → PID-scoped restart (Orca's documented non-destructive path) → requalify. Rollback is the same procedure with the previous pinned tag, kept on disk.

## 3.4 Drift control

Each health tick compares the live Orca version, settings hash, permission mode, disabled groups, bind address and cloud/relay state with the pinned values. Any drift sets Orca to `DRIFTED`, which **blocks new material dispatch** until reconciled (§4.3).

---

# 4. The single deterministic worker path

## 4.1 Sequence

```text
 1  Stage Graph node READY; manager selects it (typed output)
 2  Task Execution Envelope created (intent sub-record, stage_plan_revision)
 3  HCX selects harness×model; Placement Governor admits host; compute-governor reserves tokens
 4  worker-lease-manager.issueWorktreeLease(task, worker, writePaths, baseCommit)
       → lease_id, fencing_token          (no path yet)
 5  DIAL creates immutable base ref  refs/dial/base/<task_id> → base_sha
 6  orca-adapter: orca worktree create --repo <id> --name dial/<task_id>
       --base-branch refs/dial/base/<task_id> --no-parent --setup skip --json
       [--host <admitted-host>]
       → worktree id <repo-id>::<path>
 7  DIAL binds: lease.worktree_path, lease.orca_worktree_id; asserts
       HEAD == base_sha, branch == dial/<task_id>, path inside the Orca data scope
       any mismatch → orca worktree rm, lease REVOKED, task FAIL (no write happened)
 8  orca-adapter: orca terminal create --worktree <id>
       --command "dial-orca-launch --envelope <hash> --lease <id> --fence <token> --harness <h> --model <m>"
 9  dial-orca-launch: sets DIAL_* env, strips ORCA_CLI_COMMAND, verifies pre-tool-guard
       wiring for this harness, starts harness with allow-listed args (never bypass)
10  worker publishes ExecutionIntent → Hermes validates → progress events to SPMRF
11  every tool call: pre-tool-guard checks envelope, VEKL activation, lease, fence, path, Orca rule
12  completion candidate → DIAL checkpoint commit → review → receipt → gate reconciliation
13  lease RELEASED → housekeeping decides → orca-adapter: orca worktree rm
```

Steps 5–7 are the **binding contract**. Orca owns the physical checkout; DIAL owns whether any write in it counts.

## 4.2 Adapter operations (derived from Orca's real CLI)

Rev 1 §07.3 guessed an API. Rev 3 maps each operation onto the Orca CLI that exists at the reference commit:

| DIAL operation | Orca CLI |
|---|---|
| `orca_status` | `orca status --json` |
| `orca_project_register` | `orca repo add`, `orca repo show --repo <id>` |
| `orca_workspace_create` | `orca worktree create … --json` |
| `orca_workspace_get` / list | `orca worktree show --worktree <id> --json`, `orca worktree list --repo <id>`, `orca worktree ps --json` |
| `orca_workspace_destroy` | `orca worktree rm --worktree <id>` (DIAL housekeeping-approved only) |
| `orca_agent_start` | `orca terminal create --worktree <id> --command …` |
| `orca_agent_status` | `orca terminal show`, `orca terminal list --json`, `orca agent-context --json` |
| `orca_terminal_send` | `orca terminal send` (**owner guidance via Hermes only**) |
| `orca_terminal_tail` | `orca terminal read --terminal <h>` |
| `orca_terminal_wait` | `orca terminal wait --terminal <h>` |
| `orca_terminal_stop` | `orca terminal stop` / `close` |
| `orca_diff_get` | `orca file diff` |
| `orca_hosts` | `orca host list`, `orca environment list/show` |
| `orca_checkpoint` | **DIAL**: git commit in the worktree plus DIAL checkpoint record (Orca has no checkpoint concept) |
| `orca_workspace_pause` / `resume` | **DIAL**: lease suspend plus `terminal stop`; resume = new terminal on the same worktree (`orca terminal create --worktree <id>`), per Orca's note "for a fresh agent in an existing worktree" |

Each operation's flags and JSON shape are re-verified against the pinned tag during HOT-DU-019; CLI parity tests fail the build on drift.

## 4.3 Failure semantics (mandatory Orca, per OD-B)

| Condition | Response |
|---|---|
| Orca down, restarting, `DRIFTED` or unqualified | **No new material dispatch** (fail closed). Nodes wait as `WAITING_EXTERNAL`. There is no silent second path. |
| orcad restart | Running PTYs survive in the daemon scope; the successor adopts them; DIAL re-reads `terminal list` and reconciles. |
| Daemon lost (host reboot) | Leases stay authoritative; worktrees are on disk; DIAL reconciles `worktree list` against leases; each task is resumed (new terminal, same worktree, same lease if unexpired) or abandoned explicitly. |
| Orca registry lost | DIAL re-registers repos and re-adopts worktrees from lease records (`orca repo add` + worktree reconciliation); unknown worktrees are quarantined, never deleted. |
| Lease expired or revoked while terminal runs | pre-tool-guard denies further writes; adapter stops the terminal; late results are quarantined. |
| Worktree mismatch at bind (step 7) | Worktree removed, lease revoked, task FAIL, finding recorded. |

This keeps OD-B's single code path. DIAL's worktree/lease layer is not a fallback execution path; it is the authority and recovery layer **inside** that path. Orca outages are handled by making Orca highly available on one host (pinned, supervised, daemon-scoped, drift-controlled), not by routing around it.

---

# 5. Manager plane (OD-D)

```text
Fable  →  GPT-6 Astra  →  GPT-6 Sol  →  Claude Opus 5.5  →  Claude Sonnet 5  →  NO_HERMES_MANAGER_RUNTIME
```

| Slot | Route (existing DIAL mechanism) | Exact ID | Qualification |
|---|---|---|---|
| Fable | Claude Code subscription route | discovered by live probe | must pin non-interactively; the current probe reports Claude Code lists models only via interactive `/model` (`claude-code-probe.mjs:180`), so this is a real qualification item |
| GPT-6 Astra | Codex App Server via **ChatGPT Pro** subscription | discovered by live probe | subscription route only, never API billing |
| GPT-6 Sol | Codex App Server via ChatGPT subscription | discovered by live probe; `gpt-5.6-sol` remains until a GPT-6 Sol ID is proven | — |
| Opus 5.5 | Claude Code subscription route | discovered by live probe | — |
| Sonnet 5 (final fallback, OD-E) | Claude Code subscription route | `claude-sonnet-5` (already qualified; the only healthy slot on 2026-09-23) | — |

The registered decision supersedes the `README.md` runtime lock and amends `DEC-021` (development-ready fallback names the terminal qualified slot) and `DEC-022` (capacity preservation applies per slot). Fallback passes the identical ManagerTurnEnvelope (Rev 1 §04.3). An unqualified slot is skipped and recorded, never approximated.

---

# 5a. ARTEMIS — Android testing harness (OD-G)

ARTEMIS is `google/artemis` (Apache-2.0), pinned at commit `371aa6df…` with DIAL shell hardening (`ANDROID_TESTING_PLANE.json`, PR #45 lineage). It is an autonomous Android test and diagnostic agent. It runs **on `dial-control`** as `SUBORDINATE_ANDROID_AUTONOMOUS_TEST_AND_DIAGNOSTIC_EXECUTOR` under Hermes, and it is reached only through the governed `dial_android_testing` tool (`android_task_start`, `android_task_manage`, `android_device_state`, …) with exclusive device leases.

- It tests **any admitted Android app**: DIAL product apps, and VAN's own Android app when VAN is the project under development.
- Its results are `TEST_EVIDENCE` candidates; Hermes reconciliation admits them (Rev 1 §12).
- **VAN's relationship to ARTEMIS is only a viewer:** VAN PR #63 embeds an owner console that reaches ARTEMIS through a server-side proxy (`dial-artemis-console-proxy.service`, port 9135). VAN has no ARTEMIS authority, no ADB access and no raw MCP.
- In the integrated fabric, when a task needs Android verification, the worker asks Hermes, and Hermes runs ARTEMIS against the admitted build artifact and device (Rev 1 §12). Orca's own `emulator *` commands stay disabled (§2.2), so there is one Android test authority.

# 6. VAN Development Control Centre — design and logic (OD-C)

The full design and logic is in `VAN_DEVELOPMENT_CONTROL_CENTRE_DESIGN_REV_1.md` (`VAN-DEVCC-R1`), written against `Vanguduza/van@61d86cd`. The decisions that shape it:

1. **Fit VAN's IA; don't add 17 destinations.** VAN's design DNA fixes 8 destinations and records "Removed: the flat 17-module grid". Rev 1's screens become a **Development hub under Work** (`work/dev/**`). Approvals and blockers flow into VAN's existing **Attention** triage (source `dial-dev`), and infrastructure goes into **Connected**.
2. **Native typed screens, not a WebView.** The existing ARTEMIS console is a WebView reverse proxy. The development centre instead uses typed reads and typed actions, and implements VAN's seven-state contract (LOADING/CONTENT/EMPTY/ERROR/DEGRADED/OFFLINE/STALE) with `@DataSource` declarations.
3. **One data contract: the DIAL Development Projection API** (HOT-DU-008). It is served by DIAL on the WireGuard address, and VAN's backend is its only client. Every response carries `projection_revision`, source cursors, `freshness_ms` and `degraded[]`, which map directly onto VAN's `Stale` and `Degraded` states.
4. **Typed owner actions map onto existing DIAL controls** (`dial_owner_steer`, pause/resume, checkpoint, review, revoke, decide, reprioritise). Each action carries an idempotency key and `expected_projection_revision`. There is no optimistic success and no raw terminal input. VAN's device-proof rules apply.
5. **VAN's authority boundary holds.** VAN-Hermes remains VAN's sole agent runtime and never plans DIAL work. VAN displays DIAL state and forwards owner commands.

Implementation is VAN units `VAN-DEV-001…011` in VAN's own Development Pack, built against this contract.

---

# 7. Development Unit changes from Rev 2

| DU | Change |
|---|---|
| HOT-DU-017a | Scope narrowed: identity settled (`stablyai/orca`); remaining work is tag/SHA pin, licence hash, and proving §2.3, §2.4, §3.2 step 7 and §4.2 against the pinned tag |
| HOT-DU-017 (+018) | Deterministic install per §3.2 incl. settings-as-code and drift probe (§3.4) |
| HOT-DU-019 (+020) | Adapter = §4.2 mapping + CLI parity tests |
| HOT-DU-021 | Binding contract §4.1 steps 4–7 incl. immutable base ref |
| HOT-DU-022 | Permission hardening = §2.3 + §2.4 (Orca rule in `pre-tool-guard`; per-harness fence proof) |
| HOT-DU-023 | HCX: `executor_substrate` is always `ORCA` (no native alternative); cards gain `orca_agent_profile` and `fence_proof_ref` |
| HOT-DU-041 | Recovery per §4.3 (daemon adoption, registry rebuild, reconciliation) |
| HOT-DU-042 | Housekeeping executes `orca worktree rm` only after DIAL deletion proofs |
| HOT-DU-003 | Qualify Fable, GPT-6 Astra, GPT-6 Sol, Opus 5.5 per §5; Sonnet 5 stays qualified |
| HOT-DU-009/010 | Design and logic finalised here (§6); built in VAN as `VAN-DEV-*` |
| HOT-DU-034/035 | Per OD-G: ARTEMIS stays DIAL's Android testing harness (034 projects its tasks into ActiveWorkGraph). 035 is **not** a VAN build item: VAN's owner console onto ARTEMIS already exists (VAN PR #63), so the only VAN work is linking it from task detail. |

---

# 8. Added verification

**E2E**

- HOT-E2E-20 — orcad restart mid-task: terminal survives, DIAL reconciles, task completes with the same lease.
- HOT-E2E-21 — worker inside Orca attempts `orca worktree create`: denied by the fence, audited.
- HOT-E2E-22 — host reboot: worktrees reconciled from leases; nothing deleted; each task resumed or abandoned explicitly.
- HOT-E2E-23 — Orca settings drift (permission mode flipped to yolo): dispatch blocks within one health tick.

**Mutations (certification fails if any succeeds)**

- M-O1 worker launched with any permission-bypass flag
- M-O2 worker mutates Orca (worktree create/rm, terminal send to another terminal, orchestration run)
- M-O3 Orca `orchestration` coordinator running
- M-O4 Orca bound to a non-loopback address, or cloud relay configured
- M-O5 Orca installed from `releases/latest` or unpinned tag
- M-O6 worktree used for writes before step-7 binding succeeds
- M-O7 `orca worktree rm` on a worktree with unpushed unique commits or an active lease
- M-O8 material dispatch while Orca is `DRIFTED`/unqualified (no silent path)
- M-O9 Orca `emulator`/`computer`/browser command reachable from a worker

---

# 9. Decisions to register after Checkpoint 0

After `DEC-039 → DEC-046` (Rev 2 OD-5), registered as the next free IDs (registered 2026-09-25 under `auth-20260925-owner-fable-estate-convergence-mission`, per the owner mission instruction of 2026-09-24 and the OD-A…OD-G decisions above of 2026-09-23; full texts and evidence in `agent-system/registries/DECISION_LOG.json`):

1. **`DEC-048`** — Orca (`stablyai/orca`, pinned) is DIAL's mandatory execution-workspace runtime, integrated with the DIAL lease/fence authority as one code path (OD-A, OD-B). This is also the `DEC-039` third-party adoption decision.
2. **`DEC-049`** — Manager chain per §5: Fable → GPT-6 Astra → GPT-6 Sol → Opus 5.5 → Sonnet 5 (OD-D, OD-E), amending `DEC-021`/`DEC-022`.
3a. **`DEC-050`** — Orca version rule: latest stable, resolved then pinned, advanced through qualification (OD-F).
3b. **`DEC-051`** — ARTEMIS role clarification (OD-G).
3. **`DEC-052`** — VAN development surfaces: design/logic owned by DIAL pack, implementation by VAN (OD-C).
4. **`DEC-053`** — Placement Governor (OD-6).

The remaining OG-2 items (Zuul adoption, canonical repository cutover, oracle-admin product gateway OD-H, dual Claude Code pools, dual ChatGPT/Commander installs, multi-provider frontend design intelligence — none of them Rev 3 items) were registered in the same batch as `DEC-054`…`DEC-059`; see `docs/project-state/forensic/DECISIONS_TO_REGISTER_20260924.md` for their source texts.

**END — DIAL-HERMES-ORCA-MULTI-HARNESS-DDP-R3**
