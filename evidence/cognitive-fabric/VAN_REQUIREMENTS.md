# VAN Cognitive Fabric REV 1.6.1 candidate evidence

Baseline: Vanguduza/Van main `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af`.
Owner clarified that construction of the development system is directly authorized in Codex, without routing this implementation through Hermes. Candidate code does not mutate Project Truth, adopt decisions, deploy, or grant provider execution authority.

## Source provenance

The current main already contains the authoritative VAN OwnerContextService, deterministic Attention Engine, Mission Core, capability registry, VATI CapsuleRegistry/OpportunityEngine/InstrumentEvaluator/CandidatePool/coordinator/IntentFactory/RiskAuthority/ExecutionRouter and reduce-only ShadowCognitionRuntime. They are reused, not replaced. Compared the available meta-muse live-green, JEV/openmuse and memory-fabric branches: meta live-green adds evidence documents; the JEV branch is principally a broad browser convergence line; the memory branch has its own scope. No wholesale branch merge was performed. All new code in this candidate is Codex-authored; no recovered VAN Muse source was available. The seven recovered review files are DDS files, not the complete VAN lane.

## Requirements and executable wiring

| Requirement | Authoritative caller and evidence | Candidate state |
|---|---|---|
| DOT-WP-08 owner learning | CognitiveService -> existing OwnerContextService.admit_fact(INFERRED, MODEL_DERIVED); actual canonical owner correction supersedes inferred candidate | Implemented; 13 gateway/service tests including actual create_app ASGI middleware |
| Attention learning | Strict existing importance/urgency/actionability/novelty/owner_relevance/confidence/interruption_cost dimensions, existing SUPPRESS..URGENT_INTERRUPT vocabulary preserved; calibration is a candidate and does not alter thresholds | Candidate ingress implemented; normal policy adoption required before changing thresholds |
| Mission discovery | MISSION_CANDIDATE ingress; no mission is fabricated; existing Mission Core is sole acceptance/authority path | Implemented candidate queue; actual owner acceptance uses existing mission/command route |
| MUSE-WP-01/02/13 free-only provider family | Versioned registry; paid Spark/Code/Image/Voice disabled; Glimmer blocked; consumer Muse/Dot T3 only | Implemented, no paid fallback or transport invented |
| MUSE-WP-03 Guardian | Sanitized read projection from actual project truth cache, mission state, attention counts and trading ledger health; scoped explicit candidate import | Implemented candidate flow; no supported Personal Muse callback or live observation is claimed |
| MUSE-WP-06 tri-analyst | TriAnalystPlane -> hash-chained VATI ledger; actual configured discovery universe and exact market epoch published by AccountCoordinatorService | Implemented for account coordinator service; consumer T3 is not a live dependency |
| MUSE-WP-07 TCE/JEV | Candidate/epoch/hash/freshness/lineage/lane/model qualification validation; first-pass context excludes peer packets and discovery narrative; deterministic bounded JEV classification; dissent retained | Implemented; no inferred confidence averaging |
| MUSE-WP-08 VATI bridge | AccountCoordinatorService polls sealed admission, validates exact original bar hash, calls actual InstrumentEvaluator/capsule engine, inserts only deterministic results into existing CandidatePool; existing allocator/IntentFactory/RiskAuthority/ExecutionRouter handle remaining path | Implemented; no compatible strategy => WATCH_RESEARCH, no candidate; protection/lifecycle precedes ordinary allocation |
| MUSE-WP-09 trading learning | Candidate->intent binding at existing coordinator; TradeLearningEpisode/Outcome joins actual allocation/risk/receipt/TCA/review events; expired discovery produces NO_TRADE; ex-ante validity remains frozen | Implemented evidence learning; no analyst risk multiplier or DDS routing weight |
| MUSE-WP-11 surfaces | Existing GET /v1/trading/cognition now includes real ledger cognitive records; Android existing cognition screen displays counts, qualification and paid-state; owner gateway serves candidate/projection surfaces | Implemented source; Android build evidence separately gated |
| Cross-repo MCP integration | /v1/runtime/cognitive/projection and /candidates; actual context revision; dedicated explicit cognitive credential cannot access other runtime authority | Implemented and tested through actual app middleware; deployment provisioning remains pending |
| DOT-WP-16 Business Pulse | No qualified Business KPI projection currently supplied to VAN; Guardian reports this explicitly as unavailable | Not falsely claimed live; DDS/Business integration supplies owning projection |
| MUSE-WP-12 Glimmer | Actual local artifact hashing/hardware probe, loopback bounded benchmark, immutable measured receipts, license/Placement Governor/host/sandbox/data-class/RAM/latency gates; executable qualify_glimmer.py | Implemented qualification machinery; real model/estate activation external, no weights download or paid API fallback |

## Principal and data-class boundary

Provision a separate server credential with `VAN_INTERNAL_CONTROL_SCOPED_TOKENS=cognitive:<32+ character secret>` through the normal credential system. `cognitive` is excluded from the legacy token's default scopes. This principal can only read bounded projections and submit advisory candidates. It cannot invoke commands, broker operations, owner context canonical facts, actions, Mission Core state changes or owner approvals.

Candidate input accepts canonical PUBLIC / INTERNAL_SANITIZED. Legacy INTERNAL_SAFE_FOR_APPROVED_PROVIDER normalizes to INTERNAL_SANITIZED while retaining provider_approval_required=true. RESTRICTED and SECRET_HIGH_SENSITIVITY are denied on this cloud/explicit-import surface. Machine projections omit raw owner-pattern text and return candidate identity/status/hash summaries. Provider text is untrusted content, MODEL_DERIVED and ADVISORY_CANDIDATE. Nothing auto-promotes inferred memory to owner truth.

## Qualification and implementation limits

T2 provider calls are not claimed live: qualification is operator-owned and defaults empty. A qualifying provider/model must have explicit qualification_ref and expiry; local Meta additionally needs pinned artifact, placement, sandbox and capacity references. No external result can set qualification. Personal Muse transport remains explicit/manual owner import until MUSE-EXT-001 is independently qualified. Free quota behavior (MUSE-EXT-002), Glimmer hardware/artifact (MUSE-EXT-004), Meta privacy (MUSE-EXT-007), actual live broker/provider soak, installed APK/device checks and production deployment remain pending.

The existing single-instrument SessionRunner has no tri-analyst polling API; this candidate wires the account coordinator runtime. It is not a claim of certification for every legacy deployment. Guardian deployment/CI/business KPI source adapters are reported unavailable rather than synthesized. Full recovery of the reported VAN Muse source remains a separate unresolved input gate.

## Semantic machine reads and transport provenance

Separate `/v1/runtime/cognitive/{missions,attention,owner-context,capability-utilization,trading-market,strategy-health,performance,tca,learning-episodes}` slices query their owning Store/ledger sources, carry bounded canonical envelopes and actual source hashes, omit raw private goals/owner context and numeric money/size fields, and explicitly report missing ledger data as DEGRADED. Machine candidate ingress records trusted `DOT_COGNITIVE_MACHINE` route metadata; owner import records `EXPLICIT_OWNER_IMPORT`. Payloads cannot choose these provenance fields.

A broader trading-suite check exposed an existing file-mode preservation bug in `reconcile_vati_ledger.py`: os.open respected umask and changed an existing mode 0640 to 0600. The candidate now applies the original mode to the already-open temporary descriptor before atomic replacement; the existing regression passes without weakening its assertion.

## Common Cognitive Twin consumer

The owner-device `/v1/cognitive/twin?project_id=van` endpoint calls only DDS `/mcp` tool `cognitive_twin_projection_get` with a server-held dedicated VAN_PROJECTION credential. Configuration is default disabled (`VAN_COGNITIVE_TWIN_ENABLED`, `VAN_COGNITIVE_TWIN_BASE_URL`, `VAN_COGNITIVE_TWIN_TOKEN_FILE`, `VAN_COGNITIVE_TWIN_PROJECTS`). DDS must separately enable that principal/project in its governed consumers file. Android Work > Cognitive Twin consumes the same compiler projection unchanged through the gateway; machine facts, derived state, attention, observations, hypotheses and owner annotations remain separate, with original revision/hash/evidence and local expiration display. This read route cannot submit owner intentions or snapshots.

`backend/tests/test_cognitive_twin.py` cross-checks against the actual current DDS compiler and exact MCP JSON-RPC request over httpx test transport. It proves schema/wire preservation and fail-closed behavior, not a live credential qualification. `twin-python-tests.log` records 18 passing tests. Android JVM harness tests the actual parser; Compose/APK/device validation remains an external check. A real provisioned DDS VAN_PROJECTION credential and DDS consumer enablement are still required; no live service activation is claimed.

Final common-Twin Android verification: `android-twin-verification-final.log` records successful standalone Gradle JVM harness execution, including both new parser tests and the existing route-parent invariant. The first harness failure and correction (registering Cognitive Twin's parent as Work) are retained in `android-twin-verification.log`; no assertion was weakened.

## Candidate CI wiring and baseline correction

`.github/workflows/cognitive-fabric-r161-van.yml` triggers every push and pull request plus manual dispatch, including workflow-only changes. Python uses the existing supported Python 3.12 and `backend/requirements.lock`; required test files are checked, focused authority/transport tests and broad trading/context checks execute. The Android job pins Java 17 and Gradle 8.11.1, runs the real-source JVM harness, then executes actual Android unit tests, APK assembly and lint as blocking checks. Reports upload even on a package-gate failure; no missing tests are treated as a success. This is workflow implementation, not a claim that hosted GitHub CI has run or an APK has passed locally.

The portable MCP contract fixture in `backend/tests/fixtures/` was generated by the actual current DDS compiler. Its accompanying provenance records exact compiler and fixture SHA256; local sibling DDS checkouts recompute the actual compiler output. Without that checkout the committed compiler output exercises the complete VAN transport/parser contract rather than skipping tests. This does not qualify a live DDS service.

The two-line `deploy/van-trading-core/supabase/reconcile_vati_ledger.py` correction preserves the existing environment file permission bits during atomic rewrite. `os.open(...,mode)` applied the process umask to the temporary file, so an existing 0640 file became 0600 under the local stricter umask. `os.fchmod(fd, existing_mode)` restores the pre-existing mode before replacement. The existing `test_update_core_env_preserves_mode_and_encodes_password` failed before and passes afterward; no password or authorization semantics changed. This is a baseline bug exposed by the broad required regression run, not Cognitive Fabric activation.

Final exact-tree Python rerun after CI/portable-fixture changes: `python-tests-final-with-ci.log` records **1348 passed, 5 skipped, 2 warnings in 43.79s**. Command: `PYTHONPATH=backend:trading .venv/bin/python -m pytest -q trading/tests backend/tests/test_cognitive_fabric.py backend/tests/test_cognitive_twin.py backend/tests/test_context_admission_api.py backend/tests/test_context_lifecycle_governance.py`. Android source was unchanged by this CI-only final step; prior final JVM evidence remains 988 passing tests. Hosted CI remains unexecuted.
