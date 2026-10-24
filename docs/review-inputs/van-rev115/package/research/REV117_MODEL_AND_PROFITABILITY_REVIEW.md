# Rev1.17 — Jev, model qualification and profitability research

Scope: owner-directed specification hardening and bounded source probes, 2026-10-18. No model API inference, funded study, application e2e, production change or economic experiment was run. Current review branch app source remains unchanged. Native Jev/provider access and qualification are not attested by documentation retrieval.

## Recommendation

Keep the deterministic quantitative/risk/execution baseline, reuse the existing shared Jev service as a typed evidence critic, and compare Gemini 4 Argon with DeepSeek V4 Pro as research challengers. Add DeepSeek Flash only as an explicitly tested extraction/triage cost optimisation. Do not choose a production winner from brand reputation or finance/agent benchmarks. Existing required forecast integrations and provider capabilities remain preserved.

The near-term economic priorities are: accurate accounting and lower execution drag; better selection/abstention under real costs; independently validated strategy discovery; then model/routing complexity that demonstrates incremental benefit. Each step can legitimately find no supported edge. VAN-JM-001…008 and the 24 acceptance contracts make failure isolation, identity, privacy, independence, cost and economic qualification mandatory.

## Verified model identities and suitability

| Candidate | Primary-source observation | Useful experiment | What is unproven |
|---|---|---|---|
| Google Gemini 4 Argon (`gemini-4-argon`) | Google lists it as a stable general reasoning model with multimodal inputs, structured outputs and a large unified context window. | Complex evidence synthesis, hypothesis/refutation generation and review of long documents or proposed code in isolated research. | VAN-specific trading edge, independent review quality, immutable served weights and actual account access. |
| DeepSeek `deepseek-v4-pro` | Current docs identify the served version as DeepSeek-V4-Pro-0813. | Alternative reasoning challenger under the same evidence and consumer rules. | Superior finance accuracy, realized inference latency and net economic benefit. |
| DeepSeek `deepseek-flash` | Current docs identify DeepSeek-V4.1-Flash-1017; legacy Flash names are redirected to the newer served version. | Bounded extraction/triage and optional cost-saving escalation. | Whether reduced cost preserves the required task quality; aliases cannot inherit qualification silently. |
| Required Qlib/LightGBM and NeuralForecast baselines | Already in the retained blueprint. | Numerical forecasting, calibration and risk-matched economic controls. | No algorithm is presumed profitable before scoped evaluation. |
| Google TimesFM / FinGPT research options | TimesFM is forecasting software; FinGPT focuses on financial-language/data tasks. Both are distinct from Argon. | Optional numerical or extraction controls after task and license admission. | Neither generic forecast accuracy nor financial sentiment performance proves a tradable edge. |

Google’s identity is directly verified: the owner's “Argon 4” means Gemini 4 Argon, not Grok. Search-engine retrieval yielded redirects/scaffolding, so the identification relies on the official catalogue and model page. TimesFM 3.0 downloaded weights and source code have different licenses; authorized hosted production use and downloaded-weight use are distinct routes. No production use is selected by this review.

## Model cost illustration, not a measured inference result

Arithmetic assumes 20,000 uncached input tokens and 4,000 **total billed output tokens including reasoning**, one request, USD, no tool/search charges, no retry, no tax or negotiated account terms. These published rates were retrieved on 2026-10-18 and must be refreshed/bound before a study.

| Candidate | Published input/output per million tokens used | Illustrative call cost |
|---|---|---:|
| Argon standard, through 2026-11-30 | $2 / $10 | $0.08000 |
| Argon standard, published rate from 2026-12-01 | $4 / $20 | $0.16000 |
| DeepSeek Pro, peak | $1.32 / $3.96 | $0.04224 |
| DeepSeek Pro, off-peak | $0.66 / $1.98 | $0.02112 |
| DeepSeek Flash, peak | $0.30 / $1.20 | $0.01080 |
| DeepSeek Flash, off-peak | $0.15 / $0.60 | $0.00540 |

These are token-cost examples, not total research costs or evidence of model quality. Include caching policy, thinking/output limits, tool requests, failed attempts, retries, infrastructure, data licensing and maintenance in actual experiment accounting. An ambitious long-context agent loop can cost far more than this example. Reserve before each attempt and reconcile unknown charges; do not assume a rejected response was free.

## Bounded source findings and exact implications

| Finding | Evidence and scope | Required disposition |
|---|---|---|
| JM-SRC-001: legacy qualification is insufficient for economic admission | Actual `ModelRecord.qualified` property returns true with 50 resolved disagreements, mean 0.021 R and missing Brier. Source contains no CI, cost or selection inputs. Probe is in `evidence/rev117/source_probes.json`. | Preserve the legacy diagnostic label if needed for compatibility; route economic/probability qualification through the new exact target, opportunity, uncertainty, cost and independent evidence contract. This does not prove a live unauthorized promotion occurred. |
| JM-SRC-002: blind-packet construction does not guarantee blindness | Actual `blind_packet` preserves injected `model_id`, nested author metadata and narrative authorship. It is a local function counterexample, not a claim about every caller. | Allowlisted context serialization, free-text leakage tests, access separation, canaries and objective oracles; different model names do not prove independence. |
| JM-SRC-003: inference remains in the synchronous risk return path | AST/source inspection finds `cognition.wake` at account_service.py:658 before return at :660. Default cognition can be disabled; no actual deployed delay was measured. | Durable asynchronous boundary and measured noninterference under stalled provider/queue load, preserving urgent financial work. |
| JM-SRC-004: two budget accounting paths need reconciliation | Runtime budget checks once before the fallback loop and records spend after normalization; provider scheduler counts acquisition separately. This is source inspection, not a billed-provider test. | Atomic pre-attempt global reservation, inclusive failed/retried calls, conservative unknown liabilities and durable settlement across workers/restart. |
| Jev boundary is already intentionally advisory | Retained PR93 `JevVanAdvisor` uses consumer-scoped shared-service access; SHADOW/apply_effect and owning deterministic consumer are explicit. Source reference remains in the prior source-admission crosswalk. | Preserve it, admit trading-specific typed modules and validate scope/calibration. Never reinterpret attention/browser scores or transport labels as financial evidence/authority. |

The checked local trading files are fingerprinted in the probe receipt, anchored to published commit `874774d4ece98718f4d3e80002ec136320a84e13`. The preserved Jev adapter is from admitted review input commit `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`, not claimed deployed. Three probes executed: two pure-function/property counterexamples and one static call-order check. They are not the 24 planned application acceptance tests, which remain NOT_RUN.

## Hardening beyond the existing experience loop

- A modern model can know historical outcomes in its weights even when its prompt is time-filtered. Treat retrospective LLM backtests as potentially contaminated; seal prospective outputs before later outcomes arrive.
- Preserve raw admissible outputs and exact identity/configuration epochs for replay. A deterministic risk engine does not make remote generation deterministic; provider alias, prompt, retrieval or calibration changes invalidate inherited qualification.
- Measure all relevant opportunities, not just resolved disagreements; retain missingness and censoring. Calibrate the declared target against an appropriate reference forecast. Do not turn a disagreement-helped score into trade-win probability.
- Separate procedural adherence from economic viability. A good-process strategy can lose its edge over time; registered drift tests can suspend it without treating each individual loss as proof of failure.
- Protect research inputs from instruction injection, cross-account memory and secret leakage. Archived financial text and agent memory are evidence, never a source of tool or trading authority.
- Complete positive improvement mechanisms as well as refusals. Known-edge controls must show evaluator power, while null ensembles quantify false discoveries. Refusing all candidates is not a successful learning system.

## Sources and limits

- [Google model catalogue](https://ai.google.dev/gemini-api/docs/models)
- [Gemini 4 Argon model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)
- [Google pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [DeepSeek API documentation](https://api-docs.deepseek.com/)
- [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [DeepSeek thinking-mode behaviour](https://api-docs.deepseek.com/guides/thinking_mode)
- [Google TimesFM repository](https://github.com/google-research/timesfm)
- [FinGPT repository](https://github.com/AI4Finance-Foundation/FinGPT)

`REV117_SOURCE_REGISTER.json` records retrieval metadata, full fetched-body hashes and bounded archived excerpts. Whole third-party pages are not republished in this package. Source/provider claims establish documented capabilities, not an independently measured financial result. Experiment templates, typed records, source findings and application contracts are integrated into the main plan; real qualification still requires admitted execution and independent receipts.
