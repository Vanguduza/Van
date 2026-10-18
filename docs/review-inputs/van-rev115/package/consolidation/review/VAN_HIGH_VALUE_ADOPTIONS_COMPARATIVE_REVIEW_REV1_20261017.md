# VAN High-Value Trading Adoptions — Comparative Review

**Date:** 17 October 2026  
**Review state:** `REVIEW_COMPLETE / INTEGRATION_CHANGES_RECOMMENDED / NOT_ADOPTED`  
**Basis:** Uploaded High-Value Trading Adoptions Rev1.0; Forecast Adoption Rev1.1 and its implementation pack; current VAN Next Unified Rebuild Rev1.11 candidate; all currently advertised VAN branch heads; selected source-level review and focused VM paper-adapter probes.

## Executive decision

The uploaded blueprint is a useful complementary domain-adoption proposal, not a replacement for the current forecast specification and not an implementation-ready alternative roadmap. Preserve Forecast Rev1.1's full engineering obligations inside the newer Rev1.11 unified candidate. Integrate the uploaded document's genuinely new chain-security, sellability, temporal-wallet and complete-discovery-cohort requirements through explicit deltas. Correct the scope, gate, evidence-grade and source-baseline conflicts before adopting it.

The strongest genuinely new contribution is **read-only crypto safety and executable-exit intelligence**, not another Qlib, LightGBM or Jev stack. Several supposedly new general capabilities already have concrete source on unmerged branches. Conversely, the forecasting libraries are still represented by plans/declarations rather than a demonstrated working integration in the scanned tracked source.

The uploaded document explicitly says NOT ADOPTED / NOT DEPLOYED and limits its own original repository evidence to selected default-branch reads. This review respects that boundary and supplies a broader branch comparison; it does not convert the proposal into owner authorization. [S1 §§0,15]

## 1. What was inspected and what was not

The Global DIAL audit ran on the actual Oracle `van-trading-core` VM in an isolated scratch repository under ubuntu uid1001. No desktop was used. The branch-head snapshot covered **66 branches, 63 distinct head commits and 4,634 distinct file paths across their trees**, with no ref drift during the inventory pass. Every head tree was read and compared with the pinned main SHA.

The content pass examined 3,798 distinct path/blob pairs in selected text formats, requesting 3,706 unique blobs and scanning 3,680 UTF-8 blobs. Twenty-six candidate blobs were excluded for size/encoding/binary reasons. Other file extensions were outside the lexical pass. The audit performed mechanical text/import analysis across those variants and selective semantic review of the relevant owners, adapters and changed code. This is **not** a claim of full semantic correctness, test coverage or deployment qualification for every file.

“All branches” means the repository's currently advertised `refs/heads`: it does not include deleted historical heads, unfetched forks, uncommitted work or separately deployed untracked services. No full trading suite or model training ran this pass. Four focused synthetic PaperAdapter observations did run on the exact PR101 source. [E1–E3]

### A newer integration baseline exists

The Library's **VAN Next Unified Backend-First Rebuild Rev1.11** already incorporates Forecast Adoption Rev1.1, Rev1.10 and the Opus PR101 source. It defines a single 121-packet plan and 205 active requirements, including all 90 forecast requirements. Its status remains an independently unadmitted consolidation candidate—not F15, not Backend Complete, not deployed. Its historical documents and gate IDs are lineage/aliases, not alternative executable plans. [S3 opening, §§0,27–29]

The correct next integration point is therefore a reviewed delta to that consolidated candidate. Do not accidentally restore Rev1.10's separate scheduling or replace the complete forecasting scope with this uploaded document's smaller M0–M9 programme.

## 2. Source findings that change the comparison

### 2.1 There is no single “most complete branch” that can be selected blindly

The pinned merged baseline is `8eb1889822fc8a83f219977c15340172e16acd91`. PR101 is `a39f241b0135cf92cc5a6b9a28af226aa294603d`; the PR93 canon family includes `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`. Account coordinator and account service each have **five distinct source versions** across the heads.

PR101 carries newer execution/ledger/lockout corrections. The canon family carries Jev consumers, cognitive evidence resolution and trading temperament integration not present in the same form in PR101. Merge or transplant by reviewed function/contract with regression evidence, not by choosing the branch with the most commits. This review does not authorize merging any branch. [E1; S4–S9]

| Branch or family | What must be preserved or distinguished |
|---|---|
| `main` | Actual merged source, not the complete intended product |
| PR101 / `ccr-8f1201e9-w1xm0r` | Resting-order support, entry semantics, slippage-unit and rounding changes, incremental ledger checks, recoverable lockouts; remaining defects below |
| PR93 and canon-derived branches | Shared Jev gateway/advisor/native surfaces; cognitive and typed evidence integration; temperament contributions |
| PR92 / `chatgpt/vati-opportunity-modes-20261008` | Signed NORMAL/RISKY/AGGRESSIVE selection proposal machinery; economic evidence admission is separate |
| `muse/vati-opportunity-modes-20261008` | Head equals main in this snapshot; the branch name is not proof of a separate published implementation |
| PR77 cognitive fabric | Advisory producer/consumer work that must not be overwritten with a parallel model-evidence mechanism |
| Jev control/convergence branches | Existing service clients, registered judgments, owner controls and source-level consumers |
| PR76 / web acquisition | Reusable bounded acquisition infrastructure; it does not itself implement token security or wallet attribution |

The focused branch JSON in this pack contains exact hashes for selected relevant heads. The complete 66-head inventory is retained on the VM and identified by path and SHA-256 in the evidence summary. It was not replaced by a list inferred from branch names.

### 2.2 The research integrations are not demonstrated in scanned source

No direct production Python imports of Qlib, LightGBM, NeuralForecast, XGBoost, scikit-learn or Freqtrade/FreqAI were found in the scanned supported source. Forecast-library text matches were documents and stack/lock declarations. Prediction-market matches were documentation rather than an implementing Kalshi/Polymarket adapter. Chain-security matches were false positives in third-party licence text, not concrete token analyzers. [E2]

This supports “planned integration remains to be built in the inspected source,” not an absolute assertion that no external service, alias or uncommitted implementation exists anywhere. The current blueprint must preserve actual train/export/load and provider/consumer acceptance, not count package names in the stack lock as implementation.

### 2.3 AllocatorV1 already exists—and still excludes confidence

`portfolio_allocator.py` has the same blob on all 66 heads. It implements both deterministic V0 and an `AllocatorV1` adding edge-floor, capital-efficiency, execution-quality and stability terms. Its V1 explicitly continues to exclude uncalibrated confidence. [S5]

The uploaded phrase “the calibrated allocator upgrade / V1 gate” needs an exact policy/version mapping. Merely selecting the existing `AllocatorV1` does not enable calibrated model-weighted ranking. Introduce or extend an explicitly reviewed policy version and input contract; do not create another allocator or relax confidence restrictions indirectly through rank order.

Capital reservations remain with the account-coordination path after the proper risk decision. “Allocator never reserves” must not be misread as “the whole account replay has no capital reservation.”

### 2.4 Jev is not greenfield

The canon branch has `backend/van_gateway/jev/advisor.py`, `client.py`, `api.py`, production callers and native Jev controls. `JevVanAdvisor` is explicitly a consumer of the one shared `dial-jev` service, using a consumer credential and returning annotations—not a new authority or trade sender. [S6]

A06 should extend registered domain questions, context provenance, output validation and contribution studies through these owners. Existing attention/critic/browser judgments do not prove that a token-vetting question set exists or has financial predictive skill. Reuse the plumbing; validate the new domain behavior.

The canon's `trading/vati/learning/evidence.py` also enforces exact ledger-resolved evidence classes and allowlisted kind/producer pairs. Research or counterfactual records must not be relabeled as authoritative execution facts simply because they have hashes. [S7]

### 2.5 The backtester still needs correction across the branch set

`backtest/engine.py` is identical across all 66 heads. It still walks open → low → high → close, records its equity-curve point before terminal forced liquidation, and instantiates a single-instrument DecisionCycle. That is not evidence of full account-coordinator parity or complete execution-realistic accounting. [S8]

Both inspected PaperAdapter variants calculate realized P&L from price difference, size and value-per-price-unit; explicit commission and financing debit integration is not shown in that formula. A separate cost estimate used to screen candidates is not equivalent to charging those costs to simulated cash. These corrections must remain under the existing BE-010/BE-035 and forecast 009/010 obligations. [S9; S2 §6]

PR101 is progress, but not complete closure. The new review **reproduced previously documented Rev1.11 counterexamples**, rather than claiming them as discoveries for the first time:

| Focused VM probe on `a39f241b…` | Observed result | Interpretation |
|---|---|---|
| Buy limit 1.10000 | FILLED at 1.10007 | Limit-price invariant fails |
| Sell limit 1.10000 | FILLED at 1.09993 | Limit-price invariant fails |
| Distant buy limit | ACCEPTED; one pending order | Positive control confirms resting support exists |
| Resting stop with no explicit expiry | 86,400,000 ms lifetime | Adapter fallback is 24 hours; its STOP_ENTRY policy specifies four hours |

The direct adapter expiry probe did not exercise full policy-to-router propagation. The unified candidate already assigns the combined expiry issue to corrective contracts. These synthetic observations are not broker orders, live qualification or a full-suite pass. [E3; S3 opening; S9]

## 3. Adoption crosswalk

The complete machine-readable crosswalk accompanies this report. Forecast packet suffixes below refer to existing `VAN-ML-PKT-*` identifiers; in the unified plan, existing gate aliases remain aliases rather than second gates.

| Uploaded adoption | Review disposition | Existing home / net-new part |
|---|---|---|
| A01 executable economics | Extend, do not duplicate | Forecast 007/009/010/044 plus BE-010/035; new DEX-specific exitability and route economics |
| A02 Qlib/LightGBM/NF | Largely already specified | Forecast 011–025; preserve all model, registry, lifecycle and calibration obligations |
| A03 incremental evaluator | Valuable clarification to an existing obligation | Forecast 005/007/008/010/027/030/031/047; add full discovery cohorts and changed-trade-path evaluation |
| A04 crypto discovery | Genuine new domain scope | Chain/token/pool identity, discovery retention, staged filters and reason-specific rechecks |
| A05 chain/wallet intelligence | Genuine new domain scope | Chain-specific security facts, temporal attribution, sellability, pool migration and finality/reorg behavior |
| A06 typed Jev | Reuse existing branch implementation | Shared Jev/cognition owners; new registered questions and domain evaluation only |
| A07 prediction-market context | Narrow subset of existing mandatory scope | Retain all forecast 037–048, including non-order-sending laboratories |
| A08 agent/UI mapping | Reuse owners; extend projections | Existing Hermes and risk/router ownership; post-BG candidate funnel, not early frontend |

## 4. Integration-blocking specification conflicts

### R01 — Use the actual current umbrella and preserve authority lineage

The uploaded proposal names Rev4/5 and derived profitability documents but does not map to Forecast Rev1.1 or the newer Unified Rev1.11. Amend its authority/reference section, execution cards and delivery milestones with exact document hashes, source heads and current canonical selector. The unified candidate itself still needs independent semantic admission. Do not turn its name into proof of approval. [S1 §0; S3 opening]

### R02 — Do not thin mandatory forecasting or prediction-market scope

The upload makes NeuralForecast and Kalshi/Jev later conditional experiments. That is acceptable for **economic influence**, but incompatible if used to omit current mandatory implementation: usable NHITS/NBEATSx/DeepAR, the specified challenger plugins, retained paths, model lifecycle and the event-contract valuation/arbitrage/market-making research laboratories. [S1 §§1,12,15; S2 §§1,22]

A functioning model integration can truthfully conclude NO_QUALIFIED_MODEL or reject a trained candidate. That negative economic result does not excuse leaving required software absent. A07 must not reduce the complete existing prediction-market programme to one probability-change feature. Keeping live event-contract execution disabled remains compatible with both plans.

### R03 — M8 is scheduled too early

The uploaded M8 permits UI after M2 and at least one qualified feed. The current unified programme requires all mandatory backend work and independent global BG-001 first. Replace M8's readiness condition with the actual BG-001 dependency. Headless API/projection contracts can be implemented earlier; new UI cannot. G0–G6 and M0–M9 should map to existing canonical units, not become independent approval or release routes. [S1 §12; S3 opening]

### R04 — Evidence-grade names collide dangerously

The upload uses E1–E5 as publication/source-quality categories. Unified Rev1.11 uses E0–E6 as implementation/acceptance evidence levels. In one scheme E3 means vendor capability and E5 means unverified creator claims; in the other E3 is a test receipt and E5 is device certification. [S1 §0.1; S3 §0.4]

Never store both in one unnamespaced `evidence_grade`. Preserve separate fields such as `research_source_class` and `implementation_evidence_level`, with an explicit mapping that does not promote one into the other. A vendor capability or creator screenshot is not a passed software test or a certified phone.

### R05 — Preserve compatible branch work before extending it

A new Jev service, duplicate model registry, parallel calibration package or newly reinvented lockout governor would be avoidable duplication. The uploaded “only if absent” directory proviso is useful, but it must now point to the actual branch matrix and the forecast runtime/research split. Preserve PR101 execution fixes while reconciling canon learning evidence and signed temperament work at shared account-runtime seams. [S1 §§0.3,3,7; E1–E2; S4–S7]

### R06 — Separate software closure, source access, effect admission and live authority

The upload's staged language is compatible only when these are separate dimensions. A defensive veto can be useful without positive alpha; a read-only research component must not require a funded venue account just to finish its offline code. Conversely, an externally blocked source must not be marked provider-E2E complete or used to waive global backend acceptance. Preserve the no-new-procurement scope and report unresolved provider capabilities explicitly. [S1 §§11–13; S2 §22.2]

## 5. Technical refinements worth integrating

### R07 — Split observed executable facts from modeled economics

The proposed `ExecutableCostEvidence` mixes quote facts with projected exit proceeds and `p_fill_estimate`. Its prose correctly requires units and avoids double-counting, but the illustrative object does not itself provide sufficient target/calibration lineage for those predictions. [S1 §2]

Use linked records under the existing owners: an observed quote/route snapshot; an execution-cost/fill forecast; and a resulting net-edge assessment. Each needs side, quantity/units, currency, price convention, venue/route, as-of/available-at/expiry, fee-inclusion flags and immutable references. Predictions additionally need target/horizon, model/transform/calibration revision and domain validity. DEX simulations need a block/slot and relevant contract/router state binding. Do not name every modeled outcome an observed “fact.”

### R08 — Preserve size-only attribution and add whole-policy replay

The upload correctly identifies `ShadowEntry.shadow_r` as size-only. Current source multiplies actual R by a shadow multiplier. That can describe contribution in common baseline risk units under proportional assumptions; it is not a new trade's independently remeasured own-risk R, nor a replay of altered timing, nonlinear fees, liquidity, capital usage or selection. [S1 §4; S10]

Add matched-opportunity records to the existing experiment and account-replay services. Seal the discovered universe, both policy decisions, rejects, expiries, unavailable observations and versioned fill assumptions before outcomes mature. Replay each account independently; a skipped position changes later cash and opportunity availability. Preserve the old shadow view as a specifically labeled attribution view.

### R09 — Improve causal/statistical wording without manufacturing a new gate

Call the normal result “incremental policy performance under specified replay assumptions,” not identified causal contribution merely because two arms were simulated. Use event/time/asset-cluster-aware resampling where observations are dependent, not an unspecified independent per-row paired bootstrap. Measure false rejection of legitimate winners as well as dangerous candidates avoided. [S1 §§4,11; S2 §§16,22.14]

The proposed lower 95% confidence-bound requirement is a proposed research policy, not existing authority. Bind materiality, effect size, sample adequacy, multiple trials and stopping rules to the one versioned validation policy. Do not silently replace canonical DSR/PBO or create a contradictory second threshold service. Distinguish a terminal return quantile from path-dependent adverse excursion and stop-touch probability; define and validate each target separately.

### R10 — Expand crypto safety as a domain capability, not a trading desk

A04/A05 are the clearest new value. Retain chain-specific asset and pool identities; source-backed role attribution; technical-pool/burn exclusions without discarding raw concentration; time-indexed flows; contract-capability checks; independent sell-side simulation; and typed UNKNOWN states. A single holder snapshot cannot support a claim of holder growth or accumulation. [S1 §§5–6]

Refine identity normalization per chain rather than applying a universal string transform. Bind security findings and route simulation to the actual state observed, invalidate affected descendants on state revision/reorganization, and track pool migrations without changing the token identity. A successful read-only simulation is evidence at that state, not a promise that a later sell will succeed.

Separate factual restrictions, uncertain wallet attribution, manipulation-risk predictions and economic forecasts. `NO_HARD_BLOCK` must remain distinct from SAFE_TO_BUY. A safety veto cannot prevent mandatory risk-reducing exits or acquire wallet/signing authority. No new funded crypto venue is authorized by adopting the research code.

### R11 — Keep one bounded serving and cognition hierarchy

The upload puts bounded inference broadly in T2. The forecast blueprint provides a bounded local ForecastService in the designated forecasting lane, with T0 consuming prepared results rather than synchronously calling model training, registry or remote LLM services. Classify slow Jev/chain/public-source work separately from inexpensive precomputed model inference; do not move every inference call into remote T2 or drag heavy research dependencies into core trading imports. [S1 §§0.2,12; S2 §§3,12]

Existing typed evidence resolution and snapshot/TTL checks must remain the admission path. A model ID, artifact hash, registry alias or source quality score must not confer authority by itself. Malformed, non-finite, incompatible or expired outputs must have explicit behavior and an exercised positive valid path as well as rejection tests.

### R12 — Replay determinism is not universal retraining identity

Uploaded INV-12 promises the same candidate/model state/decision hash for frozen inputs and versions. Scope exact equality to canonical recorded decisions and a defined reproducible inference environment. Distinguish deterministic replay of persisted outputs, fixed-seed same-environment inference, cross-device numerical tolerances and independently repeated stochastic training. Do not claim every neural/GPU training run is byte-identical because the dataset is frozen. [S1 §11.2; S2 §8.4]

## 6. What the existing forecast specification should also change

This is not a one-sided review. Forecast Rev1.1 was explicit that it had not re-audited every branch. Its source reconciliation and consumer maps now need the new 66-head evidence, the PR101 code baseline, the canon evidence/Jev/mode overlaps and the Rev1.11 single-plan integration. Do not continue describing resting orders and recoverable lockouts as absent everywhere. [S2 §2; E1–E3]

Its broad point-in-time and policy-replay duties should explicitly absorb full token-discovery cohorts, technical-holder classification, state-bound sellability and rejected/migrated/disappearing pools. The crypto subdomain requires additional schemas, producer contracts and adversarial cases; merely attaching the new PDF/Markdown as reading material is insufficient.

The combined programme must regenerate its requirement→packet→producer→consumer→test→evidence→UI traceability and DAG after scope admission. Preserve all 90 forecasting requirements and current parent corrective contracts. Add new IDs only through the programme's actual generator; this review invents no new packet count or acceptance certificate.

## 7. Recommended reconciliation sequence

1. Freeze the exact document/source identities and reconcile the existing single-plan selector. Preserve the supplied High-Value document as provenance rather than allowing two active roadmaps.
2. Perform function/contract-level source consolidation under BE-001. Carry forward the compatible PR101 execution work, canon Jev/cognitive evidence, signed mode contributions and existing owner controls.
3. Close the already specified simulator and evaluator defects before using financial backtests to admit new forecast effects. Retain positive controls and deliberately failing counterexamples.
4. Implement the existing full forecasting programme and admit A04/A05's additional read-only domain scope through real producer, storage, consumer, model/evaluation and runtime contracts. Reuse the shared pipeline rather than creating a crypto-only parallel forecasting engine.
5. Complete backend APIs, failure/recovery behavior and independent backend qualification. Only BG-001 permits new native funnel and analytics UI; model influence and live trading require their separate scoped evidence/owner decisions.

This sequence is a recommendation for the existing canonical plan, not authorization to start a new implementation or merge campaign.

## 8. Review outcome and delivery boundary

**Recommended outcome:** retain and extend the current forecasting/unified specification; adopt the uploaded document as a corrected domain-specific annex and requirements delta. Its wallet/chain/sellability material is valuable. Its general forecasting and Jev sections should chiefly link to and strengthen existing owners. Its optional-model, reduced prediction-market and early-UI scheduling must not replace current mandatory obligations.

No application source or input blueprint was changed, no branch was merged, no source was economically admitted, no model was trained, no broker/chain transaction occurred and no F15/BG/production certificate was issued. The four local-in-VM paper observations are deliberately narrow. Raw branch/content/probe evidence remains in the named audit workspace. Downloadable JSON here is explicitly a compiled summary and crosswalk, not a replacement for those raw source/receipt artifacts.

## Source and evidence register

- **S1** — User upload: `VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_2026-10-17.md`, 466 parsed lines. Referenced by its original section numbers. Its donor audit was located in Library and states that private FOMO/desk execution and the creator's private production deployment were not available. Those performance claims were not used to qualify VAN.
- **S2** — `VAN_FORECAST_ADOPTION_BLUEPRINT_REV1_1_20261017.md` and its 59-member implementation pack. The review read the complete master and inspected the machine plan/crosswalk identities. Checks from its original delivery remain historical document checks, not new application proof.
- **S3** — Library `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_11_20261017.md`, file ID `file_00000000fbe48208b29a976c444e8e44`. Reviewed opening authority, current source/corrective findings and targeted plan/requirement sections; not a new full semantic audit of all 3,427 lines.
- **S4** — [PR101 metadata and scope](https://github.com/Vanguduza/Van/pull/101), pinned head `a39f241b0135cf92cc5a6b9a28af226aa294603d`. PR-reported full-suite results remain reported rather than rerun here.
- **S5** — [Portfolio allocator](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/arbiter/portfolio_allocator.py), blob `d3a824b500618918d177b4d7eff37ab585a08614`.
- **S6** — [Shared Jev consumer](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/jev/advisor.py), blob `8e9f78030613325dcd9e53b14d927ad4d5013245`.
- **S7** — [Learning evidence resolver](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/trading/vati/learning/evidence.py), blob `b9a2cc0e0eb4701534ae918373406d6fca495605`.
- **S8** — [Backtest engine](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/backtest/engine.py), blob `0e43a0c75269f608b74e0c9b12c1e4d731da377c`.
- **S9** — [PR101 PaperAdapter](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/execution/paper.py), blob `f9be04e3fbbb174726ccd86834b3b77ac81b36a2`; [OrderCommand contract](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/execution/base.py).
- **S10** — [Size-only shadow book](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/cognition/shadow_book.py), blob `4e6068e78b43ad005413962dd42543d026d81371`.
- **E1** — Actual typed inventory run `van-hva-allbranches-run-20261017-01`; complete VM `BRANCH_REVIEW_INVENTORY.json` SHA-256 `3dc2d3bbe93eab38f510573b696e150e2b5e2a0ec8df2e8a76606fa2da86cc5c`.
- **E2** — Actual typed text/import scan `van-hva-content-run-20261017-02`; VM `ALL_BRANCH_CONTENT_SCAN.json` SHA-256 `051d75ca3bda4ab2d8330dc877048e00aa4808eebe3807afe8848457e72f527c`.
- **E3** — Actual focused adapter probe `van-hva-probes-run-20261017-03`; source `a39f241b…`; raw `PAPER_PROBE_RECEIPT.json` and export retained on VM. The E1/E2/E3 labels in this report are **local bibliography identifiers only**, not either blueprint's evidence-grade enums.

**Raw VM audit directory:** `/home/ubuntu/work/van-high-value-review-20261017-005_3oh7/`. This is a forensic evidence location, not a public download link. Input SHA-256 values and typed request identities are included in `REVIEW_EVIDENCE_SUMMARY.json`.
