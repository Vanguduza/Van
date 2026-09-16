# VAN Implementation Ledger

**Updated:** 2026-09-16
**Version:** 0.5.0-dev  
**Repository:** `Vanguduza/Van`

## IMPLEMENTED (repository-side)

- Canonical authority: Project Truth, Security Policy, visual identity/Rive contract, external gates.
- VAN secure gateway: owner enrollment, signed commands, idempotency, stale-intent expiry, A4/A5 gates, prompt-injection rejection, attention, briefing, reminders, notification intelligence, audit, events and Project Truth cache.
- Hermes pack: profile `van` SOUL, skills, fail-closed policy hook, Bot Chat/councils contracts and install/doctor tooling.
- Android embodiment: overlay, Command Centre, encrypted queue, notification listener, share intent, voice/TTS hooks, biometric gate, onboarding and degraded-mode model.
- Google Workspace token vault: encrypted refresh tokens, narrow scopes, revocation and prompt scrubbing.
- **Google OAuth correctness:** live Workspace transport exchanges encrypted refresh tokens for short-lived access tokens before Google API requests.
- **Google Account Sovereignty:** one logical owner Google principal with separate Workspace OAuth, Gemini runtime, Cloud/service and consumer-session credential planes.
- **Google Intelligence Mesh:** versioned capability registry covering Gemini, Gemini Live, Deep Research, Gemini Notebook (personal + Enterprise), Mixboard, Stitch, Antigravity, Jules, Workspace API/Studio, Nano Banana, Veo, Flow, AI Studio and ADK/A2A.
- **Deterministic Google router:** action-class, approval, grant and Project Truth gates; registry-order deterministic selection; explicit fallback; persisted input hash and job state.
- **Google readiness model:** READY / CONFIGURED / UNVERIFIED / AUTH_REQUIRED / DEGRADED / RATE_LIMITED / CAPACITY_LIMITED / POLICY_BLOCKED / UNSUPPORTED / UNAVAILABLE.
- **Antigravity capacity scoping:** live generation `CAPACITY_LIMITED` records `ANTIGRAVITY_CAPACITY_LIMITED` and falls back to Jules when configured; does not fail Workspace/Gemini/Jules planes.
- **Project Truth mounts:** `registries/project_mounts.json` + sync tool prefer per-project `truth_path`; offline cache under `artifacts/project-truth/`.
- **Google provenance:** persistent jobs and artifact lineage with project, provider, tool version, input/output hashes, validation state and evidence pointer; provider artifacts can never be marked `OWNER_SIGNED`.
- **Google operator tooling:** hashed owner-principal configuration and certification/status scripts; `tools/google/mark_antigravity_capacity_limited.py`; `tools/google/import_hermes_google_attestation.py` for Hermes-hosted auth evidence.
- **Hermes Google skills:** google-intelligence, gemini-notebook, google-design, google-development; Google providers remain subordinate to Hermes.
- **Policy hardening:** Google broker/registry protected; session-cookie export, credential-plane collapse and broker bypass are prohibited patterns.
- Comprehensive canonical specification: `docs/GOOGLE_INTELLIGENCE_MESH.md`.
- Device/CI helpers: `tools/certification/device_cert_probe.py`; `tools/ci/install_github_workflow.py`; Windows `tools/bootstrap_backend.ps1`, `tools/run_gateway.ps1`, `tools/sync_project_truth_live.ps1`.
- **VATI Phase 0 — Canon & Risk Boundary:** `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md` (expert review of Rev 1 + Rev 2 canon; Rev 1 archived as provenance); `trading/vati/risk` deterministic Risk Authority (mandate load with platform ceilings and hard-forbidden behaviours, [0,1]-clamped multipliers, venue round-down sizing, stake sizing for fixed-payout contracts, portfolio heat, currency-leg netting, drawdown governor, latching kill switch, sealed hashed decisions); seven JSON Schema contracts; 110 tests including seeded property fuzz with induced-failure evidence; `trading-intelligence` Hermes skill; policy hook now denies trading A5 patterns and protects trading authority surfaces.
- **VATI Rev 2.1 — Industry Integration Architecture:** Part E of the blueprint reviews the proposed best-of-industry stack layer by layer with verified licences/versions; `trading/architecture/stack_lock.json` + test lock one tool per layer, one sizer, one order sender, one transactional authority; `trading/vtil/registry` seeds VTIL in DIAL's VEKL schema and `trading/vtil/tools/resolve_probe.mjs` proves DIAL's unmodified resolver selects trading knowledge from it (4/4 golden cases GREEN); deployment topology places the trading data plane on Van-owned hosts, attached to the DIAL fabric only via project binding.
- **VATI Rev 3 — research-grounded expert trader + Zimbabwe Stock Exchange module:** own research corpus (`docs/research/VATI_REV3_RESEARCH_CORPUS.md`, 60+ sources, verification states); Rev 3 blueprint with independent decisions (no MICRO horizon, cost-first gate, LLM boundary, minimum deterministic stack, prop-firm mandate profile); `trading/vati/zse` (sourced market facts that block live until verified, cost schedule with holding-period CGWT, ZiG regime classifier, liquidity haircut/participation cap); `LossModel.ILLIQUID_EQUITY` in the Risk Authority with `EDGE_BELOW_COST`; VTIL registry ZSE sources/resources (probe 5/5 GREEN); stack lock 3.0.0.
- **VATI build A–F — the trading system (Rev 4 consolidated blueprint `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`):** canonical hashing, event envelope and hash-chained ledger with decision replay; calendars, integrity monitor, bar aggregation, FX cost model, metrics; features, CUSUM regime engine with hysteresis, Tier-1 event matrix, sealed MarketState; capsule registry with owner-signed promotion, five deterministic strategies, horizon/strategy arbiters, rule meta-labeller, opportunity engine; execution router with sealed-decision verification, Paper/OwnerTicket/MT5-bridge/Deriv adapters, tighten-only protection, reconciliation classes, TCA, trade review, VTIL admission; one `DecisionCycle` shared by backtest and live, backtest engine with DSR/PBO/walk-forward and a leakage switch, session runner, CLI; continuous-learning engine (`trading/vati/learning`) with a reduce-only `LearningBoundary`, environment-weighted evidence, ex-ante hindsight guard, automatic demotion only, broker learning, counterfactuals, research priority, failure-cluster candidates, ledger reports, Hermes continuity bridge and curriculum gates, wired into the cycle; gateway trading surface (`/v1/trading/status`, `/tickets`, owner-signed `/halt` and ticket confirmation) with `TRADING_LEDGER_UNAVAILABLE`; learning A5 patterns; stack lock 4.0.0 with build status. Evidence: 317 tests passed, `induce_gate_failures` 13/13, VTIL probe GREEN.
- Fail-closed hardening: unsigned release refused; `/health` `ok` tracks Hermes; Project Truth PUT requires internal token; Google mesh defaults unverified until evidence; Rive load failures fall back to Canvas.

## EXTERNALLY BLOCKED / REQUIRES LIVE CERTIFICATION

- VATI Rev 4 is a Development Authority Candidate until owner acceptance (A4). Builds A–F are complete on synthetic data; real-data backtests (Parquet lake, Dukascopy/TrueFX), the NautilusTrader donor gate (Python 3.12), PostgreSQL ledger, live MT5 bridge worker, demo trading with transports, ZSE broker verification (VATI-ZSE-F001) and any LIMITED_LIVE mandate remain external gates. Adapters exist as fail-closed contracts without live transports.

- Google credential planes are authenticated on Hermes and imported into Van as `CONFIGURED` (not `READY` without canary receipts).
- Antigravity live generation remains `CAPACITY_LIMITED` (Jules fallback). Other Google planes are not failed by Antigravity quota.
- Notebook Enterprise / ADK-A2A require eligible owner-administered Google Cloud/Enterprise setup.
- Live Hermes install is certified on `dial-hermes-control` (2026-09-15). Local Project Truth mounts for van/dial/dde/gtr/goat/aeci are resolved on this workstation. Physical Samsung certification, `.riv` authoring, production signing, and GitHub workflow-scope install remain external gates.

## SUPERSEDED / FORBIDDEN

- VATI Rev 1 blueprint and the continuous-learning integration Rev 1 upload as active intent (retained as provenance under `docs/archive/`); Rev 2/2.1/3 as authority where they differ from Rev 4.
- Any learning output that promotes a capsule, raises a multiplier above 1, writes a mandate/ceiling, admits itself as knowledge or holds broker credentials in memory.
- Any model or research output that sends, sizes, modifies or cancels a broker order; multipliers above 1; rounding a lot size up to the venue minimum; a mandate that omits a hard-forbidden behaviour.

- Embedded/on-device second VAN agent loop.
- Consumer Gemini web scraping as a model credential.
- A single Google master credential shared across capability families.
- Copying/exporting Google browser cookies or sessions.
- Treating `CONFIGURED` as proof of live success.
- Direct Google project mutation that bypasses Hermes, Project Truth, grants, action classes, audit or evidence.

See `docs/EXTERNAL_GATES.md` for exact live gates.
