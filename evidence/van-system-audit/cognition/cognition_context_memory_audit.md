# VAN Cognition / Context / Memory / Learning Layer Audit

Repository: /home/user/Van, branch `claude/van-system-audit-ysgtcd`, HEAD `dff38a0`.
Mode: read-only, evidence-first. No repository file modified. Tests run with `/usr/local/bin/python3 -m pytest`
(the `pytest` on PATH is a uv-tool install lacking `httpx`; it errors at collection for every in-scope file).
Probe DB: `/tmp/claude-0/-home-user-Van/67fcd868-0be8-5c87-8497-65bef31122ee/scratchpad/probe.db`.

All paths below are relative to `/home/user/Van/backend/van_gateway/` unless stated otherwise.

---

## 0. Headline findings

1. **There is no LLM inference anywhere in scope.** Every "reasoning", "understanding", "calibration", "eval" and
   "evolution" module is deterministic bookkeeping over SQLite rows. The only model-adjacent behaviour in scope is
   the Stagehand browser adapter used by the NotebookLM consumer provider (`knowledge/notebook.py:749-768`), which
   delegates semantic page interaction to an external Browser Fabric service. Grep for
   `embed|vector|faiss|chroma|pgvector|openai|anthropic|ollama` across production code returns nothing
   (only docstrings saying "no embedding"/"not LLM guessing", e.g. `projects/router.py:83`).
2. **CriticalReasoningKernel does not reason.** `reasoning/kernel.py:192-247` takes every field of a
   `ReasoningAssessment` (facts, assumptions, alternatives, critic findings, verifier findings, confidence) as
   caller-supplied keyword arguments, checks two shape rules (alternative count >= mode minimum; a fact flagged
   `factual_authority` must have a non-empty `source` string), and INSERTs the row. There is no solver pass, no
   critic pass and no verifier pass in code. Probe: an assessment with a fabricated "sourced" fact
   `{"statement":"sky is green","factual_authority":True,"source":"made-up"}`, four one-letter alternatives and
   `confidence=0.99` was persisted and reports `is_actionable=True`.
3. **Nothing supplies those records.** The matrix says the kernel and calibration engine are "consumed by Hermes"
   (`docs/project-state/UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json:420`). The Hermes pack in
   `/home/user/Van/hermes/` contains no such consumer: the owner-runtime MCP tool list
   (`hermes/mcp/owner_runtime_stdio.mjs:50-70`) exposes context/knowledge/research/action tools only; there is no
   `understanding_observe`, no `reasoning_assess`, no `premise_assess`, no calibration tool. There is no HTTP route
   for `assess`, `assess_premise`, `record_assumption` or `calibrate` at all (`understanding/api.py:85-198` only
   reads `sycophancy_metrics()` at line 196). The Hermes policy hook (`hermes/policy/van_policy_hook.py`) is an
   A1-A5 allow/deny evaluator and writes nothing.
4. **The canonical owner-context store has no production writer for any authority above INFERRED.**
   The only production call sites of `admit_fact`/`admit_edge` are `runtime_api.py:169,178`, both gated by
   `_require_hermes_memory_candidate` (`runtime_api.py:122-124`) which raises 403 unless
   `authority == INFERRED and source_trust == MODEL_DERIVED`. Default readiness, graph and lexical queries
   exclude INFERRED (`context/service.py:199-200,393-394`; `context/retrieval.py:222-223,241-242`;
   `HotContextCapsuleRequest.allow_inferred=False` at `context/retrieval.py:89`). Probe: an INFERRED fact admitted
   the only way production allows is `MISSING` to default readiness and yields 0 default lexical hits.
   Consequently, in a deployed system the CANONICAL_OWNER / PROJECT_TRUTH / VERIFIED_* tiers are empty unless
   someone writes SQL by hand.
5. **The command path seals an empty context.** `orchestrator.py:403-407` calls
   `compile_snapshot(req.command_id, [], live_state_refs=..., policy_refs=...)` with zero requirements.
   `readiness()` over an empty list is `CURRENT` (`context/service.py:239`), so the snapshot always succeeds with
   `fact_ids=[]` (probe confirmed: `fact_ids [] kernel_revision 0`). The "canonical owner context" forwarded to
   Hermes (`orchestrator.py:430-437,520`) is therefore a snapshot id, a digest, the live-state refs (project truth
   SHA) and policy refs; it carries no owner facts.
6. **Owner-model poisoning is one internal token away.** `OwnerCognitiveModel.observe` promotes to CONFIRMED after
   three distinct `episode_ref` strings for non-autonomy fields (`understanding/owner_model.py:190-194,175`).
   Episode refs are free-form strings, never checked against missions or any episode store. Probe: three
   observe calls with `ep-a`, `ep-b`, `ep-c` produced `state=CONFIRMED, owner_confirmed_at_ms=None`, and
   `RelationshipCalibrationEngine.calibrate` then returned `verbosity=TERSE` with reason
   "owner-confirmed preference for terse updates" — a claim of owner confirmation that never happened
   (`reasoning/calibration.py:130-133` reads `actionable()` which filters on `state='CONFIRMED'` only,
   `understanding/owner_model.py:268-273`).
7. **Test status: 86/86 pass** across the nine in-scope test files (14.8 s). Every test constructs the class under
   test directly or calls `/v1/runtime/*` with a mocked `httpx.MockTransport`; none exercises a Hermes-originated
   flow or the `/v1/understanding`, `/v1/eval`, `/v1/autonomy`, `/v1/technology-radar` HTTP routes
   (grep across `tests/` for those paths: no hits outside comments).

---

## 1. Module-by-module runtime behaviour, callers, classification

Classification scale: ABSENT / STUB / SIMULATED / PARTIAL / IMPLEMENTED_BUT_ISOLATED / INTEGRATED / E2E_VERIFIED.
"INTEGRATED" here means a production, non-test code path in this repository invokes it on a real request.
"IMPLEMENTED_BUT_ISOLATED" means the code is real and tested but only reachable through an API that nothing in
this repository calls, or by no code at all.

### 1.1 context/models.py (197 lines)
- Pydantic enums and records: `EpistemicState` (10 tiers, `:9-19`), `SourceTrust` (`:22-28`), `SensitivityClass`
  (`:31-35`), `ReadinessState` (`:38-43`), `OwnerFactCandidate/Record` (`:52-80`), `ContextRequirement` (`:83-88`),
  `ContextSnapshot` (`:105-116`), edge models and `ContextGraphQuery` with bounds (max_depth 1..3, max_edges
  1..256, <=32 seeds, `:148-187`).
- Callers: `runtime_api.py:14`, `orchestrator.py` (indirectly), `knowledge/*` (SourceTrust/EpistemicState),
  `research/exa.py:12`.
- Classification: **INTEGRATED** (data model used on the command path).

### 1.2 context/service.py — OwnerContextService (504 lines)
- Does: admission validation (`:75-91`: SECRET rejected; UNTRUSTED_EXTERNAL/MODEL_DERIVED cannot claim a
  high-authority tier; CONFIRMED_LEARNED needs owner/system provenance; valid window sanity), monotonic
  `owner_context_revision` in `runtime_meta` (`:93-107`), fact INSERT with supersession closing the prior
  `valid_until_ms` (`:109-163`), deterministic requirement resolution ordered by authority rank → valid_from →
  revision → confidence (`:187-205`), same-authority conflict → `CONFLICTED` (`:213-222`), `max_age_ms` staleness →
  `STALE` (`:225-227`), snapshot sealing with SHA-256 digest into `context_snapshots` (`:245-295`), bounded
  temporal BFS over `owner_context_edges` (`:405-478`), scope export/erase (`:480-505`).
- Callers (production): `runtime_api.py:99` (constructed), `:169,178,186,207,213,228,233` (routes, internal-token
  gated); `orchestrator.py:403` (`compile_snapshot` with `[]` requirements on every owner command).
- Classification: **INTEGRATED** for snapshot sealing (but with no requirements, see §0.5); **IMPLEMENTED_BUT_ISOLATED**
  for the authority/readiness/conflict logic, because no production writer can populate the non-INFERRED tiers it
  arbitrates (§0.4).

### 1.3 context/retrieval.py — ContextRetrievalService (463 lines)
- Does: lexical scoring by NFKC-casefolded token overlap with per-field weights (subject 1600, predicate 1300,
  value 700; exact-match bonuses 12000/10000/7000; substring bonuses `exact_bonus//8`, `//12`) at `:191-212,272-279`;
  candidate pre-filter by SQL authority CASE ordering with `LIMIT candidate_limit+1` where candidate_limit =
  clamp(max_results*32, 256, 2048) (`:214-250,259`); ranking key `(-score, -authority_rank, -confidence, -revision,
  kind, id)` (`:296-303,331-338`); hot capsules = digest of (request hash, kernel revision, readiness state, fact
  refs, graph refs, lexical refs) cached in an in-memory dict `_hot_cache` with TTL 1-300 s and revision check
  (`:171,368-461`). Module docstring `:161-166` states no embedding/model/remote call, which the code honours.
- Callers: `runtime_api.py:100,191,200` only. Hermes MCP exposes `context_lexical_query` and `context_hot_capsule`
  (`hermes/mcp/owner_runtime_stdio.mjs:54-55,77-78`) but that is an agent tool, not a code path in this repo.
- Classification: **IMPLEMENTED_BUT_ISOLATED** (reachable only by internal-token API; no in-repo caller).

### 1.4 context_compiler/compiler.py — ContextCompiler / ContextPacket (304 lines)
- Does: given `dict[ContextSection, list[Claim]]`, drops claims whose `project_id` differs from the packet's
  (`:182-188`), drops ill-formed claims (`:190-194`), marks stale ones via per-class TTL (`:197-205`), scores
  `section_priority + class bonus + int(provenance.confidence*10) - 30 if stale + 5 if contested` (`:272-293`),
  packs by score under a token budget estimated as `len(json)//4` (`:151-154,231-252`), keeps contradiction pairs
  together (`:218-223,236-252`).
- Callers: **none** in production. Only `tests/test_epistemics_context_understanding.py:110-200`.
  The matrix admits this (`...MATRIX.json:418`).
- Classification: **IMPLEMENTED_BUT_ISOLATED** (pure function, never called; the `Claim` objects it needs are not
  produced anywhere either — see §1.5).

### 1.5 epistemics/models.py (213 lines)
- Does: `SemanticClass` enum with `is_factual_authority` (FACT_VERIFIED, PROJECT_TRUTH only, `:44-50`),
  `requires_provenance` (`:57-63`), `is_speculative` (`:65-71`); `DEFAULT_TTL_MS` (`:81-91`); `Provenance`
  (`:94-105`); `Claim` with `staleness_at_ms`, `is_wellformed`, `as_context_line` (`:108-162`);
  `FORBIDDEN_SELF_PROMOTIONS` frozenset of nine (from,to) pairs and `may_promote` (`:184-201`).
- Callers: `context_compiler/compiler.py:39` (isolated), `reasoning/kernel.py:36` (only for `SemanticClass` in
  `assess_premise`). `may_promote` and `FORBIDDEN_SELF_PROMOTIONS` are referenced by **no production code**;
  `AdmissionOutcome`/`AdmissionVerdict` (`:165-177`) are defined and never used anywhere including tests.
  No table stores `Claim`s; no code constructs them outside tests.
- Classification: **IMPLEMENTED_BUT_ISOLATED** (typed vocabulary with no enforcement point).

### 1.6 reasoning/kernel.py — CriticalReasoningKernel (444 lines)
- Does: `ChallengeMode` with minimum alternative counts 1/2/3/4 (`:40-58`); `required_mode()` (`:64-69`);
  `assess()` builds a `ReasoningAssessment` from caller-supplied lists, refuses if
  `recommended_next_action and len(alternatives) < minimum` (`:232-238`) or a `factual_authority` fact has empty
  `source` (`:241-245`), then INSERTs into `reasoning_assessments` (`:249-271`). `record_assumption`/
  `resolve_assumption`/`blocking_assumptions`/`assert_safe_for_irreversible_work` over `assumption_ledger`
  (`:281-348`; VERIFIED requires non-empty evidence refs `:322-324`). `assess_premise` derives
  `agreed_without_evidence = not corrected and not refs and class in {FACT_VERIFIED, FACT_UNVERIFIED}`
  (`:383-387`) and INSERTs into `premise_assessments`; `sycophancy_metrics` aggregates (`:404-429`).
- What it is NOT: there is no function that generates alternatives, critic findings, verifier findings,
  counterfactual answers or a confidence value. `critic_findings` and `verifier_findings` are parameters
  (`:208-209`). `missing_counterfactuals` only compares question strings (`:273-277`).
- Callers: `understanding/api.py:68` constructs it; the only invocation is `sycophancy_metrics()` at `:196`
  inside `GET /v1/eval`. `assert_safe_for_irreversible_work` is called by **no executor** (grep across
  `mission/`, `automation/`, `browser/`, `action/`: none). `reasoning/calibration.py:30` imports only
  `ChallengeMode, required_mode`.
- Classification: **IMPLEMENTED_BUT_ISOLATED** as a ledger; **ABSENT** as a reasoner. The matrix label
  "solver/critic/verifier separation" (`...MATRIX.json:105`) describes three JSON columns, not three passes.

### 1.7 reasoning/calibration.py — RelationshipCalibrationEngine (200 lines)
- Does: computes a `Calibration(challenge_mode, verbosity, evidence_presentation, interrupt_threshold, reasons)`
  from `required_mode(consequential, irreversible)` floor (`:108`), `prior_corrections>=2 → CRITICAL` (`:115-119`),
  `van_confidence<0.4 → CRITICAL` (`:123-125`), and substring matching of CONFIRMED owner-model values against
  needle lists ("terse","brief",...; "evidence","proof",...; "minimal","rarely",...) (`:130-152,184-191`).
- Callers: **none** in production (`grep RelationshipCalibrationEngine` outside its package and tests: nothing).
- Classification: **IMPLEMENTED_BUT_ISOLATED**. Also inherits the poisoning issue in §0.6.

### 1.8 understanding/owner_model.py — OwnerCognitiveModel (374 lines)
- Does: `observe()` upserts an assertion keyed by (owner, field, value, project) (`:133-182`,`_find :305-313`);
  ladder `>=2 distinct episode_refs → CANDIDATE`, `>=3 → CONFIRMED` unless field in
  `AUTONOMY_BEARING_FIELDS` (`:79-86,184-194`); confidence `min(0.95, 0.2+0.25*(n-1))` (`:175`); REJECTED is sticky
  (`:165-168`); `confirm/correct/reject/contest` (`:198-258`); `actionable()` = CONFIRMED and not superseded
  (`:268-278`); `understanding()` grouped view (`:280-301`).
- Callers: `understanding/api.py:64` → routes at `:88-151` (`GET /v1/understanding`, POST confirm/correct/reject,
  POST `/observe` internal-token only). `reasoning/calibration.py:92` (isolated). `evolution/vaneval.py:254-259`
  reads the table for the knowledge_memory dimension.
- Who feeds `/observe`? Nothing in this repository. Not in the Hermes MCP tool list; not in any skill; not in the
  Android client (`android/.../VanGatewayClient.kt:282-310` only reads/confirms/corrects/rejects/reverts).
- Classification: **IMPLEMENTED_BUT_ISOLATED** (reachable only by API, fed by nothing).

### 1.9 understanding/memory.py (578 lines)
- `SharedVocabularyRegistry` (`:56-118`, upsert on (term, project_id), project-scoped resolve),
  `IntentContinuityGraph` (`:151-281`, nodes/edges/missions, `mark_stale` after 90 days `:162,271-281`),
  `StrategicMemory` (`:297-346`, `already_rejected` is a case-insensitive substring test `:342-346`),
  `DecisionFingerprints` (`:352-421`, `falsified()` = rows where outcome, inferred_reason and reassessment are all
  non-null — it does not compare anything `:411-421`), `CognitiveComplementMap` (`:427-484`),
  `SymbioticGrowthLedger` (`:487-563`, record/confirm/revert/effective/awaiting_owner).
- Callers: `understanding/api.py:65-67` constructs vocabulary, complement and growth; only READ paths are exposed
  (`:93-98`) plus growth confirm/revert (`:127-138`). `IntentContinuityGraph`, `StrategicMemory`,
  `DecisionFingerprints` are constructed by **nothing** in production. No route writes vocabulary, complement,
  intent, strategic memory or fingerprints.
- Classification: **IMPLEMENTED_BUT_ISOLATED** (all six); three of six have zero production constructors.

### 1.10 understanding/api.py — UnderstandingApi (201 lines)
- Routes: `GET /v1/understanding` (`:88-99`), confirm/correct/reject (`:101-125`), adaptation confirm/revert
  (`:127-138`), `POST /v1/understanding/observe` internal (`:140-151`), `GET /v1/permissions` + revoke
  (`:153-162`), `GET /v1/technology-radar` (`:164-169`), `GET /v1/autonomy` (`:171-190`), `GET /v1/eval` (`:192-198`).
- Wired: `app.py:47,239,304`; auth split at `app.py:325-330` (only `/observe` is internal-control; the rest are
  owner-ingress).
- Classification: **INTEGRATED** as HTTP surface; **not E2E_VERIFIED** (no test hits these routes; Android
  `MissionRepository` wraps them (`android/.../MissionRepository.kt:96-129`) but no Compose screen instantiates
  `MissionRepository` — grep for `MissionRepository(` finds only the class declaration).

### 1.11 evolution/radar.py (532 lines)
- `ExternalRealityModel` (`:43-95`, INSERT/SELECT over `external_reality`, source_ref required `:60-63`),
  `AIEvolutionRadar` (`:170-297`, state machine `_FORWARD :115-128`, ADMITTED requires
  `benchmark_digest && security_profile && licence` plus `owner_decision_ref` `:247-255`),
  `BenchmarkHarness` (`:303-379`, 14 suite names, `record_run` stores caller-supplied pass/fail, `regressed()`
  compares last two runs), `StrategyLearning` (`:394-519`, PREFERRED needs `eval_run_id` and >=10 runs at >=90%
  `:403-408,464-474`; `auto_demote` <60% over >=3 runs `:487-511`).
- Callers: `understanding/api.py:72` constructs `AIEvolutionRadar` for two read routes. `ExternalRealityModel`,
  `BenchmarkHarness`, `StrategyLearning` have **no production constructor**. `record_outcome`/`preferred_for` are
  invoked by no executor; `BenchmarkHarness.record_run` is invoked by no benchmark runner (the CI benchmark
  `backend/tools/benchmark_context_retrieval.py` measures latency and writes JSON; it does not call this class).
- Classification: `AIEvolutionRadar` **IMPLEMENTED_BUT_ISOLATED** (read-only API, no discover/transition route);
  the other three **IMPLEMENTED_BUT_ISOLATED** with zero callers. None is a feedback loop: no code path records a
  strategy outcome or a benchmark result from a real run.

### 1.12 evolution/vaneval.py — VanEval (388 lines)
- Does: for 11 dimensions, three are declared unmeasurable (`:72-86`); eight compute a score from row counts:
  architecture `6 + 4*bound/activities` (`:184-205`), authority `0.0 if any VERIFIED_SUCCESS without receipt else
  9.7` (`:207-231`), agentic `terminal/total*10` (`:233-251`), knowledge `0 or 9.6` (`:253-272`), proactive
  `10-20*dup_rate` (`:274-293`), self_improvement `9.5 or 0` (`:295-314`), critical_reasoning `10-100*rate`
  (`:316-335`), adaptive `0 or 9.5` (`:337-356`). Each run INSERTs 11 rows into `eval_runs` (`:125-140`).
  `overall_score` is deliberately `None` (`:153`).
- Callers: `understanding/api.py:73,195` (`GET /v1/eval`). Nothing consumes `eval_runs`; `StrategyLearning.promote`
  accepts any string as `eval_run_id` without checking it exists (`radar.py:450-485`).
- Classification: **IMPLEMENTED_BUT_ISOLATED** (API-reachable scoreboard; scores are threshold constants
  9.7/9.6/9.5 applied to row counts, not measurements of behaviour).

### 1.13 proactive/autonomy.py (338 lines)
- `AutonomyLevel` S0-S5 (`:34-55`), `MAX_EARNED_LEVEL=S2` (`:62`), `FALSE_SUCCESS_PENALTY=10` (`:67`),
  `DomainTrust` arithmetic (`:88-159`), `DomainTrustService.record/grant/assert_may_run` (`:169-261`),
  `ProactivePolicyService.grant_policy/may_create/policies/revoke` (`:264-326`).
- Callers: `understanding/api.py:70-71` (constructed), `:174-190` (`GET /v1/autonomy` reads). `record()`,
  `grant()`, `assert_may_run()`, `may_create()` are invoked by **no executor or scheduler** (grep in `mission/`,
  `automation/`, `browser/`, `notifications/`, `decisions/`: none).
- Classification: **IMPLEMENTED_BUT_ISOLATED**. No proactive mission creation path exists to be gated.

### 1.14 knowledge/service.py — KnowledgeRuntime (295 lines)
- Constructs the four providers from settings (`:47-113`), `startup()` ensures the knowledge schema (`:115-116`),
  `status()` (`:118-131`), thin delegations (`:133-179`), and `execute_authorized_action` which maps
  `ActionRuntime` executions to Notebook mutations and back to verification (`:190-296`).
- Callers: `runtime_api.py:104,128,148,235-330`.
- Classification: **INTEGRATED** as API plane (internal-token only); **not E2E_VERIFIED** against any live
  provider in this repo.

### 1.15 knowledge/vekl.py — VeklKnowledgeProvider (216 lines)
- Does: `GET {vekl_base_url}/v1/missions/{mission_id}/vekl` with `X-Session-Id`, `X-Principal-Id`, optional
  Bearer (`:77-125`, retries on 429/5xx and connect/timeout errors `:102-104,116-121`); flattens the JSON to
  (path, value) leaves capped at 4096 (`:127-148`); scores leaves by token overlap
  (`5*path_hits + 2*value_hits + 8 substring-in-path + 4 substring-in-value`, `:154-169`); persists each selected
  leaf as `knowledge_evidence` with `source_trust=VERIFIED_SYSTEM`, `epistemic_state=EXTERNAL_EVIDENCE`
  (`:185-195`); `certify()` runs one query and writes READY into `knowledge_provider_certifications` (`:207-217`).
- Live endpoint: `config.py:79-84` defaults `vekl_enabled=False, vekl_base_url=""`. The only VEKL server in the
  repository (`trading/vekl/server.mjs:111-115`) serves `/health`, `/registry/validate`, `/activation/*`,
  `POST /resolve` — **not** `/v1/missions/{id}/vekl`. The docstring names the target as "DDE's canonical mission
  VEKL projection" (`:26`), i.e. an external DIAL system not present here. Test coverage uses
  `httpx.MockTransport` (`tests/test_knowledge_runtime.py:59-80`).
- Who decides when to query VEKL: nobody in code. It is step 6 of a prose protocol for the Hermes agent
  (`hermes/profile/van/AGENTS.md:37`) and a skill instruction (`hermes/skills/gemini-notebook/SKILL.md:28,34`).
- Classification: **IMPLEMENTED_BUT_ISOLATED** (real HTTP adapter; no configured endpoint; no in-repo server
  implements the contract; no in-repo caller).

### 1.16 knowledge/obsidian.py — ObsidianKnowledgeProvider (341 lines)
- Does: real filesystem indexer over `vault_path/**/*.md` (`:179-268`) with symlink/size/UTF-8 guards
  (`:197-225`), frontmatter/tag/link parsing (`:109-147`), secret-pattern blocking (`:30-35,160-166`), incremental
  mtime/size skip (`:208-212`), soft delete (`:253-262`), FTS5 upsert when available (`:168-177`) with a BM25 query
  path (`:274-288`) and a token-overlap fallback (`:289-300`); query persists hits as `knowledge_evidence`
  with `TRUSTED_OWNER_FILE` (`:313-327`).
- Live: `config.py:86-90` defaults disabled/empty. Tests exercise a real tmp vault (`tests/test_knowledge_runtime.py:100`).
- Classification: **IMPLEMENTED_BUT_ISOLATED** (genuine adapter, API-reachable, unconfigured, no in-repo caller).

### 1.17 knowledge/notebook.py (1022 lines)
- `CloudAccessTokenProvider`: RS256 JWT service-account exchange or token file (`:49-125`) — real.
- `NotebookOperationStore`: idempotent operation ledger with digest conflict detection (`:128-188`).
- `NotebookEnterpriseProvider`: Discovery Engine `v1alpha` REST (`:211-237`), create with preexisting-title
  preflight and readback (`:277-332`), batch/file source add with completion polling (`:404-491`), delete with
  absence readback (`:493-571`). Ambiguous timeouts → `CONFLICTED_STATE`, never replayed (`:447-451,503-507`).
- `NotebookConsumerProvider`: routes through `BrowserTaskService` + `HttpBrowserHarnessAdapter` +
  `StagehandAdapter` (`:574-653`), `ask()` (`:738-811`) and `create_note()` (`:828-1021`) with readback extraction
  and evidence sealing. This is the only place in scope where an LLM-backed component (Stagehand, an external
  service) is invoked, and it is for browser interaction, not for VAN reasoning.
- Live: all disabled by default (`config.py:92-107`); consumer requires Browser Fabric (`browser_enabled=False`).
- Classification: **IMPLEMENTED_BUT_ISOLATED**; enterprise path tested against `MockTransport`; consumer path
  tested with fakes (`tests/test_knowledge_runtime.py:221-260,338`).

### 1.18 knowledge/evidence.py, schema.py, models.py
- `KnowledgeEvidenceStore.persist/certify/certification` (`evidence.py:13-98`) → tables in `schema.py:25-50`.
  `KnowledgeSchema.ensure` also creates `obsidian_documents`, `notebook_operations`, and FTS5 if available
  (`schema.py:17-106`). Models are pydantic request/result shapes with bounds (`models.py`).
- Classification: **INTEGRATED** (schema ensured at startup via `runtime_api.py:128`).

### 1.19 research/exa.py — ExaResearchService (145 lines)
- Real `POST {base_url}/search` with `x-api-key` (`:73-75`); fail-closed authorisation (`egress_enabled`,
  key present, egress class, secret-pattern rejection `:33-43`); persists every result into `research_evidence`
  with `UNTRUSTED_EXTERNAL` (`:98-108`); canary writes `exa_ready_evidence_pointer` (`:118-129`).
- Callers: `runtime_api.py:105-111,402-420`. Defaults disabled (`config.py:51-54`).
- Classification: **IMPLEMENTED_BUT_ISOLATED** (API-reachable; disabled by default; no in-repo caller).

### 1.20 Extended "not called by anything" list (beyond the matrix's three)
Matrix (`...MATRIX.json:411-421`) lists ContextCompiler, VerifierRegistry, CriticalReasoningKernel,
RelationshipCalibrationEngine as uncalled and OwnerCognitiveModel/AttentionScorer/DomainTrustService/
AIEvolutionRadar/VanEval as "reachable only by API". Verified, and the list must be extended with:
- `ExternalRealityModel`, `BenchmarkHarness`, `StrategyLearning` (no production constructor).
- `IntentContinuityGraph`, `StrategicMemory`, `DecisionFingerprints` (no production constructor).
- `SharedVocabularyRegistry`, `CognitiveComplementMap`, `SymbioticGrowthLedger` (constructed; only reads and
  growth confirm/revert exposed; no write route, no writer).
- `ProactivePolicyService` (constructed; read-only route).
- `epistemics.may_promote` / `FORBIDDEN_SELF_PROMOTIONS` / `AdmissionOutcome` / `AdmissionVerdict` (no caller).
- `CriticalReasoningKernel.assess`, `record_assumption`, `assert_safe_for_irreversible_work`, `assess_premise`
  (no route, no caller; only `sycophancy_metrics` is reachable).
- `ContextRetrievalService` (API-only; not on the orchestrator path).
- `AttentionScorer.score` (API only reads `metrics()`; `decisions/service.py:9,57` uses the older
  `AttentionEngine`, not the scorer).

---

## 2. Is there any LLM inference? What does the kernel actually do?

- No. Production code in scope contains no model client, no embedding, no vector index. `grep -rn -i
  "embed|vector|faiss|chroma|pgvector|openai|anthropic|ollama"` over `van_gateway/` (excluding tests) yields
  only prose. `HermesBridge` (`hermes/bridge.py:18-19`) is an HTTP client to the Hermes runtime ("Never launches
  models directly") and is the only place model work is delegated, via `create_run` (`:58-75`) from
  `orchestrator.py:497`.
- `CriticalReasoningKernel.assess` (`reasoning/kernel.py:192-247`) validates the *shape* of a record someone else
  supplies: (a) alternatives count vs. mode; (b) `factual_authority` facts carry a non-empty `source`. It does not
  inspect the source, evaluate the alternatives, or produce findings. `assess_premise` (`:363-402`) records a
  premise/position pair and derives one boolean.
- Intended supplier: Hermes (`understanding/api.py:8-9,144`; `...MATRIX.json:420`). Hermes-side reality: the MCP
  server (`hermes/mcp/owner_runtime_stdio.mjs`) has 20 tools; none touches `/v1/understanding`, `reasoning_*`,
  `premise_*`, or calibration. `hermes/profile/van/AGENTS.md`, `SOUL.md` and all 16 `skills/*/SKILL.md` do not
  mention observe/premise/assessment/calibration. There is also no gateway route to reach `assess` even if Hermes
  wanted to (`understanding/api.py` exposes only `sycophancy_metrics` via `/v1/eval:196`).
- Therefore "reasoning" in this layer is a schema for a ledger that is presently write-only-by-tests.

---

## 3. Memory taxonomy

Legend: W = write criteria, R = retrieval criteria, P = provenance, C = confidence, D = decay/TTL,
X = contradiction handling, Del = deletion. All stores are SQLite tables via `storage/db.py` migrations unless
marked in-memory. (Table DDL line refs are in `storage/db.py`.)

| Category | Store | Real? | W / R / P / C / D / X / Del |
|---|---|---|---|
| Conversation state | none in gateway | — | Hermes owns runs; gateway keeps `idempotency` results and `audit` (out of scope). |
| Working memory | `ContextRetrievalService._hot_cache` (`context/retrieval.py:171`) | in-memory dict | W: on capsule compile; R: by request hash + same revision + not expired (`:378-380`); D: TTL 1-300 s; lost on restart. |
| Working memory | `CloudAccessTokenProvider._cached_token` (`notebook.py:66-67`) | in-memory | token cache only. |
| Working memory | `ContextPacket` (`context_compiler`) | transient object | never persisted, never built. |
| Facts (canonical) | `owner_facts` (db.py:233-258) | table | W: `admit_fact` after `_validate_admission` (`service.py:75-91`); production route restricts to INFERRED/MODEL_DERIVED (`runtime_api.py:122-124`). R: exact (subject,predicate,scope) within validity window, authority-ranked (`service.py:187-205`); lexical (`retrieval.py:214-231`). P: `source_ref`, `source_trust`, `revision`, `content_digest`. C: `confidence_permille` 0-1000 (`models.py:60,70-75`); ranking uses authority before confidence. D: `valid_until_ms` closure on supersession (`service.py:125-129`); `max_age_ms` per requirement → STALE (`:225-227`); no background expiry. X: same-authority differing digests → CONFLICTED, both ids returned (`:213-222`); lower authority cannot supersede higher (`:123-124`). Del: `erase_scope` (`:495-505`) via `DELETE /v1/runtime/context/scope/{scope}`; also `export_scope`. |
| Facts (graph) | `owner_context_edges` (db.py:260-281) | table | W: `admit_edge` (`service.py:297-337`); same production restriction. R: bounded BFS (`:405-478`), lexical (`retrieval.py:233-250`). P/C/D same as facts. X: competing edges retained (`:411-416`). Del: `erase_scope`. |
| Facts (snapshots) | `context_snapshots` (db.py:283-296) | table, append-only | W: `compile_snapshot` when readiness CURRENT (`service.py:258-260`). Stores evidence refs **unvalidated** (probe §0: `vekl://does-not-exist` accepted). Del: none. |
| Project knowledge | none in scope | — | Project Truth lives in `projects/` (out of scope); snapshots only carry `project-truth:<id>:<sha>` refs (`orchestrator.py:399-401`). `SemanticClass.PROJECT_TRUTH` and `StrategicMemory` are unused. |
| Episodic | `supporting_episode_refs_json` inside `owner_cognitive_model` | strings only | No episode table. Refs are opaque, unverified (§0.6). `DecisionFingerprints` (db.py:939) is the nearest episodic store: no writer. |
| Preference / owner model | `owner_cognitive_model` (db.py:916-937) | table | W: `observe` (internal token) / owner confirm/correct/reject. R: `actionable()` CONFIRMED only; `understanding()` all but SUPERSEDED. P: `evidence_refs_json` (free strings). C: 0.2 + 0.25/episode, cap 0.95; owner confirm → 1.0. D: none (fields `last_revalidated_at_ms`, `temporary` exist but nothing sets/uses them except confirm). X: `contest()` exists (`owner_model.py:248-258`), no caller; two differing values for one field simply coexist. Del: none; REJECTED rows persist (sticky, `:165-168`). |
| Preference (derived) | `shared_vocabulary`, `cognitive_complement_map`, `symbiotic_growth`, `intent_nodes/edges/missions`, `strategic_memory`, `decision_fingerprints` (db.py:958-1057) | tables | W: class methods only; no production writer. R: API reads for vocabulary/complement/growth. D: `IntentContinuityGraph.mark_stale` 90 d (`memory.py:162`), no scheduler calls it. X: intent `conflicts` edges (`:247-261`). Del: none. |
| Reasoning ledger | `reasoning_assessments`, `assumption_ledger`, `premise_assessments` (db.py:1060-1119) | tables | W: kernel methods, no production caller. R: `blocking_assumptions`, `sycophancy_metrics` (30-day window `kernel.py:413`). Del: none. |
| Operational / eval | `eval_runs` (db.py:1266), `benchmark_runs` (:1227), `execution_strategies` (:1245), `technology_capabilities` (:1201), `external_reality` (:1185), `domain_trust` (:1151), `proactive_policies` (:1164), `attention_candidates` (:1127) | tables | W: `VanEval.run` on every `GET /v1/eval` (11 rows per call, unbounded growth); others no production writer. Del: none. |
| Tool state | `notebook_operations` (`knowledge/schema.py:68-84`), `knowledge_provider_certifications` (`:43-50`), `runtime_meta` keys `owner_context_revision`, `exa_ready_evidence_pointer` | tables | idempotency ledger; certification READY flags. Del: none. |
| External evidence | `knowledge_evidence` (`schema.py:25-42`), `research_evidence` (db.py:351-366), `obsidian_documents` (+FTS) | tables | W: every provider query persists every hit (unbounded; `evidence.py:29-67`). P: `source_ref`, `source_trust`, `content_digest`, `retrieved_at`. C: none stored. D: none. X: none. Del: none (Obsidian rows soft-deleted on vault removal `obsidian.py:253-262`). |

Observations:
- No store has a retention or compaction job. `knowledge_evidence`, `research_evidence`, `eval_runs` and
  `context_snapshots` grow without bound.
- Only `owner_facts`/`owner_context_edges` have an erase path. There is no owner-facing "forget" for the owner
  model, evidence, or reasoning ledgers.
- Contradiction handling exists in code for facts (CONFLICTED), the compiler (contradiction groups — unused) and
  intents (edges — unused). The owner model has no contradiction detection between values of one field.

---

## 4. Context retrieval mechanics

- **Ranking**: pure arithmetic. Facts: SQL pre-order by authority CASE → confidence → valid_from → revision
  (`retrieval.py:31-33,228,247`), then Python token-overlap score with field weights and exact/substring bonuses
  (`:191-212`), final sort `(-score, -authority_rank, -confidence, -revision, kind, id)` (`:296-303,331-338`).
  Graph: authority → confidence → revision → edge_id (`service.py:395-403,435-443`). Obsidian: BM25 via FTS5 with
  column weights (0, 8, 2, 4, 2) (`obsidian.py:280`) else token overlap. VEKL: leaf token overlap (`vekl.py:154-169`).
  Compiler (unused): `SECTION_PRIORITY + class bonus + 10*confidence - 30 stale + 5 contested` (`compiler.py:272-293`).
- **Budgets**: lexical `max_results` 1..64, candidate scan clamp 256..2048 (`retrieval.py:43,259`); graph depth
  1..3, edges 1..256, seeds <=32 (`models.py:158-180`); hot capsule scopes <=8, seeds <=16, queries <=8,
  requirements <=32, graph depth <=2, edges <=96, hits/query <=24, TTL 1-300 s (`retrieval.py:84-135`);
  compiler token budget 8000 at ~4 chars/token (`compiler.py:45,51`), unused.
- **Cross-project isolation**: by `scope` string equality in every SQL clause (`service.py:192,367;
  retrieval.py:215,234`); hot capsules iterate explicit scopes (`retrieval.py:397,411`). There is no mapping from
  `req.project_id` to a scope on the command path; the orchestrator passes no requirements at all. The compiler's
  `project_id` hard isolation (`compiler.py:182-188`) is never executed in production.
- **Stale handling**: `ContextRequirement.max_age_ms` vs `last_verified_at_ms or observed_at_ms` → STALE
  (`service.py:225-227`); blocks snapshot (`:259-260`). `STALE` is also an `EpistemicState` tier (rank 100) that
  nothing ever assigns. Epistemics TTLs (`epistemics/models.py:81-91`) apply only to unused `Claim`s.
- **Vector DB / embeddings**: none. `REV31_CONTEXT_RETRIEVAL_CERTIFICATION.md:19,56` explicitly defers semantic
  retrieval "only as an escalation" and "do not add vector or LLM retrieval". The certification's latency numbers
  come from `backend/tools/benchmark_context_retrieval.py` (exists) run in CI against a synthetic 321-fact corpus
  (`:29-38`); it certifies latency of the local path, not recall or integration.

---

## 5. Owner model / symbiosis

- **What is learned**: 12 `OwnerModelField` values (`owner_model.py:60-75`) as free-text `value` strings per field.
  Nothing else is inferred; there is no extraction from conversations, missions, or actions in this repo.
- **Admission**: OBSERVED → CANDIDATE at 2 distinct `episode_ref`s → CONFIRMED at 3 unless autonomy-bearing
  (`:184-194`); owner `confirm` → CONFIRMED/1.0 (`:198-210`); `correct` supersedes (`:212-234`); `reject` sticky
  (`:236-246`).
- **Reversibility**: `reject`, `correct` (history kept via `superseded_by`), `SymbioticGrowthLedger.revert` only
  if `reversible=1` (`memory.py:538-547`) → 409 otherwise (`api.py:135-137`).
- **Inspectability**: `GET /v1/understanding` returns fields, state, confidence, episode count, autonomy flag,
  owner_confirmed, project (`owner_model.py:280-301`) plus vocabulary, complement, effective/awaiting adaptations
  (`api.py:91-99`). Evidence refs are not returned to the owner.
- **Poisoning protections**: internal token on `/observe` (`api.py:145`; token check
  `google/control.py:12-21`); autonomy-bearing fields never auto-confirm; REJECTED sticky. Gaps: (a) episode refs
  unverified → three POSTs mint CONFIRMED and calibration reports it as "owner-confirmed" (probe §0.6);
  (b) `evidence_refs` unverified strings; (c) `project_id` is caller-supplied and only used as a key, so a
  project-scoped observation can be planted for any project; (d) no rate limit; (e) `owner_principal_id` is any
  string, no principal registry check.
- **Production feed**: none. `/v1/understanding/observe` has no caller in backend, Hermes pack, tests, or Android.
  `VanEval._knowledge` (`vaneval.py:253-272`) therefore always reports "no owner-model assertions recorded yet".

---

## 6. Learning / evolution

- `VanEval`: computes constants from row counts (§1.12); the honest "unmeasured" reporting is real
  (`vaneval.py:358-365`), but the measured scores are not measurements of quality (e.g. authority = 9.7 whenever no
  VERIFIED_SUCCESS row lacks a receipt, `:221`). No consumer of `eval_runs`.
- `StrategyLearning`: register/record_outcome/promote/auto_demote exist; no executor records outcomes; `promote`
  does not verify `eval_run_id` exists in `eval_runs`. `preferred_for` is consulted by no planner.
- `SymbioticGrowthLedger`: append/confirm/revert only; nothing records an adaptation, and nothing reads
  `effective()` to change behaviour except the owner-facing view.
- `AIEvolutionRadar`: state machine with gates; no discover/transition route; `deprecations()` read by
  `/v1/technology-radar`. No scanner feeds it.
- `BenchmarkHarness.regressed` is called by nothing (`auto_demote` uses success ratios, not benchmarks).
- Verdict: **empty frameworks with correct invariants and no loop**. No production event (mission outcome,
  verification receipt, owner correction) is wired into any of these classes.

---

## 7. Knowledge runtime adapters

- VEKL: real HTTP GET to `/v1/missions/{mission_id}/vekl` (`vekl.py:92,101`); read-only; `vekl_base_url` default
  empty; no in-repo server implements that route (`trading/vekl/server.mjs:111-115` implements `/resolve` etc.
  for the trading commander, a different consumer at `hermes/profile/van/config.yaml:123`). No deploy env in
  `deploy/` sets `VAN_VEKL_BASE_URL`/`VAN_VEKL_SESSION_ID` (grep: only trading `VAN_VEKL_URL=:9134`). WHEN to
  query is left to the Hermes agent's prose protocol (`AGENTS.md:37`).
- Obsidian: real filesystem index + FTS5 (§1.16); disabled/unconfigured by default.
- NotebookLM Enterprise: real Discovery Engine v1alpha client with JWT auth (§1.17); disabled by default.
- NotebookLM Consumer: real delegation to Browser Fabric (`BrowserTaskService`, harness, Stagehand); disabled;
  requires `browser_enabled` and an authenticated profile; the mutation path is bound to `ActionRuntime`
  authorisation (`service.py:190-296`).
- All providers persist evidence with `epistemic_state=EXTERNAL_EVIDENCE` (`evidence.py:37`) and never write
  `owner_facts` — the "evidence not truth" invariant holds in code. Nothing in VAN consumes `knowledge_evidence`
  after it is written (grep for `FROM knowledge_evidence`: none outside `evidence.py`).

---

## 8. Epistemics enforcement

- `SemanticClass`/`Claim`/`FORBIDDEN_SELF_PROMOTIONS`/`may_promote`: enforced on **no real path**. Not consulted by
  `OwnerContextService._validate_admission` (which uses the separate `EpistemicState`/`SourceTrust` vocabulary,
  `service.py:75-91`), not by `KnowledgeEvidenceStore`, not by `ActionRuntime`, not by the orchestrator. Only
  `tests/test_epistemics_context_understanding.py:68-108`.
- Two parallel taxonomies exist and are not reconciled: `context.models.EpistemicState` (10 tiers, enforced) and
  `epistemics.models.SemanticClass` (9 classes, unenforced). `PROJECT_TRUTH` appears in both.
- `AssumptionLedger` gate `assert_safe_for_irreversible_work` (`kernel.py:341-348`): no caller in `action/`,
  `mission/`, `automation/`, `browser/`.
- `REQUIRED_COUNTERFACTUALS` (`kernel.py:167-174`): only `missing_counterfactuals` string comparison; nothing
  requires them before a mission transition.
- `assess_premise`: no route, no caller; metrics exist for a ledger nobody writes.
- Enforcement that IS real (adjacent, for contrast): `_validate_admission` (SECRET, trust/authority coupling),
  `_require_hermes_memory_candidate` (`runtime_api.py:122-124`), provider secret-pattern filters
  (`obsidian.py:30-35`, `exa.py:20-25`), research egress classes (`exa.py:33-43`).

---

## 9. Tests

Command: `cd backend && VAN_DATABASE_PATH=<scratch> /usr/local/bin/python3 -m pytest -q -p no:cacheprovider <files>`

| File | Collected | Result |
|---|---:|---|
| tests/test_context_admission_api.py | 2 | pass |
| tests/test_context_graph.py | 4 | pass |
| tests/test_context_retrieval.py | 5 | pass |
| tests/test_context_snapshot_lineage.py | 1 | pass |
| tests/test_epistemics_context_understanding.py | 30 | pass |
| tests/test_knowledge_runtime.py | 9 | pass |
| tests/test_proactive_evolution_eval.py | 23 | pass |
| tests/test_relationship_calibration.py | 10 | pass |
| tests/test_hermes_bridge.py | 2 | pass |
| **Total** | **86** | **86 passed, 0 failed, 14.83 s** |

Also relevant: `tests/test_owner_runtime.py` (9 tests) covers `OwnerContextService` and Exa fail-closed behaviour
directly. Note the PATH `pytest` (uv tool) fails collection with `ModuleNotFoundError: httpx` for all nine files;
the project interpreter must be used.

Coverage character: unit tests on classes with a fresh `Store`; HTTP tests only for `/v1/runtime/context/*`
routes and their internal-token gating (`test_context_graph.py:172`, `test_context_retrieval.py:248`,
`test_context_admission_api.py:32,63`). No test hits `/v1/understanding*`, `/v1/eval`, `/v1/autonomy`,
`/v1/technology-radar`. No test drives a command through `CommandOrchestrator` and asserts what context Hermes
receives. Knowledge providers are tested with `httpx.MockTransport`, tmp vaults, and fake Stagehand.

---

## 10. TODO / FIXME / placeholder / synthetic / mock / legacy markers in scope

Production files (grep -i "TODO|FIXME|XXX|placeholder|synthetic|mock|stub|not yet|legacy|preview API|no owner input"):
- `context_compiler/compiler.py:41` — `DECISION (recorded, no owner input): 8000 tokens`
- `context_compiler/compiler.py:47,68` — `DECISION (recorded)` (chars/token; section priority)
- `epistemics/models.py:75,181` — `DECISION (recorded)` (TTLs; forbidden promotions)
- `reasoning/calibration.py:75` — `DECISION (recorded, no owner input)`
- `understanding/owner_model.py:15` — `DECISION (recorded, made without owner input)` (ladder thresholds)
- `understanding/memory.py:159` — `DECISION (recorded)` (90-day intent staleness)
- `evolution/vaneval.py:68` — `DECISION (recorded, no owner input)` (unmeasurable dimensions)
- `evolution/vaneval.py:152,156` — "cannot yet do / cannot yet evidence"
- `evolution/vaneval.py:291` — `"nuisance_rate_note": "needs owner dismissal feedback; not yet collected"`
- `evolution/radar.py:403` — `DECISION (recorded)` (PREFERRED thresholds)
- `proactive/autonomy.py:58,64` — `DECISION (recorded, no owner input)` (S2 cap; penalty 10)
- `knowledge/notebook.py:416-418` — comment: retry does not re-issue mutation because "provider-side request IDs
  are not documented for this preview API"
- `knowledge/notebook.py:597` — `**_legacy: Any` swallowed constructor kwargs
- `knowledge/notebook.py:326,788,981` — `__import__('van_gateway.context.models', ...)` dynamic import hack
  (module already imports `van_gateway.context.models`-dependent names; smells like a merge artefact)
- `config.py:102` — `notebook_consumer_profile_dir: str = ""  # legacy; direct Playwright is no longer used`
- `context/service.py:384` — the word "placeholders" is SQL parameter placeholders, not a stub marker.
- `evolution/radar.py:12-16` docstring claims `ExternalRealityModel` hands contradictions "to the reasoning
  kernel to reconcile" — no such hand-off exists in code.
- `reasoning/kernel.py:1-24` docstring claims "Solver, critic and verifier are separate passes" — they are
  separate JSON columns filled by the caller.
Docs:
- `docs/project-state/UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json:420` — "consumed by Hermes, not the
  gateway" for kernel/calibration: no Hermes consumer exists in the repository.
- `...MATRIX.json:105,141` — WS9/WS13 "BUILT" notes describe ledgers, not reasoning.
- `...MATRIX.json:411` — the integration note itself concedes BUILT ≠ called; this audit confirms and extends.
- `REV31_CONTEXT_RETRIEVAL_CERTIFICATION.md:29-31` — benchmark corpus is synthetic (321 facts, 160 edges).
Tests (mocks, for completeness): `tests/test_knowledge_runtime.py:59-80,142-158,180-197,249,285-295,316-326`
(`httpx.MockTransport`, `fake_create`).

---

## 11. Consolidated classification table

| Module / class | Classification | Evidence |
|---|---|---|
| context.models | INTEGRATED | used on command path via service |
| context.service.OwnerContextService | INTEGRATED (snapshot) / IMPLEMENTED_BUT_ISOLATED (authority tiers) | `orchestrator.py:403` with `[]`; `runtime_api.py:122-124` |
| context.retrieval.ContextRetrievalService | IMPLEMENTED_BUT_ISOLATED | only `runtime_api.py:191,200` |
| context_compiler.ContextCompiler | IMPLEMENTED_BUT_ISOLATED (no caller) | matrix `:418` |
| epistemics.models | IMPLEMENTED_BUT_ISOLATED (no enforcement point) | §8 |
| reasoning.kernel.CriticalReasoningKernel | IMPLEMENTED_BUT_ISOLATED as ledger; ABSENT as reasoner | `kernel.py:192-247`, probe §0.2 |
| reasoning.calibration.RelationshipCalibrationEngine | IMPLEMENTED_BUT_ISOLATED | no caller |
| understanding.owner_model.OwnerCognitiveModel | IMPLEMENTED_BUT_ISOLATED (API, unfed) | no `/observe` caller |
| understanding.memory.* (6 classes) | IMPLEMENTED_BUT_ISOLATED; 3 with no constructor | §1.9 |
| understanding.api.UnderstandingApi | INTEGRATED (routes) but untested over HTTP | `app.py:239,304` |
| evolution.radar.* (4 classes) | IMPLEMENTED_BUT_ISOLATED; 3 with no constructor | §1.11 |
| evolution.vaneval.VanEval | IMPLEMENTED_BUT_ISOLATED (API) | `api.py:195` |
| proactive.autonomy.* | IMPLEMENTED_BUT_ISOLATED (read API only) | §1.13 |
| knowledge.service.KnowledgeRuntime | INTEGRATED (API plane), not E2E | `runtime_api.py:104,128` |
| knowledge.vekl | IMPLEMENTED_BUT_ISOLATED; no endpoint, no server, no caller | §1.15 |
| knowledge.obsidian | IMPLEMENTED_BUT_ISOLATED; unconfigured | §1.16 |
| knowledge.notebook (3 providers) | IMPLEMENTED_BUT_ISOLATED; disabled; mock-tested | §1.17 |
| knowledge.evidence/schema/models | INTEGRATED (schema at startup) | `runtime_api.py:128` |
| research.exa.ExaResearchService | IMPLEMENTED_BUT_ISOLATED; disabled | §1.19 |

Nothing in scope reaches E2E_VERIFIED. Nothing is SIMULATED or STUB in the sense of fake success: the code is
genuinely implemented; it is the *feeding* and *consumption* that are absent.

---

## 12. Recommendations (for the caller; not applied)

1. Either wire `orchestrator.py:403` to real requirements (derive from `req.project_id`/resolver output) or stop
   describing the forwarded snapshot as "canonical owner context"; today it is a policy/live-state receipt.
2. Provide a trusted writer for CANONICAL_OWNER/PROJECT_TRUTH facts (owner UI, project-truth sync) or default
   retrieval to `allow_inferred=True`; the current combination makes the fact store unreachable in production.
3. Bind `episode_ref`s to mission/command ids (`missions` FK) before counting independence, and make
   calibration reasons say "confirmed by evidence" vs "confirmed by owner" based on `owner_confirmed_at_ms`.
4. Add routes (or MCP tools) for `assess`, `assess_premise`, `record_assumption`, and a Hermes-side
   post-run hook that emits them — or remove the "consumed by Hermes" claim from the matrix.
5. Decide on one epistemic taxonomy (`EpistemicState` vs `SemanticClass`).
6. Add retention for `knowledge_evidence`, `research_evidence`, `eval_runs`, `context_snapshots`.
7. Validate evidence refs on `compile_snapshot` against `knowledge_evidence`/`owner_context_edges`.
8. Fix the three `__import__` hacks in `knowledge/notebook.py`.
