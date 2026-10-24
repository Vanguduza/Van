# Current independent review submission — 22 October 2026

The owner transferred execution from Opus to Codex. This submission issues no independent admission, owner signature, F15, backend-complete gate or product qualification.

Pin the full head of `ccr-9e07e1af-8mgz1p`, draft PR #105, before reviewing. The recovered checkpoint was `2a10b7884b9bcf214395d5c15815ab6d96f56845`; the applied maintenance baseline is `461186efbc7f8318468a81187eeb6e46c9a9dd41`. Consolidation baseline `b02075f327ea8180ab6d269eba358cf8c5479878` and the original package delivery remain unchanged.

The reference package tree is `ac0226a22a95f51642cfeb37b3709b40f7cacf10`; archive SHA-256 is `6c7c7c1cb4fbd4748c0d63ceb2add9bd460778b66fb3b2302e16de09ac3a57a8`. Its status is a reviewed proposal pending native identity and independent admission. "Admitted" in older tooling variable names means this frozen input path, not evidence that native admission occurred.

## Evidence to review

Use `tools/rebuild/requirements.lock` in an isolated environment and run `python -m pytest -q tests/rebuild`. Run `python tools/rebuild/manifest.py check` against the exact review commit; the manifest hashes all current rebuild evidence, tools and tests. The reviewer independently pins its containing commit.

- PRE-001's frozen-baseline inventory, 116 symbol dispositions, 34 overlap rows, 2,131 file classifications and ref dispositions remain in `../pre001/`. Execute its checker/selftests and review the new maintenance commits as a separate source delta.
- All 324 requirement dossiers remain author-prepared pending independent challenge. The semantic reviews, owner-decision register and obligations remain applicable except for explicitly corrected findings below.
- AP-001 alone remains the previously verified 1,624-identity proposal, digest `8eb76af51c41260c0e86ab4201a75339126367126ab3ada806ee0d2d89e10e49`.
- AP-002 alone is verified at 1,618 identities, digest `eb88ef3a005e21a34ad49e1248beaf50c5d65d1b99897fd47f39eb2ef54becc9`. AP-001 plus AP-002 is verified at 1,632, digest `f9e2bf7b7fb72c70ab4526c4bbdf28cb4efe6323c28bfe158c1ebb46a1a67b49`. Each passes all ten package checks; thirteen preservation regressions rederive receipts and reject induced changes to old tests, new oracles, units, lineage and signatures. Full proposed oracles survive in the generated amendments. Read `../pre002/AP-002/AP-002_REVIEW.md`. Neither amendment is admitted.
- Forecast provenance is resolved: `python tools/rebuild/forecast_provenance.py check` reproduces all 90 requirement and 48 packet hashes from the bundled original records. The recipe uses sorted JSON keys, ensure_ascii=False, default separators, UTF-8 and no newline. Original source and recorded digests are unchanged. Six induced corruption classes are rejected. `FORECAST_PROVENANCE.json` and regenerated `PRODUCT_TRUTH_TRACE_REVIEW.json` replace the previous unverifiable-hash finding.
- Local maintenance evidence is in `../receipts/BUILD_VALIDATION_20261022.json`: 1,273 JVM tests, 195 Android app unit tests, APK/instrumentation APK assembly and lint with zero Error/Fatal. The regex fixes reproduce host ICU failures before correction. Debug Rive sampling now uses fixed animation time and preserves visibility thresholds. Hosted runtime evidence now passes at head `637eaf96` / tree-identical test merge `b2ed4481`: 14 passed, zero failed, four full/production-mode skips; Character Forge core gate PASS. See `INSTRUMENTATION_637eaf96.json`.
- `../ci/ASR_ARCHIVE_REQUALIFICATION_20261022.json` records another upstream archive repack, verification of its official digest, unchanged selected model bytes, and the durable acquisition correction using immutable model-file URLs. The compiled 45-file voice manifest is unchanged.
- `F15_LIFECYCLE_REVIEW_20261022.md` traces DDS `204f2f3b4e19243fb4593d4e7f48dfa332cbef22`. The runtime source-contract baseline remains DDS `64d6b7158c723b7700e5b53175ea8048d4e92d00`; neither is a deployed-version attestation.

## Remaining decisions and native requirements

1. Review/admit the selected AP-001/AP-002 candidate and independently challenge the full requirement scope. New identities remain NOT_RUN.
2. Review the 14 proposed owner-facing Product Truth mappings and the backend-first atom covering 18 clauses. Clause-text hashes are content identifiers, not independent owner provenance. Record genuine citations/approval rather than manufacturing links.
3. Resolve the applicable 18 owner decisions, affecting 49 requirements (56 direct pairs). START, exit and consequential activation gates differ; do not impose activation decisions prematurely or invent financial/provider/retention values.
4. Obtain native registry/pack readback. The certifier compares the native registry and native pack IDs; a package UUID and slug may be valid separate namespaces. A mismatch has not been observed.
5. Obtain valid scope-lock approval. The existing source/memory authorization consumer does not itself verify approval of a scope lock. Identify the existing supported consumer or admit an explicit adapter binding the lock/package/baseline/project and owner approval purpose.
6. Complete #94's one-time trusted-base adoption, reviewed intake and source admission. Branch-local ledger GREEN does not replace the trusted-base check. No merge or bypass was performed.
7. Supply the DDS-only Actions read credential. Both REST and the supplied gh authentication return HTTP 403 for secret administration; no credential was created or broadened, and private DDS source was not copied into Van.
8. Review the recorded hosted instrumentation outcome and its four explicit core-mode skips. Full/production rig coverage, owner signing/provisioning, hosted-service qualification and S24 Artemis acceptance remain separate.
9. After the baseline/package and preparation findings are settled, issue F15 through the eligible native process. Refresh evidence/envelopes after integration advances the registered baseline; do not keep a stale checkout as a substitute for revalidation.

The original planned acceptance registry remains NOT_RUN, as do additions in the candidate packages. No live host, provider, financial, native device or owner-acceptance effect occurred in this continuation.

The complete trusted-base intake candidate is `MAIN_AUTHORIZATION_INTAKE_CURRENT.json` (45 records, original 39 unchanged plus six continuation records). Recompute it against the actual protected base after bootstrap.

Mutation continuation at `5d6372fd`: all 36 original input findings are resolved, all 374 case identities remain (380 edits), and all 32 retargeted cases are assertion-detected after valid controls. Initial survivors, missing dependencies and an invalid Kotlin replacement remain recorded as failed attempts. The shared runner rejects pytest collection and Gradle compilation/setup failures. See `ci/MUTATION_RECONCILIATION.md`, its exact mapping and per-component receipts. Thirty-five focused controls and 52 rebuild regressions pass. Full corpus run `39721114929` is in progress; its browser shard passed 26/26, with no complete corpus score claimed. Native admission, owner decisions and release/handset requirements remain unchanged.


Latest source evidence: c2a27848 / run39725953372, exact merge 9ae436ab / tree42e4a6b0.
All 374 legacy mutations now pass with valid controls and once-only identity
coverage; Android emulator 16 passed / 0 failed / 4 explicit core skips; Android
build/lint, Character Forge core and rebuild regressions pass. The source corpus
gap is closed. New mission-creation race/error guards pass 100 related local
backend tests; 55 connection/policy/signing-refusal checks passed. No formal
Rev1.18 unit or native/handset acceptance is inferred. See the current checkpoint
and exact receipts. Original failed scores/attempts and the immutable blueprint
remain preserved. Trusted-main and DDS credential jobs still fail their genuine
prerequisites; nothing was bypassed.
