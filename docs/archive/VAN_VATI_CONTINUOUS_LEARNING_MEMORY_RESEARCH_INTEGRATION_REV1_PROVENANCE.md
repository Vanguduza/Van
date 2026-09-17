# VAN / VATI Continuous Learning, Memory & Research Integration — Rev 1 (provenance record)

**Status:** superseded as provenance by `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`, Part L.
**Origin:** owner-uploaded integration document reviewed in the build session on 2026-09-16. The upload was
reviewed in-session and was not committed verbatim; this note records what it proposed, what was kept, and
what Rev 4 changed, so the design lineage stays auditable.

## What Rev 1 proposed (sections as numbered in the upload)

| § | Proposal | Rev 4 disposition |
| --- | --- | --- |
| 3, 50 | Hermes persistent memory as the continuity layer between sessions | Kept, narrowed: `HermesMemoryBridge` — `trading` namespace only, TTL per record kind, credential-shaped text refused, evidence citable only by 64-hex artifact hash, `authority = CONTINUITY_ONLY_NOT_EVIDENCE` |
| 5, 7 | Trade experience episodes as the unit of learning | Kept: `ExperienceEpisode` assembled from the hash-chained ledger (`episode_from_ledger`), sealed, written back as `TRADE_EXPERIENCE_ARTIFACT` |
| 19, 42 | Learn from no-trades / missed opportunities | Kept with a **hindsight guard**: validity judged from the frozen ex-ante snapshot hash; later path scores only over the setup's own horizon window; Risk Authority rejections are `GOOD_NO_TRADE` by definition |
| 20 | Counterfactual replay of alternative decisions | Bounded to six predefined variants on the same bar path, labelled `SIMULATED_EVIDENCE_NOT_CAUSAL`, weight 0.2, capsule-level aggregation only |
| 21 | Strategy evolution from failures | Kept: `cluster_failures` → `propose_candidate` creates a versioned capsule in RESEARCH; parent preserved; promotion stays owner-signed |
| 22 | Capsule health feeding the meta-labeller | Kept: `StrategyHealthTracker` with environment-weighted samples and hysteresis (`sustain`); demotion automatic, recovery/promotion never |
| 23 | Learning adjusts live parameters | **Replaced** by `LearningBoundary`: exactly three reduce-only live targets (`CAPSULE_HEALTH`, `REGIME_PROBABILITY`, `BROKER_PROFILE`), ≥ 30 weighted samples, evidence hashes required; every other target raises |
| 24, 43 | Broker behaviour learning from TCA | Kept: `BrokerLearner` states CERTIFIED/DEGRADED/EVENT_LIMITED/NO_SCALPING/SUSPENDED → liquidity multiplier ≤ 1; simulated execution facts weigh 0 |
| 27 | Curriculum of market conditions | Kept as eight measurable stages with the highest capsule state each unlocks (`curriculum_gate`) |
| 29, 41 | Research prioritisation | Kept, made deterministic: `ResearchPriorityEngine` scores value × tractability; meta-learning of tool value bounded [0.1, 1.5] |
| 30–32 | Daily / weekly / monthly learning cycles | Kept: computed from the ledger (`daily_report`, `weekly_report`, `monthly_report`); Hermes narrates, never computes |
| — | Environment provenance for evidence | **Added**: quantified weights per environment (LIVE 1.0 … COUNTERFACTUAL 0.2) with zero weight for simulated execution facts |
| — | Policy | **Added** A5 patterns for learning (`learning_engine_writes_mandate`, `learning_widens_risk`, `learning_raises_multiplier`, `auto_promote_strategy`, `self_admit_knowledge`, `broker_credentials_in_memory`, `memory_as_evidence`) and `trading/vati/learning/boundary` as a protected surface |

## Review verdict recorded at the time

The Rev 1 design was sound on *what* to learn from and weak on *where learning may act*. It described adaptive
parameters without a hard boundary, treated Hermes memory as a knowledge store, and let counterfactual and
missed-trade analysis imply what "should" have happened using information not available at decision time. Rev 4
keeps every learning source and adds the boundary, the environment weights and the ex-ante guard, then wires the
result into the shared `DecisionCycle` so backtests and live sessions learn through the same code path.
