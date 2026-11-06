# VAN Jev Control Centre transplant matrix — 2026-09-29

**Programme:** B — DIAL Global Jev × OpenMuse Convergence Rev 1 (unit G, contract B5).
**Authority:** `auth-20260929-owner-jev-openmuse-convergence-r1`; see
`docs/project-state/MISSION_PROVENANCE_MEMORY_FABRIC_JEV_20260929.md`.
**Source:** `origin/gpt/jev-control-centre-20260925` @ `f3df7a10e12fc76d25f958e9f19cb0b25c798168`
(123 ahead / 19 behind `main`). **Merge-base with target:** `be49e8e734181f99733742119912d810a49d0a3b`.
**Target:** `origin/gpt/jev-openmuse-convergence-r1-van-20260929` @ `a16f7cb` (OpenMuse convergence
`a8d3f19` + provenance), branch `unit-g-jev`.

The source branch is **not** merged as a merge commit. A trial `git merge --no-commit` was used to
obtain git's three-way result, then `git merge --quit` and the result was committed as four
ordinary commits, so that the two dropped documents are not recorded as "merged and deleted".

Derivation (re-runnable):

```
git diff --name-only be49e8e f3df7a1            # 50 files changed on the source
git diff --name-only be49e8e a16f7cb            # 197 files changed on the OpenMuse target
comm -12 <(sort src) <(sort tgt)                # overlap: 13 files
git diff --quiet f3df7a1 4bf8d1a -- <file>      # identical after transplant?
```

Three-way result: 9 of the 13 overlapping files auto-merged; 4 conflicted (`app.py`, `models.py`,
`runtime_api.py`, `degraded/registry.py`) and were resolved as unions (both sides kept).

## Disposition counts

| Disposition | Count | Meaning |
|---|---|---|
| TRANSPLANTED | 32 | byte-identical to the source |
| MERGED | 13 | three-way merge with OpenMuse; source and OpenMuse content both present |
| ADAPTED | 3 | content changed on purpose (reason given) |
| DROPPED | 2 | not carried over (reason given) |
| **Total** | **50** | |

Transplant commits: `3017574` (backend), `bdb5cda` (trading), `ef40f78` (Hermes/tools),
`4bf8d1a` (Android).

## Matrix

"Source SHA" is the last source-branch commit touching the file (`git log -1 f3df7a1 -- <file>`).

### Backend (`3017574`)

| File | Source SHA | Disposition | Note |
|---|---|---|---|
| `backend/van_gateway/jev/__init__.py` | `66766a9c` | TRANSPLANTED | |
| `backend/van_gateway/jev/advisor.py` | `6113d6d3` | TRANSPLANTED | consumer-scoped advisor; SHADOW ⇒ `apply_effect=false` |
| `backend/van_gateway/jev/api.py` | `bbe1898e` | TRANSPLANTED | owner-device projection routes |
| `backend/van_gateway/jev/client.py` | `ca2b3edb` | TRANSPLANTED | later **extended** in `fb9d17e6` with the B5 `JevProposeActionClient` |
| `backend/van_gateway/command/local_executors.py` | `2c0a7b8d` | TRANSPLANTED | |
| `backend/van_gateway/command/resolver.py` | `15a887b1` | TRANSPLANTED | |
| `backend/van_gateway/command/success_contracts.py` | `8ba1e2ef` | TRANSPLANTED | |
| `backend/van_gateway/orchestrator.py` | `cdffad19` | TRANSPLANTED | |
| `backend/van_gateway/reasoning/kernel.py` | `2f01cb25` | TRANSPLANTED | raise-only critic extension |
| `backend/van_gateway/understanding/api.py` | `1ec25f29` | TRANSPLANTED | |
| `backend/van_gateway/verification/production.py` | `102defd8` | TRANSPLANTED | |
| `backend/tests/test_jev_attention_integration.py` | `30469256` | TRANSPLANTED | |
| `backend/tests/test_jev_control.py` | `97d7bc75` | TRANSPLANTED | |
| `backend/tests/test_jev_critic_integration.py` | `c3fabe86` | TRANSPLANTED | |
| `backend/van_gateway/action/registry.py` | `ddf5b7f6` | MERGED | auto-merge |
| `backend/van_gateway/attention/engine.py` | `55225590` | MERGED | auto-merge |
| `backend/van_gateway/authority/descriptor.py` | `06829baf` | MERGED | auto-merge |
| `backend/van_gateway/config.py` | `4d51fe1e` | MERGED | auto-merge; `jev_enabled` stays default `False` |
| `backend/van_gateway/app.py` | `f554e440` | MERGED | conflict: union. The Jev advisor/projection block is placed before `AttentionEngine`, which now takes `jev_advisor`; OpenMuse's artifacts/documents/goals/suggestions/conversations then consume that one engine (OpenMuse's own `AttentionEngine(...)` line is the only line dropped, to avoid two engines) |
| `backend/van_gateway/models.py` | `24a9519a` | MERGED | conflict: union of `DIAL_DEV_*` (OpenMuse) and `JEV_UNAVAILABLE` (source) degraded codes |
| `backend/van_gateway/runtime_api.py` | `3a8ff56b` | MERGED | conflict: union of OpenMuse service kwargs and `jev_advisor` |
| `backend/van_gateway/degraded/registry.py` | `ca531ca6` | MERGED | conflict: union of catalogue rows |

### Trading (`bdb5cda`)

| File | Source SHA | Disposition | Note |
|---|---|---|---|
| `trading/tests/test_jev_architecture_boundary.py` | `69502dba` | TRANSPLANTED | Jev absent from every deterministic VATI path |
| `trading/tests/test_cognition_invokers.py` | `1e2d0423` | TRANSPLANTED | |
| `trading/vati/cognition/invokers.py` | `7f52286c` | ADAPTED | Source let a Jev result with `apply_effect=true` inform the cognition result. Blueprint §4 keeps `van.trading.*` ANNOTATE / `trading_subordinate_only` / ceiling SHADOW, so the prompt now says Jev is comparison evidence only and never changes the conclusion; the Jev block no longer lists size/route/stop vocabulary (it says "cannot create this CognitiveAssessment or alter any of its fields, and never touches a mandate or execution") |

### Hermes and tools (`ef40f78`)

| File | Source SHA | Disposition | Note |
|---|---|---|---|
| `hermes/skills/jev-management/SKILL.md` | `1f898c50` | TRANSPLANTED | |
| `hermes/profile/van/SOUL.md` | `23601591` | TRANSPLANTED | |
| `hermes/skills/browser-intelligence/SKILL.md` | `0d62f447` | TRANSPLANTED | `van.browser.state.v1` RAISE_ONLY evidence |
| `tests/hermes/test_profile_layout.py` | `6db9cb07` | TRANSPLANTED | |
| `tools/hermes/doctor_van_profile.sh` | `0a565cf4` | TRANSPLANTED | |
| `tools/hermes/install_van_profile.sh` | `60e1d45c` | TRANSPLANTED | |
| `tools/runtime/configure_jev_gateway.sh` | `d48a5340` | TRANSPLANTED | |
| `hermes/mcp/README.md` | `b081971a` | MERGED | auto-merge |
| `hermes/profile/van/config.yaml` | `99640e14` | ADAPTED | the source rewrote line 1 with a UTF-8 BOM and mojibake (`â€”`); OpenMuse's header line is kept, the `dial_jev` MCP server and `jev-management` skill are taken as-is |
| `hermes/skills/trading-intelligence/SKILL.md` | `f3df7a10` | ADAPTED | Jev section rule 3 rewritten to ANNOTATE-only (same reason as `invokers.py`); the "Live Trading Analyst" section (from `f3df7a1`) is **not** carried — see DROPPED |

### Android (`4bf8d1a`)

| File | Source SHA | Disposition | Note |
|---|---|---|---|
| `android/.../command/jev/JevControlRoute.kt` | `07b607ec` | TRANSPLANTED | |
| `android/.../command/jev/JevControlScreens.kt` | `c17887b1` | TRANSPLANTED | |
| `android/.../command/jev/JevEvidenceScreens.kt` | `261688ba` | TRANSPLANTED | |
| `android/.../command/jev/JevModels.kt` | `5772f6db` | TRANSPLANTED | |
| `android/.../command/jev/JevModuleScreens.kt` | `4df27f2d` | TRANSPLANTED | |
| `android/.../command/jev/JevOverviewScreens.kt` | `454fa537` | TRANSPLANTED | |
| `android/.../command/jev/JevRepository.kt` | `793fc8fa` | TRANSPLANTED | |
| `android/.../command/settings/SettingsRoute.kt` | `6e3c5a74` | TRANSPLANTED | |
| `android/verification/src/test/kotlin/com/dial/van/command/jev/JevModelsTest.kt` | `5bcc138c` | TRANSPLANTED | |
| `android/.../command/CommandCentreActivity.kt` | `0bc0d363` | MERGED | auto-merge |
| `android/.../command/nav/VanRoute.kt` | `c0053c21` | MERGED | auto-merge |
| `android/.../gateway/VanGatewayClient.kt` | `00dccf3a` | MERGED | auto-merge |
| `android/verification/build.gradle.kts` | `8117ba7c` | MERGED | auto-merge |

**Android — what was and was not checked.** `android/verification` is the standalone Kotlin/JVM
harness that compiles the app's *pure* files (docs/VAN_CLOSURE_HANDOFF.md §4). On `6e0ff722` (which contains `4bf8d1a`),
`gradle test --console=plain` in `android/verification` exited 0 (`BUILD SUCCESSFUL`); the JUnit XML
shows 991 tests, 0 failures, 0 errors, 0 skipped, including `JevModelsTest` (5 tests), so
`JevModels.kt` compiles and behaves there. (A first attempt failed on plugin resolution: `--offline`
had no cached Kotlin plugin, and Maven Central then answered `429`.) The Android Gradle Plugin cannot
be fetched in this environment, so `:app` is **not** compiled: the Compose screens
(`Jev*Screens.kt`, `JevControlRoute.kt`), `JevRepository.kt`, `VanGatewayClient.kt`, `VanRoute.kt`,
`CommandCentreActivity.kt` and `SettingsRoute.kt` have no compile evidence here.

### Dropped

| File | Source SHA | Reason |
|---|---|---|
| `docs/VAN_EXPERT_TRADING_TERMINAL_M0_SEMANTIC_CLOSURE_REV_1.md` | `100df31a` | Expert Trading Terminal product contract, not Jev Control Centre. Out of this unit's transplant scope; it remains on the source branch for its own programme and review |
| `docs/VAN_EXPERT_TRADING_TERMINAL_UX_BLUEPRINT_REV_1_1.md` | `33f7a27c` | same |

## Not verified here

- Android compile/test (above).
- Live `dial-jev` service behaviour; every Jev test uses fakes or `httpx.MockTransport`.
- `hermes/profile/van/config.yaml` keeps the source's `dial_jev: enabled: true`. It only makes
  the MCP tool surface available to Hermes; the DDS modules stay SHADOW/DISABLED (blueprint §6).
