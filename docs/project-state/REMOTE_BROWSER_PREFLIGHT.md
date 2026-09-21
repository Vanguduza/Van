# Remote Browser — Phase 0 state

**Blueprint:** `docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md`
**Programme ledger:** `docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json` (122 rows)
**Baseline:** `main` at `66e4e42` — the PR #48 merge the blueprint names
**First preflight run:** `evidence/van-remote-browser/PREFLIGHT_REV_1_5.md`

This file is the §33 preflight document: the living statement of where Phase 0 stands. The
evidence file above is the dated record of the run that produced it; this one is edited as
the programme moves.

## Phase −1 — the closure gates

Run before and after every closure group (§35):

```bash
python3 tools/ci/maturity_gate.py
python3 tools/ci/authority_map.py
python3 tools/ci/ledger_reconcile.py     # now also enforces §40.5 against the RB matrix
python3 tools/audit/kotlin_reachability.py
```

Green at `66e4e42`. §35 forbids proceeding from a red baseline, so this is a precondition
rather than a report.

## Phase 0 checklist

| item | state |
|---|---|
| exact current `main` resolved | done — `66e4e42` |
| Project Truth / Security Policy / Authority Map read | done |
| current schema read | done — 26, next unused is 27 |
| canonical browser aliases revalidated | done — `public_research`, `authenticated_owner`, and no others |
| §13 dual-homed topology locked | done — `VAN-ADOPT-REMOTE-BROWSER-STREAMING-001` |
| `deploy/van-browser-stream/` created | **not yet** — RB-010, checkpoint C7 |
| profile-storage implementation selected | **not yet** — RB-118, needs the host |
| Browser Control Agent private mTLS contract defined | **not yet** — RB-115, checkpoint C7 |
| next schema migration resolved | done — 27, resolved from the live repository |
| implementation matrix + component refs created | done — 122 rows, enforced by the reconciler |
| owner-decision records created | done — see below |
| dependency candidates recorded | done — digests measured, not quoted |

## Decisions taken, and by whom

The owner delegated the Phase 0 decisions and asked for recommendations rather than
questions. Each is an artefact with its `decision_type` recorded honestly; none is written
down as an owner signature.

| record | type | what it settles | what the owner still has to do |
|---|---|---|---|
| `docs/decisions/VAN-ADOPT-REMOTE-BROWSER-STREAMING-001.yaml` | `OWNER_DELEGATED_RECOMMENDATION` | dedicated dual-homed stream host; Android WebRTC and OkHttp admitted with measured digests | provision the host and its VCN attachment; decide TURN placement once measured |
| `docs/decisions/VAN-ADOPT-OFFLINE-VOICE-RUNTIME-001.yaml` | `OWNER_SUPERSESSION` | reverses closure-blueprint owner decision 2 (“Sherpa ASR — do not build it”) for the offline-voice requirement | supply or approve the voice model bundle and its licence |
| `docs/decisions/VAN-ADOPT-STAGEHAND-001.yaml` | already `SIGNED` (2026-09-18) | Stagehand as a Hermes subagent | nothing; what remains is live certification, an external gate |

## What the repository cannot resolve

These are not deferred work items. They are things no amount of code here can produce:

- **A Browser Stream Host.** RB-010 and everything downstream of it.
- **A physical S24.** RB-120's attestation preflight, every device canary, and the 16
  `ENVIRONMENT_UNVERIFIED` residuals already carried from PR #48.
- **A Stagehand runtime and a Browser Harness runtime.** Adapters exist; §32.8 forbids
  moving the ledger on the strength of an adapter.
- **A voice model bundle.** The loader, manifest and fail-closed readiness classification
  are repository work; the model is not.

Every component that depends on one of these ends at
`EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` with the absent artefact named, never at
`INTEGRATED_AND_EVIDENCED`.

## Corrections made to the blueprint on landing

Four, recorded in its own §0F and pinned by `tests/contracts/test_remote_browser_matrix.py`
so a later edit cannot quietly restore the stale text. One of them was a correction to a
correction: the first draft of §0F.1 claimed no component is `CALLED_UNTESTED` any more,
which is false — two still are, and what changed was their terminal state. The contract test
caught it before the commit.
