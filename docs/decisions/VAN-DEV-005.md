# VAN-DEV-005 — `work/dev` Development Home + project switcher

Pack: `VAN-DEVCC` (VAN Development Control Centre) · Spec: `VAN-DEVCC-R1` (DIAL
`docs/dial/final-audit/06_DEVELOPMENT_SYSTEM/VAN_DEVELOPMENT_CONTROL_CENTRE_DESIGN_REV_1.md`, the
contract this unit implements; DIAL owns design and logic, VAN builds — owner decision OD-C).
Canonical repository: `Vanguduza/Van` · Baseline SHA at implementation: `be49e8e` (`main`).
Authority: VAN Project Truth (`docs/PROJECT_TRUTH_PROTOCOL.md`), design authority
`docs/design/VAN_PRODUCT_DESIGN_DNA.md` + `docs/design/COMPONENT_CATALOGUE.md`, gates V1–V8.

**Status:** IMPLEMENTED — not built on a device or by CI yet; owner signature PENDING.
**Depends on:** VAN-DEV-001, 003, 004.
**Branch:** `claude/busy-bardeen-sbfo2u-van-android` (not merged, not pushed).

## Scope (`VAN-DEVCC-R1` §6.1)

`command/dev/DevHomeRoute.kt`.

- `@DataSource("GET /v1/dial-dev/projects")` — the switcher (admitted DIAL projects).
- `@DataSource("GET /v1/dial-dev/projects/{p}/home")` — readiness chips (FORENSIC_BUILD_READY,
  Oracle gate, runtime slots), `MetricTile` row (ready · running · blocked · needs you · in
  review, each opening the matching task view), "Now" (≤ 5 rows with harness/model/heartbeat
  and next action), "Needs you" (top 3, deep links), "Latest" (checkpoint + `EvidenceRow`s),
  health strip (Hermes/Orca/SPMRF/OpenViking/VEKL `StatusChip`s → `connected`).
- Mission controls `PAUSE_MISSION` / `RESUME_MISSION` (§3.3) — the persistent Oracle mission,
  never a local loop; statuses per VAN-DEV-009.
- Links to every hub child and to `work/artemis` (DIAL's ARTEMIS harness console, unchanged).
- EMPTY: "No admitted DIAL projects yet." DEGRADED: from `degraded[]`.

## Data layer shared by every development screen

- `VanGatewayClient.dialDev` (`DialDevClient`): GET reads under `/v1/dial-dev/*` (ingress +
  device token), `submitAction` through `postProved`, and `events()` — the SSE stream
  `GET /v1/dial-dev/events` parsed by `DialDevSse` (JVM-tested framing).
- `command/dev/DevProjection.kt`: first read on entry; refetch when an SSE event names one of the
  screen's sections; **poll at the route's stale threshold as the fallback** when the stream is
  down or absent (404 stops retrying the stream, the poll continues); 3 s poll while an owner
  action awaits its outcome.
- `dialdev/DialDevEnvelope.kt` (`DialDevScreenReducer`, pure, JVM-tested): `degraded[]` →
  `Degraded(rows, data)`; age (`freshness_ms` + time since served) > 30 s (10 s workspaces) →
  `Stale`; missing `freshness_ms` → maximally stale; `503`/`dial_dev_unavailable` → `Error(canRetry)`;
  401/403 → `Error(canRetry = false)`; offline → `Offline(0)` (owner actions are never queued;
  only the read refresh re-runs); a failure or offline phone with a last good projection keeps
  it as `Stale` with its true age; a body with no `projection_revision` is refused.

## Proof

`DialDevEnvelopeTest` (16), `DialDevModelsTest` home cases; V6 sheet
`dev-control-centre/work_devprojectproject_seven_states.png` (VAN-DEV-011).

## Must not

Call DIAL directly; hold a DIAL address, port or credential in Android; invent a count.

## Evidence recorded at implementation (container run, 2026-09-24)

| Instrument | Baseline (`be49e8e`) | After this unit group | Command |
|---|---|---|---|
| `android/verification` pure-JVM tests | 100 classes · 915 tests · 0 failed | 104 classes · 977 tests · 0 failed | `cd android/verification && gradle test` |
| `VanNavModelTest` (V1) | 16 tests | 23 tests | same run |
| `:visual-preview:test` (standalone harness, see below) | 5 classes · 24 tests · 0 failed | 6 classes · 28 tests · 0 failed | `gradle :visual-preview:test` |
| `tests/contracts` (pytest) | 527 passed · 3 skipped · 1 instrument failure¹ | 528 passed · 3 skipped | `python -m pytest tests/contracts` |
| `tools/audit/android_design_lint.py --baseline …` (V2) | 179 violations, all in baseline | 179 violations, all in baseline; 0 in new files | same |

¹ The baseline was run from a `git archive` export, which is not a git checkout;
`test_debug_signing_identity.py::test_no_signing_key_is_committed_to_this_repository` needs one.
That is the instrument, not the code; on the real checkout the suite passes.

Gates broken on purpose to prove they bite (each reverted): a completion candidate captioned
"Passed" → 5 tests fail; dev routes parented to Home → 1 fails; stale threshold ignored → 3 fail;
forwarder's `APPLIED` trusted on 202 → 1 fails; action built with no revision → 1 fails; a §4
`when` branch deleted → compile error "'when' expression must be exhaustive".

**Not run here, and not claimed:** `./gradlew :app:testDebugUnitTest :app:assembleDebug
:app:lintDebug` and the in-tree `./gradlew :visual-preview:*`. The Android Gradle Plugin and SDK
come from `dl.google.com`, which this container's egress proxy refuses (`CONNECT tunnel failed,
response 403`), so the app module cannot be configured. Substitute evidence, stated as such:
(a) the pure half compiles and runs in `android/verification`; (b) every new Compose file under
`command/dev/**` plus `design/**`, `dialdev/**` and `VanRoute.kt` compiles (Kotlin 1.9.24 + Compose
compiler 1.5.14) against Compose Multiplatform desktop 1.6.11 with minimal Android/navigation stubs
in a local-only harness, which was shown to fail on an induced type error and an induced
`@Composable`-context error; (c) `visual-preview` built and tested through a standalone settings
file that includes only that module. CI's `android-and-visual-evidence` job is the real gate.

```yaml
owner_signature_status: PENDING
owner_signature_evidence_ref: null
implemented_by: agent (W5, Claude) — an agent may not sign this record
```
