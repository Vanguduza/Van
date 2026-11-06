# Floating assistant: inherited-source repair continuation — 4 November 2026

Status: **candidate source only; not full-unit, release, native runtime or handset acceptance**.

This continues the exact existing floating batch on `fcbb6abafa546e5f7a3cc7ed885026e4487e5bf5` and the original FE-005 / VAN-NX-006 / LAC266–270 obligations. It is not a replacement blueprint, a new UI design, or permission to skip BG-001, asset admission, independent evidence, signing, deployment or S24 acceptance. The original 131-unit scope and dependencies remain required.

## Source implemented

The retained first batch repairs measured rectangular placement, safe insets and keyboard overlap; pointer-based dismissal; fractional dragging; cancellable docking; startup/teardown safety; shared active-time animation; live reduced-motion observation; and Rive pause/resume and silhouette cleanup. Candidate B artwork, native aura, state/action/input/trigger codes and dependency versions are unchanged.

The continuation adds a shared, reference-counted application-context observer for actual battery, power-save, thermal, memory and backdrop-blur changes. It delegates every budget decision to the existing VanResourceEnvelope and VanEffectPolicy. Registration cleanup and late-callback guards keep this event-driven: there is no new resource polling loop. Native backdrop blur now follows the resource ceiling rather than only the initial device reading.

Actual view-display refresh changes feed an active-clock cadence sampler. Sustained cadence pressure reduces existing effects; recovery cannot exceed the current resource ceiling. Pause/resume and refresh-rate changes discard incomparable samples. These are **animation callback cadence measurements, not GPU render times, presentation latency, Android JankStats or handset performance qualification**.

Review reproduced a prior-batch architecture regression: the service had grown to 789 lines and failed the unchanged 450-line architecture contract. The source now separates native interaction, materialized-node gesture coordinates and workboard presentation into bounded components. The service remains the owner of its foreground-service/window lifecycle and is 436 lines. The original architecture assertions were not relaxed.

## Actual evidence

The combined pure-source JVM suite passed **110 tests with zero failures and zero skips**, including 20 additional live-effect/cadence regressions in this continuation. These are not additive to the preceding 90-test result. All 25 tested production/test input hashes remained identical after native adapter refactoring. The four original overlay architecture test functions also pass unchanged.

A bounded native compilation passed for **55 actual production files**, producing 384 class files with the project's Kotlin1.9.24, Compose1.5.14, Android SDK36 and actual configured Android/Rive dependency classpath. This uses real production dependencies, not interface or platform stubs. Its source hashes were unchanged. It does **not** cover the full application service/product binding or establish APK, runtime or device acceptance.

Whole-app validation remains unproven. Original attempts retain the missing BuildTools35 selection, offline dependency-cache misses, JVM heap exhaustion and subsequent bounded full-Gradle/direct-compiler deadlines. Selecting the already installed correct SDK and normally resolving the existing dependency pins fixed those specific setup problems; they did not make the timed-out compilation a pass. The existing Commander 512MiB soft/768MiB hard resource policy was never changed or escaped.

The clone's original shallow ancestry prevented the required Project Truth baseline from being resolved. The exact existing history was hydrated, making `4fd466dec3910ed5de614bfbf95887ad619df5ca` an actual ancestor without changing it. Subsequent full-history verification timed out without a terminal GREEN result. Normal source hooks remain installed; no public push or release readiness is inferred from a timeout.

Original per-attempt logs, receipts, JUnit output and exact checksums are in `receipts/floating-20261104-r2/`. Historical failures remain failures. The prior delivery ZIP and patch are preserved unchanged in the original VM workspace; this evidence does not overwrite that checkpoint.

## Continuation and remaining work

Complete exact whole-app compilation and normal required-baseline verification through the original integration owner before publication. Then bind and run actual Android instrumentation, visibility/reduced-motion/keyboard/docking tests, Rive rendering and measured handset frame/power tests. A source commit or a component compile is not independent qualification.

The final articulated Candidate B rig, reviewed M1 semantic vectors, complete original fourteen action paths, expanded gesture/micro-motion catalogue, production attention targets, gesture arbitration and playback-clock speech synchronization remain unfinished. No third-party gesture asset or mechanics prototype has been promoted to production `van.riv`. Candidate B's existing prototype remains explicitly non-canonical until its original artwork/rig/animation/device/owner gates are met.
