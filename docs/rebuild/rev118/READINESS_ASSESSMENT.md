# Rev1.18 readiness assessment — 2026-10-21

Scope: start of execution on `ccr-9e07e1af-8mgz1p`, derived from `consolidation/opus-clean-rev118-20261021` at `b02075f3`. Machine state lives in `EXECUTION_LEDGER.json`; this note explains it.

## Verified facts (command and result)

| Claim | Probe | Result |
|---|---|---|
| Serving model | `get_session` | configured and last served `claude-opus-5-5` |
| Archive identity | `sha256sum` | `6c7c7c1c…3a57a8`, matches receipt |
| Package identity | `git rev-parse <commit>:package`, `git diff --quiet 3c3379bd HEAD -- package` | tree `ac0226a2` at delivery and at source head; fresh ZIP extraction identical |
| Documentary verifiers | ten package commands | all exit 0 (26/26, 79/79, 47/47, 36/36, 35/35, 900 members). Documents only |
| Consolidation inputs | `tools/consolidation/verify.py` | 70 branches, zero findings once the Project Truth hooks were installed |
| Registry counts | `tools/rebuild/pre001.py` trace check | 324 / 1,610 / 131 / 349 / 234 / 93 / 171 / 22 / 72 derived from the artefacts |
| Branch and PR state | live `git ls-remote` + GitHub pulls API | 71 heads (70 evaluated unchanged, 1 new: the consolidation); 104 PRs (25 open, 65 merged, 14 closed unmerged) |

## Instrument corrections made during this packet

1. The session clone was **shallow**. On it, 54 PR heads looked unreachable from every evaluated branch. After `git fetch --unshallow` the count was 31. The tool now refuses to run on a shallow clone.
2. `main` was pruned and re-rooted (`c910ed1d`, "canonical-main prune"), so a merged PR's head need not be an ancestor of `main`. Ancestry under-reports preservation. The inventory therefore also checks the content layer: does every post-image blob of the PR's own diff exist in evaluated history? 12 of 31 PR-only heads are content-preserved (11 merged, plus PR-104 dispositioned as the consolidation head); 19 are not.
3. The first trace selftest passed vacuously, because the real registry already has 5 findings. Each mutation must now add a finding that the baseline lacks.

## Dependency position

Every one of the 82 backend and 12 backend-verification units depends on **PRE-003**. PRE-003 is an independent F15 issued by a trusted issuer together with a valid owner signature; this pack's checker cannot issue it. So the only dependency-ready work is PRE-001, then PRE-002. No backend or application implementation can start under the canonical programme until PRE-003 is issued. That is a real authority blocker, not a choice.

## What professional delivery needs beyond code, and the method for each

- **Source admission:** a frozen ref and blob inventory, a content-layer preservation check, and a function-level ledger with reviewed dispositions (PRE-001, in progress).
- **Domain invariants and financial reconciliation:** property and state-machine tests against independent oracles. Examples are the TCA decomposition versus direct signed fill cost, and joint slice feasibility. These belong to BE-009/010/012 after F15.
- **Recovery:** fault injection at the outbox and transaction boundaries, plus restart and replay equality (BE-003/010, BQ-002/007).
- **Dependency and provider qualification:** exact-version pins and qualification records. A selected eligible CEX spot target is an owner/provider decision (OQ-CRYPTO-01).
- **Economic claims:** a qualified evaluator, sealed datasets, a trial census and out-of-sample comparison (BE-035/036, BQ-009). Engineering completion is never equated with edge.
- **Migration, accessibility and release:** after BG-001 only, with the S24 Ultra through admitted Artemis as the final device evidence.

Raw evidence used here: Git objects, live refs, PR API readback and package registries. Evidence that could falsify the conclusions: `pre001.py check` (drift), `pre001.py selftest` (ten induced failures), and the committed raw ref snapshot.

## Separations

- **Verified:** the facts in the table above.
- **Design requirements:** the Rev1.18 package, which is unsigned (`signed_authority: false`).
- **Assumptions:** none adopted for gate purposes.
- **Unresolved:** PRE-003 issuer and signature; 21 owner questions; trusted-base main admission (PR #94); native DIAL/Oracle/Artemis are not callable from this session.
