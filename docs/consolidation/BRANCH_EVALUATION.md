# Van branch consolidation — 21 October 2026

All **70** remote branch tips were evaluated at the recorded cutoff. Source was consolidated on `consolidation/opus-clean-rev118-20261021`. The default branch and live hosts were not changed.

The exact Rev1.18 package is the active rebuild specification. Its historical source snapshots are evidence, not extra modules to import or test. Existing locked authority and release gates remain in force.

## Dispositions

| Disposition | Branches |
|---|---:|
| ALREADY_IN_MAIN | 24 |
| HISTORICAL_EVIDENCE | 5 |
| INTEGRATED | 4 |
| INTEGRATED_ANCESTOR | 15 |
| PATCH_EQUIVALENT_SUPERSEDED | 1 |
| PRESERVED_CANDIDATE | 10 |
| RECONCILED_IN_SOURCE | 9 |
| SUPERSEDED_SPECIFICATION | 2 |

## Every branch

| Branch | Tip | Disposition | Reason |
|---|---|---|---|
| `ccr-71397b02-lm6fid` | `bdd63a40174d` | INTEGRATED | Source baseline including owner-attributed cleanup and historical ledger reconciliation. |
| `ccr-8f1201e9-w1xm0r` | `a39f241b0135` | INTEGRATED | Merged trading corrections and recovery controls; three merge conflicts resolved preserving canonical learning evidence and PostgreSQL atomic reads. |
| `chatgpt/allow-sandboxed-playwright-userns-20261008` | `504a3f6759ff` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/better-remote-commander-oci-20261021` | `739e5904d4fb` | PRESERVED_CANDIDATE | Optional pinned host agent installer and qualification scripts; no Van runtime integration or activation. Keep separate from current application source. |
| `chatgpt/fix-browser-harness-pillow-pin-20261008` | `1e9e18a710d7` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/fix-browser-runtime-ancestor-acl-20261008` | `5dcf14969359` | RECONCILED_IN_SOURCE | Execute-only ancestor ACLs retained in canonical historical bootstrap; canonical browser placement is deploy/van-browser-core. Do not restore an old whole installer. |
| `chatgpt/fix-browser-runtime-path-access-20261008` | `b8af36e4ed35` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/fix-browser-runtime-path-perms-20261008` | `1698430078d8` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/fix-browser-systemd-retry-20261008` | `36690fd7c656` | RECONCILED_IN_SOURCE | Canonical bootstrap already clears worker start limits with systemctl reset-failed; preserve its later placement and authority guards. |
| `chatgpt/fix-browser-systemd-retry2-20261008` | `71a01e7a5450` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/fix-browser-systemd-startlimit-20261008` | `71a01e7a5450` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/fix-gateway-browser-runtime-staging-20261008` | `5402cabb1c85` | RECONCILED_IN_SOURCE | Canonical install_van_gateway_service.sh stages browser config and docs/decisions. Later runtime reconciliation supersedes this old patch. |
| `chatgpt/fix-stagehand-listen-syntax-20261008` | `6ade5eed60b7` | PATCH_EQUIVALENT_SUPERSEDED | Patch-equivalent syntax fix landed through the v2 branch; canonical worker subsequently moved to van-browser-core. |
| `chatgpt/fix-stagehand-listen-syntax-v2-20261008` | `96bc3590a0cd` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/fix-stagehand-readiness-window-20261008` | `7043d0aadd42` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/harden-playwright-chromium-ownership-20261008` | `306834775ab3` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/stage-browser-governance-certification-20261008` | `7231caf101cf` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/van-browser-assignment-proof-20261008` | `1b3c6d014f68` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/van-browser-sandbox-launch-20261008` | `5ffa59ef2bf0` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/van-browser-task-read-auth-20261008` | `9cab59773476` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/van-browser-tested-source-20261008` | `e22080c496db` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `chatgpt/van-overlay-firewall-persistence-20261007` | `cc60ea8edacd` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `chatgpt/van-web-acquisition-fabric-20261004` | `01e7d84a1edd` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `chatgpt/vati-opportunity-modes-20261008` | `923ecf9bbb81` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `claude/busy-bardeen-sbfo2u` | `4554ee22e438` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `claude/van-fable-forensic-audit-ds8g0o` | `620cba868ab9` | HISTORICAL_EVIDENCE | Implementation was previously merged; one additional forensic audit is retained at the archive ref as dated evidence, not current acceptance. |
| `claude/van-forge-audit-11n4wh` | `2ff009646e4b` | PRESERVED_CANDIDATE | Contains older forge/audit work and a debug owner-imported VRM experiment. Canonical source retains reviewed forge fixes; do not replace accepted visual authority or launcher with this branch. |
| `codex/cognitive-fabric-r161-20261006` | `c091d22ce217` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-canon-ci-import-path-2026-10-08` | `4ad31883d57a` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-canon-consolidation-2026-10-08` | `dfc1557ab99a` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-canon-runtime-closure-2026-10-09` | `dfc1557ab99a` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-canon-runtime-evidence-2026-10-09` | `c502cf7ab5c2` | HISTORICAL_EVIDENCE | Ancestor of evaluated codex/van-dfc1557a-direct-acceptance-2026-10-09. Three later publication/live-receipt commits describe exact dfc1557a, not the new consolidated head. Preserve dated evidence without importing its duplicate source archives as current source. |
| `codex/van-dfc1557a-direct-acceptance-2026-10-09` | `ab59c8cd0498` | HISTORICAL_EVIDENCE | Three later publication/live-receipt commits describe exact dfc1557a, not the new consolidated head. Preserve dated evidence without importing its duplicate source archives as current source. |
| `codex/van-direct-artemis-2026-10-08` | `f3cab5cb75d7` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-owner-core-only-2026-10-08` | `75e2e95b734b` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-owner-wiring-2026-10-08` | `652ef3f38717` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `codex/van-project-truth-bootstrap-review-2026-10-09` | `296d647d8755` | RECONCILED_IN_SOURCE | Canonical source contains the hook/checker framework and later CI additions. Independent bootstrap/admission findings remain a real merge prerequisite; no adoption certificate is inferred. |
| `feat/supabase-one-install-multiproject-20261020` | `16af4b93ebbc` | PRESERVED_CANDIDATE | Non-deploying multi-project fabric research/validator with external project cutover scope. No current production tenant migration or new database authority admitted. |
| `feature/muse-dual-surface-control-20261012` | `0e825b44f559` | PRESERVED_CANDIDATE | Shared Muse/owner-controls/Studio candidate chain: preserve complete source, tests and provenance at archive ref. UI/native receipt/schema integration needs canonical backend admission and BG-001; do not import candidate routes or a parallel control truth into the baseline. |
| `feature/rea-trading-accounts-tactile-20261015` | `3b2c9e04df87` | INTEGRATED | Merged atomic account registry replacement and conservative provider-capability declaration; not a claim of completed funding adapters. |
| `fix/muse-zram-host-resilience-20261012` | `72fe7fd07f2c` | PRESERVED_CANDIDATE | Optional host-specific boot-time zram helper; retain source and tests at archive ref. Application consolidation neither establishes host need nor activates a new privileged service. |
| `forge/candidate-b-rive-mechanics-20260925` | `80f3f0f304cf` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `gpt/character-forge-netcup-env-hotfix-20260923` | `9d20ce68b9b1` | RECONCILED_IN_SOURCE | Current forge bootstrap/qualifier/worker already bind isolated RIVE_HOME, explicit Java and canonical Android AVD homes; preserve later canonical source. |
| `gpt/character-forge-netcup-qualification-fix-20260923` | `359ec7d12f7d` | RECONCILED_IN_SOURCE | Current forge tools carry explicit Java and Android state selection and qualification. Older installer snapshots are superseded, not restored wholesale. |
| `gpt/character-forge-production-closure-20260924` | `4a858df1d355` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `gpt/jev-control-centre-20260925` | `f3df7a10e12f` | RECONCILED_IN_SOURCE | Canonical Jev owner surfaces and bounded proposal/readback integration were explicitly reconciled with current consent, frozen mail and durable mission contracts. |
| `gpt/jev-openmuse-convergence-r1-van-20260929` | `5138ae9a5e64` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `gpt/jev-openmuse-convergence-r1-van-20260929-parent-ccr-integration` | `78ca1baeccd8` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `gpt/memory-fabric-rev1-2-van-20260929` | `8c67f53ee522` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `gpt/meta-muse-access-live-green-20261002` | `f11a8949ba14` | HISTORICAL_EVIDENCE | Dated Meta access receipts do not prove present provider health or the new source head. Keep at archive ref; no live state promoted. |
| `gpt/meta-muse-secure-access-20261002` | `51f84a38a7ae` | HISTORICAL_EVIDENCE | Owner-only access boundary documentation and pre-auth receipt remain dated evidence at archive ref, not runtime activation. |
| `gpt/muse-egress-hardening-20260930` | `4cac338e6d20` | RECONCILED_IN_SOURCE | Canonical consolidation selectively retained scoped Muse security, qualification and launch provenance while moving production browser placement; older trading-core whole-tree restore would regress those boundaries. |
| `gpt/openmuse-van-convergence-r1` | `a8d3f1930ad9` | INTEGRATED_ANCESTOR | Retained through selected source ancestry: ccr-71397b02-lm6fid, feature/rea-trading-accounts-tactile-20261015 |
| `gpt/van-artemis-console-20260923` | `ed7dd6179ca5` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `gpt/van-character-forge-authority-closure-20260924` | `49d8d4cf8ba6` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `gpt/van-character-forge-engineering-20260922` | `b8bc8a0795d1` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `gpt/van-character-forge-production-v3-20260924` | `85610c9a2949` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `gpt/van-post-fable-product-closure-20260922` | `67eee3f924d6` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `gpt/van-rive-build-input-pack-20260924` | `ae764c510de8` | RECONCILED_IN_SOURCE | Canonical Candidate B mechanics/tools retain the later asset-pack validator and approved identity policy; older whole manifests are historical inputs. |
| `main` | `8eb1889822fc` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `muse/vati-opportunity-modes-20261008` | `8eb1889822fc` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `ops/dial-control-recovery-20260930` | `72635c8832be` | PRESERVED_CANDIDATE | One-off external host recovery workflows are operational incident tooling, not Van application source. Preserve at archive ref without enabling historical privileged Actions workflows. |
| `owner/dial-universe-whatsapp-browser-20261008` | `c0c2984e1ead` | ALREADY_IN_MAIN | Ancestor of the preserved main baseline; retained through canonical source ancestry. |
| `platform/rev3-cinematic-studio-20261016` | `4ad12183d9f6` | PRESERVED_CANDIDATE | Shared Muse/owner-controls/Studio candidate chain: preserve complete source, tests and provenance at archive ref. UI/native receipt/schema integration needs canonical backend admission and BG-001; do not import candidate routes or a parallel control truth into the baseline. |
| `platform/rev3-interaction-pr93-contribution-20261014` | `081a547117ea` | PRESERVED_CANDIDATE | Shared Muse/owner-controls/Studio candidate chain: preserve complete source, tests and provenance at archive ref. UI/native receipt/schema integration needs canonical backend admission and BG-001; do not import candidate routes or a parallel control truth into the baseline. |
| `platform/rev3-owner-controls-20261015` | `68394af3c6e5` | PRESERVED_CANDIDATE | Shared Muse/owner-controls/Studio candidate chain: preserve complete source, tests and provenance at archive ref. UI/native receipt/schema integration needs canonical backend admission and BG-001; do not import candidate routes or a parallel control truth into the baseline. |
| `review/muse-vati-rev114-inputs-20261018` | `cbd059cfb1dd` | SUPERSEDED_SPECIFICATION | Rev1.14 independent-review inputs are superseded by the exact Rev1.18 package and its parent lineage. No competing active plan imported. |
| `review/van-next-universal-coverage-b4-closure-20261016` | `0a694a998cfe` | SUPERSEDED_SPECIFICATION | Whole-product/no-blanket-waiver obligations retained by Rev1.18 action/domain refinements and qualification gates; old implementation plan is not active. |
| `review/van-rev115-20261018` | `3c3379bd791f` | INTEGRATED | Merged exact Rev1.18 blueprint package and receipt without changing package contents. |
| `spike/van-next-chart-engine-20261015` | `30bc2d03d018` | PRESERVED_CANDIDATE | Chart implementation was deliberately removed from the rebuild branch before backend admission. Preserve the spike; Rev1.18 still requires full charts after BG-001. |

## Preservation and admission

Every original tip has a corresponding `archive/van-20261021/<original-branch>` tag. The JSON registry records its exact commit, ancestry counts, changed paths, decision, and supporting reconciliation commit. Optional installers, incident workflows, unqualified UI candidates, and dated receipts remain recoverable there. Do not restore whole historical trees over current source.

No product obligation was removed by a branch disposition. Candidate capabilities still require their Rev1.18 implementation and acceptance contracts. Historical live passes apply only to their recorded source, host, and attempt.

The existing Project Truth intake/trusted-base rules and required independent review apply before main admission. This branch is a reviewable build starting point, not an agent-issued admission or release certificate.
