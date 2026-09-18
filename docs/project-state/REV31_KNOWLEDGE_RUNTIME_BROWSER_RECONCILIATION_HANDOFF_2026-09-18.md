# VAN Rev 3.1 Knowledge Runtime ↔ Browser Integration Reconciliation Handoff

**Date:** 2026-09-18  
**Repository:** `Vanguduza/Van`  
**Branch:** `gpt/rev3-1-full-knowledge-runtime-20260917`  
**Certified parent/base:** `87f5a225b12a8c6b5a1dc1758cd6fc8dabb0fd00`  
**Knowledge-runtime implementation commit:** `5fc4972`  
**Acceptance-alignment commit:** `714cbf7`  
**Purpose:** freeze and publish the complete Rev 3.1 knowledge-runtime work so it can be reconciled with the parallel Browser Harness / Stagehand integration work. The browser-integration agent owns the final reconciliation and remaining closure after this handoff.

---

## 1. Handoff state

This branch is **not a conceptual scaffold**. It contains the full repository-side implementation completed in this workstream for VEKL, Obsidian and Notebook knowledge integration, including authority boundaries, persistence, evidence lineage, action execution, tests, tooling and external-gate documentation.

The branch is deliberately being handed off **before live external-provider certification and before reconciliation with the parallel browser work**. Do not discard the implemented semantics just because the browser work has a different transport or browser lifecycle.

At handoff:

- Working tree before this document was clean.
- Backend regression suite: **125 passed**, 2 deprecation warnings.
- Contract + Hermes + acceptance scenario subset: **37 passed**.
- No Android source files were changed in this knowledge-runtime delta.
- Full GitHub Actions on this new branch must run after push.
- External live-provider gates remain separate and are listed below.

---

## 2. What was implemented

### 2.1 Unified knowledge capability plane

A new `backend/van_gateway/knowledge/` package implements one deterministic capability plane beneath Hermes:

- `models.py` — typed provider, evidence, operation and request/response contracts.
- `schema.py` — durable knowledge provider/evidence/index/operation storage.
- `evidence.py` — content digests, provenance, evidence pointers and provider certification.
- `vekl.py` — bounded read-only DDE/VEKL mission evidence adapter.
- `obsidian.py` — bounded owner-vault index/query provider.
- `notebook.py` — Notebook Enterprise official API transport + personal NotebookLM browser transport.
- `service.py` — `KnowledgeRuntime` lifecycle, status, query and mutation orchestration.

**Invariant:** these providers produce evidence or verified mutation receipts. They do not write Project Truth or canonical Owner Facts.

### 2.2 VEKL

Implemented:

- read-only mission projection/query;
- bounded results and query length;
- authenticated session/principal/bearer configuration;
- deterministic flatten/ranking;
- retry/backoff and fail-closed provider errors;
- scope-denial handling;
- persisted evidence with provenance/digests;
- provider certification canary;
- no owner-truth admission route.

VEKL remains engineering/domain evidence. It does not become VAN hot memory or canonical truth.

### 2.3 Obsidian

Implemented:

- owner-selected vault path;
- bounded incremental Markdown indexing;
- changed/unchanged/deleted document tracking;
- maximum file and vault-count guards;
- symlink/path traversal protection;
- secret-like content exclusion;
- frontmatter, tag and link extraction;
- SQLite FTS5 where available;
- deterministic lexical fallback where FTS is unavailable;
- read-only query surface;
- persisted evidence and provider certification.

Obsidian is an owner-readable durable knowledge source. Runtime truth remains in the Owner Context Kernel.

### 2.4 Gemini Notebook / NotebookLM

The implementation intentionally keeps two credential/transport planes separate.

#### Notebook Enterprise

Uses the Google Cloud/service credential plane and the official Discovery Engine `v1alpha` notebook/source lifecycle.

Implemented:

- Cloud access-token provider;
- service-account JWT exchange or short-lived access-token file;
- notebook create;
- notebook readback;
- recent notebook listing;
- source batch add;
- source processing-state polling;
- source readback;
- notebook deletion;
- source deletion;
- durable idempotency/operation ledger;
- retry state;
- conflict state for ambiguous post-submit outcomes;
- readback verification before `VERIFIED_SUCCESS`;
- persisted evidence/provenance.

**Do not replace Enterprise API operations with browser automation.** The official API remains canonical when configured.

#### Personal consumer NotebookLM

Uses the owner consumer-session plane.

Implemented:

- persistent Chromium profile;
- no cookie export;
- authenticated-session detection;
- grounded Notebook ask/read capability;
- note creation;
- exact-title/body submission;
- UI readback verification;
- pre-existing same-title ambiguity protection;
- idempotent retry state;
- evidence/provenance;
- provider certification path.

This direct Playwright lifecycle is the **main intended reconciliation point** with the Browser Harness / Stagehand work. See §6.

### 2.5 Action/runtime authority

Notebook writes do not bypass the Rev 3.1 action runtime.

Canonical registered mutation actions now include:

- `google.notebook.note.create`
- `google.notebook.enterprise.create`
- `google.notebook.enterprise.sources.add`
- `google.notebook.enterprise.delete`
- `google.notebook.enterprise.sources.delete`

All are registered with typed parameters, action class and readback verification.

The knowledge mutation route is:

`signed owner command → typed resolver → sealed command authority → action_begin → AUTHORIZED ActionExecution → knowledge_action_execute → provider submit/readback → ActionRuntime verification/receipt`

`knowledge_action_execute` requires an already-authorized execution ID and exact parameter digest. Provider code cannot mint authority.

The action runtime also gained deterministic failure transitions for precondition, execution, verification, retryable, conflict and partial outcomes.

### 2.6 False-completion hardening

Implemented corrections include:

- Enterprise source ingestion cannot be marked verified while still processing.
- Source processing failures remain verification failures.
- Post-submit uncertain source operations do not silently retry destructive/mutating work.
- Enterprise notebook creation records pre-existing notebook IDs before submission; timeout recovery cannot accept an unrelated same-title notebook.
- Personal NotebookLM note creation cannot treat a pre-existing same-title note as VAN-created.
- Notebook operation correlation survives retry transitions.
- Mutation success requires provider readback/postcondition evidence.
- Unsupported/unverifiable states do not become `VERIFIED_SUCCESS`.

### 2.7 Context lineage

`ContextSnapshot` now carries separate:

- fact IDs;
- graph evidence refs;
- lexical evidence refs;
- **knowledge evidence refs**;
- live-state refs;
- policy refs.

Knowledge evidence is therefore sealed into the same immutable planning context as other evidence. It is not left as an untracked model input.

### 2.8 Hermes owner-runtime MCP

The existing narrow stdio MCP bridge now exposes read-only knowledge tools plus one constrained mutation executor.

Read-only tools include:

- `knowledge_status`
- VEKL query
- Obsidian query
- Notebook Enterprise recent/get
- personal Notebook grounded ask

Mutation:

- `knowledge_action_execute` — only executes an already-authorized action execution.

The MCP still exposes:

- no shell;
- no generic HTTP;
- no credential export;
- no canonical-memory admission tool;
- no Project Truth write tool.

### 2.9 Hermes operating protocol

`hermes/profile/van/AGENTS.md` now requires:

1. deterministic command resolution;
2. exact context readiness;
3. bounded graph retrieval where relevant;
4. deterministic lexical retrieval;
5. revision-sealed hot capsule for repeated active context;
6. VEKL / Obsidian / Notebook evidence only when local deterministic context is insufficient or the task explicitly requires those sources;
7. immutable context snapshot including `knowledge_evidence_refs`;
8. `action_begin` before mutations;
9. provider submission/readback;
10. success only after verified completion.

---

## 3. Repository files changed by the implementation

The main implementation commit `5fc4972` changed 30 files, adding ~3,126 lines.

High-value shared files:

- `backend/requirements.txt`
- `backend/van_gateway/action/registry.py`
- `backend/van_gateway/action/service.py`
- `backend/van_gateway/command/authority.py`
- `backend/van_gateway/command/resolver.py`
- `backend/van_gateway/config.py`
- `backend/van_gateway/context/models.py`
- `backend/van_gateway/context/service.py`
- `backend/van_gateway/orchestrator.py`
- `backend/van_gateway/runtime_api.py`
- `hermes/mcp/owner_runtime_stdio.mjs`
- `hermes/profile/van/AGENTS.md`
- `docs/EXTERNAL_GATES.md`
- `docs/IMPLEMENTATION_LEDGER.md`

New knowledge package:

- `backend/van_gateway/knowledge/__init__.py`
- `backend/van_gateway/knowledge/evidence.py`
- `backend/van_gateway/knowledge/models.py`
- `backend/van_gateway/knowledge/notebook.py`
- `backend/van_gateway/knowledge/obsidian.py`
- `backend/van_gateway/knowledge/schema.py`
- `backend/van_gateway/knowledge/service.py`

Tests/tooling:

- `backend/tests/test_knowledge_runtime.py`
- `backend/tests/test_command_authority_constraints.py`
- `backend/tests/test_context_snapshot_lineage.py`
- `backend/tests/test_rev31_runtime_wiring.py`
- `backend/tests/test_typed_command_resolver.py`
- `tests/contracts/test_owner_runtime_mcp_contract.py`
- `tools/google/bootstrap_notebook_consumer.py`
- `tools/google/certify_knowledge_runtime.py`

Acceptance alignment commit `714cbf7` additionally changes:

- `tests/hermes/test_profile_layout.py`
- `tests/scenarios/test_acceptance_scenarios.py`

---

## 4. Test status at handoff

### Green locally

`PYTHONPATH=backend pytest -q backend/tests`

Result:

- **125 passed**
- 2 Starlette/httpx deprecation warnings

`PYTHONPATH=backend pytest -q tests/contracts tests/hermes tests/scenarios`

Result:

- **37 passed**

### Still required after branch push/reconciliation

- full GitHub Actions on the published handoff commit;
- Android build/lint/visual regression CI even though this delta has no Android source changes;
- Browser Harness / Stagehand integration tests after reconciliation;
- target-host live provider certification.

Do not convert local green tests into a claim that external providers are live-ready.

---

## 5. External/live gates still open

From `docs/EXTERNAL_GATES.md`:

### Personal Gemini Notebook

Repository side is implemented.

Still needs:

- owner Google session on Hermes/browser host;
- persistent profile bootstrap;
- live authenticated ask canary;
- live note-create + UI-readback canary;
- certification evidence.

State must remain `CONFIGURED` until canary evidence exists.

### Notebook Enterprise

Repository side is implemented.

Still needs:

- eligible Google Cloud/Enterprise setup;
- project number/location;
- service-account or short-lived token source;
- live notebook lifecycle canary;
- live source-ingest/readback canary;
- certification evidence.

### VEKL

Repository side is implemented.

Still needs:

- reachable DDE/VEKL mission endpoint;
- bounded VAN principal/session credentials;
- live mission projection query;
- certification evidence.

### Obsidian

Repository side is implemented.

Still needs:

- selected vault mounted on the gateway host;
- live index;
- live query;
- certification evidence.

---

## 6. Required reconciliation with Browser Harness / Stagehand WIP

This is the primary purpose of this handoff.

### 6.1 Preserve browser authority boundaries

The browser subsystem must remain an **executor/tool**, not an independent VAN agent loop.

Hermes remains the sole planner/reasoner. Gateway context/authority/action verification remains authoritative.

Do not let Stagehand, Browser Harness or browser-side model reasoning:

- mint owner authority;
- choose a lower action class;
- bypass `action_begin`;
- bypass command/snapshot binding;
- directly mark a mutation successful;
- write Project Truth or canonical Owner Facts;
- export Google cookies/session material into model context.

### 6.2 Reconcile personal NotebookLM onto the shared browser stack

`backend/van_gateway/knowledge/notebook.py` currently owns a direct Playwright persistent-context lifecycle for the consumer NotebookLM path.

If the parallel browser work has established the canonical Browser Harness + Stagehand stack, **replace the transport/lifecycle layer, not the Notebook semantics**.

Preserve:

- owner-owned persistent authenticated profile;
- no cookie/session export;
- notebook-specific deterministic navigation contract;
- explicit auth detection;
- bounded operation timeout;
- idempotency key;
- pre-existing-object ambiguity check;
- one mutation attempt per operation lineage;
- post-submit UI readback;
- failure if selectors/semantic controls drift;
- evidence pointer and observed postcondition;
- `VERIFIED_SUCCESS` only after readback.

Recommended target:

`NotebookConsumerProvider → BrowserHarness/Stagehand adapter → NotebookLM UI → readback verifier`

not:

`Hermes → free-form browser agent → “looks successful”`.

### 6.3 Stagehand role

Stagehand may improve semantic resilience for NotebookLM controls and grounded-question interactions, but must be bounded by an operation descriptor.

A useful descriptor should include:

- capability/action ID;
- target host;
- authenticated profile ID/reference;
- allowed navigation origin(s);
- expected controls/semantic goals;
- mutation budget;
- timeout;
- expected postconditions;
- readback requirements;
- forbidden credential/session extraction;
- idempotency/execution ID.

Browser execution output should be treated as provider evidence and fed back into the ActionRuntime verifier.

### 6.4 Browser Harness role

The deterministic harness should own:

- browser process/context lifecycle;
- profile locking;
- navigation policy;
- download/upload policy;
- origin allowlist;
- timeouts;
- screenshots/DOM evidence where appropriate;
- crash/restart recovery;
- correlation IDs;
- audit/evidence emission.

The Notebook provider should own:

- Notebook-specific operation semantics;
- idempotency;
- pre/postconditions;
- interpretation of Notebook readback;
- provider-specific failure codes.

### 6.5 Do not browser-wrap official API paths

Do **not** move these to Stagehand when Enterprise API is available:

- Enterprise notebook create/get/list;
- Enterprise source add/get/delete;
- Enterprise notebook delete.

Browser automation is for account-native consumer surfaces without equivalent supported API access.

### 6.6 Shared files likely to conflict

Reconcile carefully instead of choosing one branch wholesale:

- `backend/requirements.txt`
- `backend/van_gateway/action/registry.py`
- `backend/van_gateway/action/service.py`
- `backend/van_gateway/command/authority.py`
- `backend/van_gateway/command/resolver.py`
- `backend/van_gateway/config.py`
- `backend/van_gateway/orchestrator.py`
- `backend/van_gateway/runtime_api.py`
- `hermes/mcp/owner_runtime_stdio.mjs`
- `hermes/profile/van/AGENTS.md`
- `docs/EXTERNAL_GATES.md`
- `docs/IMPLEMENTATION_LEDGER.md`

Prefer semantic reconciliation over “ours/theirs”.

The new `backend/van_gateway/knowledge/` package should generally be preserved and adapted at its browser transport seam.

---

## 7. Non-negotiable invariants after reconciliation

1. Hermes profile `van` remains the sole agent runtime.
2. Models may reason/propose; they do not hold owner truth or action authority.
3. Browser automation does not become a second authorization plane.
4. VEKL, Obsidian and Notebook outputs remain evidence until explicitly admitted by a higher-authority process.
5. Secret-class content is excluded from owner-memory/personalization stores.
6. Notebook mutations are A3 unless canonical policy changes them through the normal authority process.
7. A mutation cannot reach `VERIFIED_SUCCESS` from provider submission alone.
8. Exact ActionExecution parameter digest must match the provider execution request.
9. Idempotency/retry logic must not duplicate ambiguous mutations.
10. Browser/session credentials never enter prompts or provider evidence payloads.
11. Personal consumer cookies/session material are never exported from the browser profile.
12. Knowledge evidence used in planning is sealed in `knowledge_evidence_refs`.
13. Project Truth outranks provider/research/Notebook content.
14. VATI/trading authority remains separate and must not be altered by this reconciliation.
15. The measured deterministic local context path remains the normal fast path; Notebook/VEKL/Obsidian are escalation/domain sources, not mandatory per-command dependencies.

---

## 8. Work intentionally left to the reconciliation/finishing agent

The next agent should finish the following after merging this branch with the browser WIP:

1. Reconcile consumer NotebookLM browser transport with canonical Browser Harness / Stagehand.
2. Remove duplicate raw Playwright lifecycle code if the shared harness fully replaces it.
3. Keep Notebook provider-specific postcondition/idempotency logic intact.
4. Add Browser Harness/Stagehand integration tests for NotebookLM:
   - auth missing;
   - selector drift;
   - pre-existing same-title note;
   - successful create + readback;
   - navigation timeout;
   - browser crash/restart;
   - duplicated execution/idempotency replay;
   - forbidden origin/navigation;
   - credential/session exfiltration attempt.
5. Run all backend/contracts/Hermes/scenario tests after reconciliation.
6. Run full GitHub CI including Android/visual regression.
7. Run live provider certification only where credentials/environment are available.
8. Update `IMPLEMENTATION_LEDGER.md` and `EXTERNAL_GATES.md` with actual live evidence, never assumptions.
9. Decide whether personal NotebookLM browser can be declared `READY`; leave `CONFIGURED` otherwise.
10. Preserve the branch's evidence lineage and action-authority behavior during any refactor.

---

## 9. Fast reconciliation checklist

Before merging browser WIP into this branch, answer:

- Does browser WIP introduce another planner/agent loop? If yes, remove that authority.
- Does it have its own action classification? If yes, map it to gateway A1–A5 rather than parallel policy.
- Does it submit mutations outside `ActionRuntime`? If yes, route through `action_begin` + execute + verify.
- Does it manage persistent profiles? Reuse for consumer NotebookLM, preserving no-cookie-export.
- Does it expose arbitrary browser HTTP/navigation to Hermes? Constrain to typed capability tools.
- Does it already provide correlation/evidence capture? Reuse and map into Notebook operation evidence.
- Does it include Stagehand semantic actions? Use them behind the Notebook operation descriptor, not as completion authority.
- Does it alter `runtime_api.py`, MCP or AGENTS? Reconcile semantics line-by-line.

---

## 10. Final handoff statement

This branch should be treated as the **knowledge-runtime implementation authority to be reconciled**, not as a throwaway experiment.

The browser-integration work should supply the shared browser execution substrate. This branch supplies the knowledge semantics, authority model, provenance, context lineage, idempotency and verification rules.

The correct combined architecture is:

`Hermes planner → deterministic gateway context/authority → typed action → Browser Harness/Stagehand or official API executor → provider readback → ActionRuntime verifier → evidence + immutable context lineage`

Do not replace that with:

`Hermes/model → free-form browser → optimistic success`.