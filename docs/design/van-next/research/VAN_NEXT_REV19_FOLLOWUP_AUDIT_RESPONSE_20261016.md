# Response to the Rev 1.9 follow-up audit

**Audit archive:** `VAN_NEXT_REV19_FOLLOWUP_AUDIT_20261016.zip`, review ID `VAN-NEXT-REV19-FOLLOWUP-20261016`, disposition `CONDITIONAL_PREFERRED_FREEZE_CORRECTIONS_REQUIRED`.

**Method:** each finding was checked against this repository (the `ccr-8f1201e9-w1xm0r` branch) and, for the gate findings, against the governing standard PRD-DDP-R2 in `Vanguduza/dial-development-system` (§17–§19, last changed `e250cdf`).

**Result:** all nine findings were confirmed. The owner approved F1–F4 (OD-28…OD-31), and Rev 1.9a applies them.

| Finding | Verified how | Result | Rev 1.9a |
|---|---|---|---|
| V19-A01 BLOCKER: F13/F15 conflate planning with production proof | §17 against PRD-DDP-R2 §17 ("runtime/external qualification matrix") and §19 ("Normal implementation may start only with status FORENSIC_BUILD_READY … does not claim live production readiness") | **Confirmed.** Rev 1.9's F13 demanded a signed APK and owner-device proof, which cannot exist before development, and the plan never required F15 | U1: F13 redefined as the predevelopment matrix, with actual proofs moved to the §17.1 post-implementation states; F15 issued by an independent verifier at DU-31 |
| V19-A02 BLOCKER: code-bearing PKT-001 before the 171/115 mapping and F15 | Plan §4 order; §12.5 steps 4–6 merge code | **Confirmed** | U2: DU-00a (read-only) → DU-01 → DU-31 (F15) → DU-00b. New generator rule `CODE_BEFORE_F15`, proven by self-test |
| V19-A03 HIGH: cross-signal consumer before its producer | Ancestor walk: DU-10d was not upstream of DU-14d, nor the reverse | **Confirmed.** The validator only checked reachability to qualification, not requirement-level producers | U3: VAN-NX-065 moved to DU-10d with `N --> JD`; requirements declare `Needs:`; new rule `REQ_NEEDS_NOT_UPSTREAM`, proven by self-test |
| V19-A04 HIGH: "Cancelled, not filled" survives as a test | grep §18.2 | **Confirmed**; missed in Rev 1.9 | U4: race-interleaving tests |
| V19-A05 HIGH: news test contradicts D4/D5 | §18.2 against §8.5 | **Confirmed** | U5: tests split by path and by who manages the position |
| V19-A06 MEDIUM: stop guarantee stronger than the recovery path | R1 change-log row against §7.4.3 | **Confirmed** (R1 wording and the "more than seconds" promise) | U6: request invariant plus three tracked protection states |
| V19-A07 MEDIUM: winning-only for automatic trades | §7.4.6 against OD-10 ("winning auto trade") | **Confirmed** | U7: winning at approval and at submission, for both origins |
| V19-A08 EVIDENCE: executable inputs not supplied | `git ls-tree origin/main -- docs/design/van-next` → 0 files; the working branch has them | **Accurate.** The work lives on the working branch, not `main` | U8: hash-pinned evidence pack in `evidence/`, bound to a commit, with receipts |
| V19-A09 LOW: REA status wording | §16.2 | **Confirmed** | U9 |

**Found while applying the fixes.**
- The generator's DAG parser accepted only letter node keys. The new key `A0` (DU-00a) was silently dropped from the graph. The validator caught it straight away: DU-00a showed up as an unknown unit in four findings. The pattern was widened to `[A-Z][A-Z0-9]{0,2}`.
- The self-test's own guard then caught a case whose anchor text no longer existed (`self-test case 'cycle' did not change its input`), so that case could not pass silently. Its anchor was updated.
- The evidence builder's refusal gate ("inputs must equal the committed HEAD") was tested by modifying an input on purpose, and it **failed**: the pack was built anyway. The cause was git pathspecs resolved against the wrong directory, so nothing ever looked modified. After the fix, the gate refuses both a modified input and a deleted one (exit 2), and the pack was rebuilt from clean inputs.

**Evidence pack (U8).**
- Pack: `evidence/VAN_NEXT_PREDEV_EVIDENCE_PACK_REV1_9A.zip`, bound to source commit `8ac8992`, zip SHA-256 `3dfb6518c4617a8bfef8a63ef143dfa413bb8e4bbb725bd170092df170b45648`.
- Build: deterministic, byte-identical on rebuild.
- Rerun: unzipped into an empty directory, every input matched its manifest hash, and all five commands reproduced their receipts exactly (four exit 0; the run on the pack's original machines exits 1 with its 69 findings, as expected).

**Still owner-only:** signing the decision record (OQ-05, now the start gate of the read-only PKT-001) and decisions B1–B6. **Still independent-only:** the F15 certificate at DU-31. No assistant or worker may self-issue it.
