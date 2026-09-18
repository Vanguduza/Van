# VAN Rev 3.1 — Deterministic Owner-Context Retrieval Certification

Status: **MEASURED / CI-EVIDENCED**  
Scope: VAN Canonical Owner-Agent Runtime Rev 3.1 local context critical path  
Evidence run: `van-ci #192` (`35225247722`)  
Evidence commit: `4f3f5bbe3c7545fe9a568e5506510cafe71a2d95`  
Artifact: `van-context-latency-evidence`  
Artifact SHA-256: `19d303a26d4cc94fe01426f2490309b79514a224db1f3f1f250698120774c1ab`

## 1. Certified architecture

VAN's normal owner-command context path remains deterministic and local:

1. exact canonical requirement lookup;
2. bounded temporal graph traversal where relationships are required;
3. deterministic lexical/entity retrieval when exact/graph evidence is insufficient;
4. revision-sealed hot-context capsules for repeated active-workstream evidence;
5. immutable context snapshot sealing before consequential planning/execution;
6. semantic/vector/model retrieval only as an escalation for recall gaps or deep knowledge work;
7. external research only when local knowledge is insufficient or current-world evidence is required.

Graph, lexical results and hot capsules are retrieval evidence, not truth authority. Canonical authority remains with the Owner Context Kernel and its provenance/temporal rules.

## 2. Measurement environment

The CI benchmark deliberately measures only the local deterministic path:

- SQLite temporary local database;
- 321 facts;
- 160 temporal graph edges;
- owner-context kernel revision 481 after corpus admission;
- 50 steady-state samples per normal retrieval operation;
- 10 cold hot-capsule compiles;
- no model calls;
- no remote calls;
- no semantic embeddings.

The benchmark source is `backend/tools/benchmark_context_retrieval.py`. CI writes `artifacts/release/context/context-latency.json` and uploads it as `van-context-latency-evidence`.

## 3. Measured latency

| Operation | p50 | p95 | p99 | Max |
|---|---:|---:|---:|---:|
| Exact readiness | 0.919 ms | 0.982 ms | 1.021 ms | 1.021 ms |
| Deterministic lexical query | 12.328 ms | 12.922 ms | 13.401 ms | 13.401 ms |
| Temporal graph query | 23.820 ms | 24.552 ms | 25.143 ms | 25.143 ms |
| Hot capsule, cold compile | 39.861 ms | 40.272 ms | 40.272 ms | 40.272 ms |
| Hot capsule, cache hit | 0.864 ms | 1.130 ms | 1.350 ms | 1.350 ms |

These numbers describe the CI runner and the controlled benchmark corpus; they are evidence for the implementation, not a guarantee for every Android/device/workload environment. Device p50/p95/p99 must still be measured separately before a device-specific SLO is claimed.

## 4. Decision

The measured local path is already comfortably below the Rev 3.1 design envelope for context readiness. Therefore:

- **Do not add vector or LLM retrieval to the ordinary critical path.**
- Preserve exact → graph → lexical → hot-capsule ordering.
- Add semantic retrieval only when a concrete recall-quality test demonstrates a local deterministic miss that matters to the owner task.
- Semantic retrieval must return evidence candidates through the same authority/temporal filters and must never bypass snapshot sealing.
- Hot capsules remain caches of revision-bound evidence references, never a second memory authority.

## 5. Snapshot lineage

`ContextSnapshot` now seals graph and lexical evidence separately in its digest. The public model exposes:

- `graph_evidence_refs`;
- `lexical_evidence_refs`;
- `live_state_refs`;
- `policy_refs`.

The existing physical `graph_evidence_refs_json` storage column is retained for schema compatibility and stores a typed envelope with separate `graph` and `lexical` arrays. This preserves evidence class identity without another database migration.

## 6. Remaining certification

Before final Rev 3.1 production closure:

- measure the same retrieval path on the target Android/device/runtime environment;
- certify any knowledge-source adapters (Obsidian/NotebookLM/VEKL) independently;
- keep semantic retrieval escalation-only unless recall evidence proves otherwise;
- preserve Hermes as sole planner/reasoner and the gateway as context/authority/action verifier.
