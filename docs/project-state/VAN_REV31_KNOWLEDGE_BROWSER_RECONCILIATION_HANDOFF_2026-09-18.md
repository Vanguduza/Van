# VAN Rev 3.1 Knowledge Runtime × Browser Integration Reconciliation Handoff

**Date:** 2026-09-18  
**Repository:** `Vanguduza/Van`  
**Branch:** `gpt/rev3-1-full-knowledge-runtime-20260917`  
**Certified parent:** `87f5a225b12a8c6b5a1dc1758cd6fc8dabb0fd00`  
**Knowledge implementation:** `5fc4972146f267e1942cd3955382dd2429f00460`  
**Acceptance alignment:** `714cbf7f7764e971c622502ea0a42a4b04212c2f`

## 1. Purpose

This document is the reconciliation authority for merging the Rev 3.1 full knowledge-runtime work with the separate browser-integration WIP.

Do not treat this branch as an alternate VAN architecture. It extends the certified Owner-Agent Runtime while preserving these locked boundaries:

- Hermes profile `van` remains the sole agent/planner runtime.
- The gateway owns context authority, action authorization, provider execution state and postcondition verification.
- VEKL, Obsidian and Notebook are evidence/cognition sources; none may self-promote into Owner Facts or Project Truth.
- Provider acceptance is not completion. Mutations are successful only after deterministic/readback verification.
- Browser capability must not create a second authority or bypass A1-A5 action policy.

## 2. Current tested state

The branch working tree was clean before this handoff was added.

Local backend regression command:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests -q
```

Result on `714cbf7f7764e971c622502ea0a42a4b04212c2f`:

```text
125 passed, 2 warnings in 38.26s
```

The warnings are existing Starlette/httpx deprecations from the trading API test surface, not knowledge-runtime failures.

No live provider is promoted to READY merely because repository tests pass. Live VEKL, Obsidian and Notebook readiness remains evidence-gated.

## 3. Implemented: common knowledge capability plane

A full `backend/van_gateway/knowledge/` runtime now provides typed provider states, evidence records, mutation states, bounded requests, durable evidence/certification storage, stable evidence pointers, content digests, explicit source trust and provider lifecycle aggregation.

Provider output has no path that self-promotes into canonical Owner Facts or Project Truth.

## 4. Implemented: VEKL and Obsidian

### VEKL

The VEKL adapter is read-only and bounded. It includes authenticated mission projection access, session/principal scoping, retry/backoff, deterministic flatten/ranking, provenance persistence, scope-denial handling and live canary certification.

VEKL results remain evidence. They do not become owner truth automatically and cannot directly mutate Project Truth.

### Obsidian

The Obsidian adapter includes incremental Markdown indexing and deletion tracking, safe-root/path and symlink controls, file-count and file-size bounds, frontmatter/tags/link extraction, FTS5 querying with deterministic lexical fallback, secret-like content exclusion, evidence persistence and live index/query certification.

The vault is owner-selected durable knowledge, not the runtime fact database.

## 5. Implemented: Notebook Enterprise

The Enterprise path uses the programmatic Google Cloud Notebook API surface and includes authenticated Cloud credential/token handling, notebook create/get/list lifecycle, source batch creation/readback, source-processing polling, source deletion/readback, mutation idempotency, durable operation state, explicit retry/failure/conflicted states and postcondition verification before VERIFIED_SUCCESS.

## 6. Implemented: personal NotebookLM

The consumer path uses a persistent authenticated Chromium owner profile without exporting cookies or session secrets.

Implemented functions include grounded notebook ask/read as evidence, note creation, UI/DOM readback after mutation, persistent mutation operation/idempotency records, explicit auth/configuration failure states, ambiguous pre-existing same-title note rejection, and retry correlation that cannot turn bare existence into success.

Operator tooling:
- `tools/google/bootstrap_notebook_consumer.py`
- `tools/google/certify_knowledge_runtime.py`

The current consumer transport is direct Playwright inside `backend/van_gateway/knowledge/notebook.py`. This is the primary reconciliation point with the browser WIP.

## 7. Implemented: action authority and execution

Notebook mutations are registered A3 actions. They are not generic model-write tools.

The gateway requires an already-authorized `ActionExecution` bound to the signed owner command, effective action class, requester/principal, immutable context snapshot and parameter digest.

Provider execution follows:

```text
AUTHORIZED -> provider submit -> SUBMITTED/VERIFYING -> VERIFIED_SUCCESS
```

Provider failures map to explicit action failure states. Ambiguous timeout after a mutation must never be silently converted to success or blindly replayed.

## 8. Implemented: Hermes and runtime integration

The owner-runtime internal API now exposes bounded knowledge status/read/query/certification surfaces and an authorized mutation execution bridge.

Hermes MCP exposes only the constrained allowlist. It does not expose generic HTTP, shell/browser credentials, canonical-memory admission or direct provider mutation bypassing `action_begin`.

Hermes operating instructions require knowledge evidence used in planning to be sealed into `knowledge_evidence_refs` before action planning.

## 9. Browser-integration reconciliation requirements

The browser WIP should absorb the personal NotebookLM transport rather than maintain two independent browser-control stacks.

Preferred end state:

```text
Hermes intent/planning
 -> gateway authorized action/evidence request
 -> Browser Harness deterministic session/control
 -> Stagehand semantic browser operation where needed
 -> provider-specific Notebook adapter
 -> DOM/readback evidence
 -> gateway ActionRuntime verification
```

The browser layer is transport/execution capability only. It must not decide action class, owner approval, Project Truth, context authority or completion status.

## 10. Files most likely to overlap with browser WIP

Reconcile these deliberately rather than choosing one branch wholesale:

- `backend/requirements.txt`
- `backend/van_gateway/config.py`
- `backend/van_gateway/runtime_api.py`
- `backend/van_gateway/knowledge/notebook.py`
- `backend/van_gateway/knowledge/service.py`
- `hermes/mcp/owner_runtime_stdio.mjs`
- `hermes/profile/van/AGENTS.md`
- `tools/google/bootstrap_notebook_consumer.py`
- `tools/google/certify_knowledge_runtime.py`
- owner-runtime MCP contract tests

If the browser WIP already defines the canonical Browser Harness/Stagehand abstraction, replace direct Playwright calls behind the Notebook consumer provider with that abstraction. Preserve the provider contract, idempotency and verification semantics.

Do not remove the persistent owner-profile rule unless the replacement gives equivalent session isolation and no-cookie-export guarantees.

## 11. Invariants that must survive reconciliation

1. Hermes remains the sole agent runtime.
2. Browser/Stagehand is never an authority source.
3. Consumer browser session secrets/cookies never enter model context.
4. Read-only evidence calls may be directly available to Hermes only through bounded tools.
5. Every Notebook mutation starts from a gateway-authorized action execution.
6. The execution parameter digest must match the provider request.
7. Same idempotency key with different parameters is a hard conflict.
8. Provider submission is not owner-visible success.
9. Readback/correlation is required for VERIFIED_SUCCESS.
10. Pre-existing same-title consumer notes cannot satisfy a new create command by existence alone.
11. Ambiguous mutation timeouts fail closed; never blind-replay duplicate-prone or destructive work.
12. VEKL/Obsidian/Notebook evidence remains non-canonical until a separate authority process admits it.
13. `knowledge_evidence_refs` remains part of the immutable planning snapshot/digest.
14. SECRET-class content must not enter personalization, knowledge indexing or context truth stores.
15. Existing A4 biometric proof, VATI sender authority and secure device pairing must not be weakened.

## 12. What remains after this branch

### Browser reconciliation

- Replace/adapt direct Playwright consumer Notebook control to the canonical Browser Harness + Stagehand architecture if that WIP is authoritative.
- Reconcile persistent browser-profile/session ownership, process lifecycle, retries, semantic locators and observability.
- Add browser-harness-specific Notebook tests/canaries after the transport swap.
- Ensure voice-triggered and text-triggered Notebook actions use the same gateway action path.

### Live provider certification

Still external/evidence-gated:

- VEKL: configure DDE/VEKL mission endpoint + bounded VAN principal/session credential and run a mission projection canary.
- Obsidian: mount/configure the owner-selected vault on the gateway host and run index/query certification.
- Personal NotebookLM: authenticate the persistent owner browser profile and run grounded ask + mutation/readback canaries.
- Notebook Enterprise: configure eligible owner-administered Google Cloud/Enterprise project and credential plane and run API lifecycle/readback canaries.

No provider should be labelled READY before those live receipts exist.

## 13. CI / merge work still required

This handoff records a locally green backend suite, but the reconciliation agent must still:

1. reconcile the browser WIP and this branch onto one current VAN lineage;
2. resolve shared-file conflicts semantically;
3. run backend unit tests, contract tests and Hermes policy tests;
4. run Android/build/lint/visual evidence gates even if the reconciliation appears backend-only;
5. run Browser Harness/Stagehand integration tests and Notebook canaries;
6. inspect generated evidence rather than relying only on exit codes;
7. update the implementation ledger/external gates after live evidence exists;
8. merge only after the reconciled branch is CI-green.

## 14. Suggested reconciliation sequence

1. Use this branch as the knowledge-runtime side and the browser-WIP branch as the browser-control side.
2. Preserve `knowledge/` models, evidence, schema and provider contracts first.
3. Preserve ActionRuntime/CommandAuthority changes and their tests.
4. Adopt the browser WIP's canonical Browser Harness/Stagehand service boundary.
5. Refactor only the consumer Notebook transport behind that boundary.
6. Keep Enterprise Notebook on its official API path; do not browser-automate it unnecessarily.
7. Re-run provider-specific tests and the full repository gates.
8. Perform live provider canaries where credentials/sessions are available.
9. Supersede this handoff with a reconciliation certification document after closure.

## 15. Branch delta

Relative to certified parent `87f5a225...`, this line adds roughly 3,100 lines across 32 files before this handoff.

Key commits:
- `5fc4972` — full Rev 3.1 knowledge runtime.
- `714cbf7` — acceptance/profile alignment for the hardened runtime.

This is intentionally a WIP reconciliation handoff, not a declaration that live browser/provider integration is complete.
