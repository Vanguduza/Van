# VAN Next — Deterministic Development Plan, Rev 1

**Status:** `DRAFT / AWAITING_OWNER_APPROVAL`. No packet starts until the owner approves this plan.
**Derived from:** `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9_20261015.md` §16.1, §16.2, §19.1 and `VAN_NEXT_OWNER_DECISIONS_REV1.md` (open questions).

| Input | SHA-256 (full file bytes) |
|---|---|
| `docs/design/van-next/VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9_20261015.md` | `af8ca74906e3f5a7f4958b593e28e78767ac4024768588e654495c7d8893e772` |
| `docs/design/van-next/VAN_NEXT_OWNER_DECISIONS_REV1.md` | `61909b8adef17d596d2bd91015991eea48a72861d46825dcdf3b7b1b8c3de81f` |
| `docs/design/van-next/plan/generate_plan.py` | `b99e8c392d690b31bd2e513b70d33cf3f5f01c3055a132c2ea37fbb269988795` |

Aggregate input digest `78033ecdfdb1bb7fd5dba71c63625166cb902c2b27f6765b173cdb3851c44b1f` = SHA-256 of the blueprint bytes, one newline byte, the decision-record bytes and the generator bytes. `PLAN_INPUT_PROVENANCE.json` records these values and the hashes of the generated plan.

**Generator:** `plan/generate_plan.py`. Re-running it on the same inputs gives byte-identical output. `--check` validates the inputs **and** fails if this file is stale; `--selftest` proves each check catches a deliberately broken input.

## 1. Rules

1. **One packet at a time, in sequence order.** A packet starts only when its entry gate holds; the next packet starts only when the current one has exited. Parallel work is allowed only when the owner assigns another worker, and then only to packets of the same wave (§6) whose dependencies have exited.
2. **Entry gate (every packet):** all dependency packets exited; the packet's acceptance contract written and owner-approved (fields of blueprint §16.4, including exact source SHA, files, negative cases, acceptance commands, rollback); every open question that blocks its start resolved.
3. **Exit gate (every packet):** the contract's acceptance commands pass on a recorded commit; each new gate is broken deliberately and seen to fail before it is trusted; the parity checker (from PKT-001 onward) shows no `FEATURE_LOSS`; independent review recorded; artifact state at least `REPOSITORY_PROVEN` (§17.1). Device, live and owner-acceptance states are reached in P4–P5 and are never claimed earlier.
4. **No code outside a packet.** Work not in an open packet is not done. A discovery that changes scope stops the packet and goes to the owner as a blueprint amendment; the plan is regenerated.
5. **Order key** (deterministic): phase (§19.1) → dependency depth in the §16.2 DAG → lane order of §16.3 → DU number. P2 builds the five §19.1 vertical slices as milestone M1 of each DU in a slice and of every DU those slices depend on; P3 completes each DU (M2), then the remaining DUs in full.
6. **Owner-only steps** are listed per packet and are never assumed: signatures, open-question answers, `OWNER_RETIRE` dispositions, live promotion.

## 2. Validation of the blueprint inputs

- Development Units in the DAG: 49; solid dependency edges: 89; non-blocking (dotted) edges: 2.
- Requirements parsed: 69; open questions parsed: 18.
- Findings: none. The DAG is acyclic; every requirement and every open question maps to a DU in the DAG; every DU has a lane; no DU depends on a later phase; every build unit has a dependency path to DU-25, DU-26 and DU-MR.
- DUs with no requirement row (kept, flagged for the freeze list): none.
- DU-27 is not a packet: REA research (static) done under OD-15/16/17. Its admission record is VAN-NX-026, carried by DU-01; its findings are inputs to the DU-10 and DU-29 contracts.

## 3. Plan-level choices awaiting owner approval

These are the only inputs not read from the blueprint.

| DU | Phase | Lane |
|---|---|---|
| DU-00 | P0 | Consolidation |
| DU-01 | P0 | Foundation |
| DU-02 | P1 | Foundation |
| DU-03 | P1 | Foundation |
| DU-04 | P1 | Foundation |
| DU-05 | P2 (M1, if in a slice closure) / P3 | Orb/Floating |
| DU-06 | P2 (M1, if in a slice closure) / P3 | Orb/Floating |
| DU-07 | P2 (M1, if in a slice closure) / P3 | Orb/Floating |
| DU-08 | P2 (M1, if in a slice closure) / P3 | Continuity |
| DU-09 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-10 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-10b | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-10c | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-10d | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-11 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-12 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-12a | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-12b | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-13 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-14a | P2 (M1, if in a slice closure) / P3 | News |
| DU-14b | P2 (M1, if in a slice closure) / P3 | News |
| DU-14c | P2 (M1, if in a slice closure) / P3 | News |
| DU-14d | P2 (M1, if in a slice closure) / P3 | News |
| DU-14e | P2 (M1, if in a slice closure) / P3 | News |
| DU-14f | P2 (M1, if in a slice closure) / P3 | News |
| DU-15 | P2 (M1, if in a slice closure) / P3 | Work Graph |
| DU-16 | P2 (M1, if in a slice closure) / P3 | Work Graph |
| DU-17 | P2 (M1, if in a slice closure) / P3 | Work Graph |
| DU-18 | P2 (M1, if in a slice closure) / P3 | Work Graph |
| DU-19 | P2 (M1, if in a slice closure) / P3 | Continuity |
| DU-20 | P2 (M1, if in a slice closure) / P3 | Continuity |
| DU-21 | P2 (M1, if in a slice closure) / P3 | Continuity |
| DU-22 | P4 | Qualification |
| DU-23 | P4 | Qualification |
| DU-24 | P1 | Foundation |
| DU-25 | P4 | Qualification |
| DU-26 | P4 | Qualification |
| DU-28 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-28b | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-28c | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-28d | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-28e | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-29 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-29a | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-29b | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-29c | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-30 | P2 (M1, if in a slice closure) / P3 | Trading |
| DU-MR | P5 | Qualification |

| Vertical slice (§19.1 P2) | DUs |
|---|---|
| S1 Home orb → Quick Hub → Attention | DU-05, DU-06, DU-08 |
| S2 Trading Home → Chart → manual trade review → Position (demo account) | DU-09, DU-10, DU-28, DU-11 |
| S3 Work → Flow → Task | DU-15, DU-16 |
| S4 Intelligence → News → Instrument | DU-13, DU-14d |
| S5 Floating VAN → Voice / Work | DU-07, DU-21 |

## 4. Packet sequence

| Packet | DU | Title | Phase | Milestone | Lane | Depends on | Requirements | Owner decisions (start / live / exit) |
|---|---|---|---|---|---|---|---|---|
| PKT-001 | DU-00 | Consolidation, Feature Ledger, parity oracle | P0 | FULL | Consolidation | — | VAN-NX-028 | OQ-05 / — |
| PKT-002 | DU-01 | Product Truth and preservation reconciliation | P0 | FULL | Foundation | PKT-001 | VAN-NX-026, VAN-NX-053 | — / — |
| PKT-003 | DU-02 | Visual golden authority + labels | P1 | FULL | Foundation | PKT-002 | VAN-NX-001, VAN-NX-030 | — / — |
| PKT-004 | DU-24 | Anti-loss checker + module isolation | P1 | FULL | Foundation | PKT-002 | VAN-NX-023, VAN-NX-029, VAN-NX-039 | — / — |
| PKT-005 | DU-03 | Clean theme and component system | P1 | FULL | Foundation | PKT-003, PKT-004 | VAN-NX-002 | — / — |
| PKT-006 | DU-04 | Adaptive app shell | P1 | FULL | Foundation | PKT-004, PKT-005 | VAN-NX-003 | — / — |
| PKT-007 | DU-29 | Account lifecycle, linking, edit, delete | P2 | M1 | Trading | PKT-002 | VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-056, VAN-NX-057, VAN-NX-064 | OQ-15, OQ-18 / — |
| PKT-008 | DU-30 | Trading modes | P2 | M1 | Trading | PKT-002 | VAN-NX-058 | — / OQ-20 |
| PKT-009 | DU-14a | Multi-source feeds + health | P2 | M1 | News | PKT-002 | VAN-NX-013, VAN-NX-038 | OQ-06, OQ-11 / — |
| PKT-010 | DU-29a | Funding ledger + flow-adjusted risk | P2 | M1 | Trading | PKT-007 | VAN-NX-051, VAN-NX-059 | OQ-16 / — |
| PKT-011 | DU-14b | Story analysis + headline episodes + history profiles | P2 | M1 | News | PKT-009 | VAN-NX-013, VAN-NX-037 | — / — |
| PKT-012 | DU-28 | Manual trading backend | P2 | M1 | Trading | PKT-002, PKT-010 | VAN-NX-027 | OQ-02, OQ-07 / OQ-01, OQ-03 |
| PKT-013 | DU-14c | Decision paths D1-D7, shadow then live | P2 | M1 | News | PKT-011 | VAN-NX-032 | OQ-09 / OQ-08 |
| PKT-014 | DU-05 | Orb semantics and rendering | P2 | M1 | Orb/Floating | PKT-006 | VAN-NX-004 | — / — |
| PKT-015 | DU-07 | Floating VAN remodel | P2 | M1 | Orb/Floating | PKT-006 | VAN-NX-006 | — / — |
| PKT-016 | DU-12a | Shared market projection | P2 | M1 | Trading | PKT-006 | VAN-NX-040 | — / — |
| PKT-017 | DU-28b | Adds, Hand to VAN, take back | P2 | M1 | Trading | PKT-012 | VAN-NX-031 | — / — |
| PKT-018 | DU-28e | Order vocabulary + venue capabilities | P2 | M1 | Trading | PKT-012 | VAN-NX-045 | — / — |
| PKT-019 | DU-15 | Project data adapter | P2 | M1 | Work Graph | PKT-006 | VAN-NX-014 | — / — |
| PKT-020 | DU-08 | Attention/Approvals | P2 | M1 | Continuity | PKT-006 | VAN-NX-007 | — / — |
| PKT-021 | DU-21 | Browser/Voice/ARTEMIS | P2 | M1 | Continuity | PKT-006 | VAN-NX-020, VAN-NX-069 | — / — |
| PKT-022 | DU-09 | Trading Home | P2 | M1 | Trading | PKT-006, PKT-008, PKT-016 | VAN-NX-008 | — / — |
| PKT-023 | DU-16 | Spatial task graph | P2 | M1 | Work Graph | PKT-019 | VAN-NX-015 | — / — |
| PKT-024 | DU-10 | Rich Chart | P2 | M1 | Trading | PKT-022 | VAN-NX-009, VAN-NX-041, VAN-NX-042 | OQ-14 / — |
| PKT-025 | DU-13 | Analyst | P2 | M1 | Trading | PKT-022 | VAN-NX-012 | — / — |
| PKT-026 | DU-11 | Positions/Orders/Protection | P2 | M1 | Trading | PKT-012, PKT-017, PKT-018, PKT-024 | VAN-NX-010, VAN-NX-061, VAN-NX-062 | — / — |
| PKT-027 | DU-14d | News briefs + News UI | P2 | M1 | News | PKT-011, PKT-013, PKT-025 | VAN-NX-013, VAN-NX-065 | — / — |
| PKT-028 | DU-06 | Compact Quick Hub | P2 | M1 | Orb/Floating | PKT-014, PKT-019, PKT-020, PKT-022, PKT-026 | VAN-NX-005, VAN-NX-063 | — / — |
| PKT-029 | DU-29 | Account lifecycle, linking, edit, delete | P3 | M2 | Trading | PKT-002, PKT-007 | VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-056, VAN-NX-057, VAN-NX-064 | OQ-15, OQ-18 / — |
| PKT-030 | DU-30 | Trading modes | P3 | M2 | Trading | PKT-002, PKT-008 | VAN-NX-058 | — / OQ-20 |
| PKT-031 | DU-14a | Multi-source feeds + health | P3 | M2 | News | PKT-002, PKT-009 | VAN-NX-013, VAN-NX-038 | OQ-06, OQ-11 / — |
| PKT-032 | DU-29a | Funding ledger + flow-adjusted risk | P3 | M2 | Trading | PKT-010, PKT-029 | VAN-NX-051, VAN-NX-059 | OQ-16 / — |
| PKT-033 | DU-14b | Story analysis + headline episodes + history profiles | P3 | M2 | News | PKT-011, PKT-031 | VAN-NX-013, VAN-NX-037 | — / — |
| PKT-034 | DU-28 | Manual trading backend | P3 | M2 | Trading | PKT-002, PKT-012, PKT-032 | VAN-NX-027 | OQ-02, OQ-07 / OQ-01, OQ-03 |
| PKT-035 | DU-29c | Funds orchestration | P3 | FULL | Trading | PKT-029, PKT-032 | VAN-NX-055 | OQ-19 / — |
| PKT-036 | DU-14c | Decision paths D1-D7, shadow then live | P3 | M2 | News | PKT-013, PKT-033 | VAN-NX-032 | OQ-09 / OQ-08 |
| PKT-037 | DU-14f | Prediction-market expectations | P3 | FULL | News | PKT-033 | VAN-NX-036 | — / — |
| PKT-038 | DU-05 | Orb semantics and rendering | P3 | M2 | Orb/Floating | PKT-006, PKT-014 | VAN-NX-004 | — / — |
| PKT-039 | DU-07 | Floating VAN remodel | P3 | M2 | Orb/Floating | PKT-006, PKT-015 | VAN-NX-006 | — / — |
| PKT-040 | DU-12a | Shared market projection | P3 | M2 | Trading | PKT-006, PKT-016 | VAN-NX-040 | — / — |
| PKT-041 | DU-28b | Adds, Hand to VAN, take back | P3 | M2 | Trading | PKT-017, PKT-034 | VAN-NX-031 | — / — |
| PKT-042 | DU-28c | Behaviour diagnostics | P3 | FULL | Trading | PKT-034 | VAN-NX-034 | OQ-13 / — |
| PKT-043 | DU-28e | Order vocabulary + venue capabilities | P3 | M2 | Trading | PKT-018, PKT-034 | VAN-NX-045 | — / — |
| PKT-044 | DU-14e | Live news trading bundle | P3 | FULL | News | PKT-034, PKT-036, PKT-037 | VAN-NX-033 | OQ-11, OQ-12 / — |
| PKT-045 | DU-15 | Project data adapter | P3 | M2 | Work Graph | PKT-006, PKT-019 | VAN-NX-014 | — / — |
| PKT-046 | DU-08 | Attention/Approvals | P3 | M2 | Continuity | PKT-006, PKT-020 | VAN-NX-007 | — / — |
| PKT-047 | DU-19 | Memory/Automation continuity | P3 | FULL | Continuity | PKT-006 | VAN-NX-018, VAN-NX-066, VAN-NX-067, VAN-NX-068 | — / — |
| PKT-048 | DU-20 | Settings/Connected | P3 | FULL | Continuity | PKT-006 | VAN-NX-019 | — / — |
| PKT-049 | DU-21 | Browser/Voice/ARTEMIS | P3 | M2 | Continuity | PKT-006, PKT-021 | VAN-NX-020, VAN-NX-069 | — / — |
| PKT-050 | DU-09 | Trading Home | P3 | M2 | Trading | PKT-006, PKT-022, PKT-030, PKT-040 | VAN-NX-008 | — / — |
| PKT-051 | DU-12b | Alerts, watchlists, screener | P3 | FULL | Trading | PKT-040 | VAN-NX-047 | — / — |
| PKT-052 | DU-28d | Pattern extraction to candidates | P3 | FULL | Trading | PKT-042 | VAN-NX-035 | — / — |
| PKT-053 | DU-29b | Portfolio, health, statements | P3 | FULL | Trading | PKT-029, PKT-040 | VAN-NX-052 | — / — |
| PKT-054 | DU-16 | Spatial task graph | P3 | M2 | Work Graph | PKT-023, PKT-045 | VAN-NX-015 | — / — |
| PKT-055 | DU-18 | Muse qualified interaction | P3 | FULL | Work Graph | PKT-045 | VAN-NX-017 | — / — |
| PKT-056 | DU-10 | Rich Chart | P3 | M2 | Trading | PKT-024, PKT-050 | VAN-NX-009, VAN-NX-041, VAN-NX-042 | OQ-14 / — |
| PKT-057 | DU-12 | Markets and Watchlists | P3 | FULL | Trading | PKT-040, PKT-050 | VAN-NX-011 | — / — |
| PKT-058 | DU-13 | Analyst | P3 | M2 | Trading | PKT-025, PKT-050 | VAN-NX-012 | — / — |
| PKT-059 | DU-17 | Agent/Handoff flow | P3 | FULL | Work Graph | PKT-054 | VAN-NX-016 | — / — |
| PKT-060 | DU-10b | Indicators, drawings, workspaces | P3 | FULL | Trading | PKT-056 | VAN-NX-043 | — / — |
| PKT-061 | DU-10c | Replay sandbox | P3 | FULL | Trading | PKT-056 | VAN-NX-044 | OQ-17 / — |
| PKT-062 | DU-11 | Positions/Orders/Protection | P3 | M2 | Trading | PKT-026, PKT-034, PKT-041, PKT-043, PKT-056 | VAN-NX-010, VAN-NX-061, VAN-NX-062 | — / — |
| PKT-063 | DU-14d | News briefs + News UI | P3 | M2 | News | PKT-027, PKT-033, PKT-036, PKT-058 | VAN-NX-013, VAN-NX-065 | — / — |
| PKT-064 | DU-06 | Compact Quick Hub | P3 | M2 | Orb/Floating | PKT-028, PKT-038, PKT-045, PKT-046, PKT-050, PKT-062 | VAN-NX-005, VAN-NX-063 | — / — |
| PKT-065 | DU-10d | Chart observations | P3 | FULL | Trading | PKT-060 | VAN-NX-046 | — / — |
| PKT-066 | DU-22 | Cross-domain privacy/failure | P4 | FULL | Qualification | PKT-039, PKT-059, PKT-062, PKT-063, PKT-064 | VAN-NX-021 | — / — |
| PKT-067 | DU-23 | Performance and accessibility | P4 | FULL | Qualification | PKT-066 | VAN-NX-022, VAN-NX-060 | — / — |
| PKT-068 | DU-25 | Integrated verification/Zuul | P4 | FULL | Qualification | PKT-004, PKT-030, PKT-032, PKT-034, PKT-035, PKT-036, PKT-044, PKT-046, PKT-047, PKT-048, PKT-049, PKT-051, PKT-052, PKT-053, PKT-055, PKT-057, PKT-060, PKT-061, PKT-065, PKT-067 | VAN-NX-024 | — / — |
| PKT-069 | DU-26 | Physical S24 + owner acceptance | P4 | FULL | Qualification | PKT-068 | VAN-NX-025 | — / — |
| PKT-070 | DU-MR | Controlled migration/retirement | P5 | ROLLOUT | Qualification | PKT-069 | VAN-NX-054 | — / — |
| PKT-071 | DU-MR | Controlled migration/retirement | P6 | RETIREMENT | Qualification | PKT-069, PKT-070 | VAN-NX-054 | — / — |

## 5. Milestones

- **FULL:** Whole DU to its requirement acceptance.
- **M1:** Only what its §19.1 slice (or a dependent slice) needs, end to end on real permitted data; scope fixed in the packet contract.
- **M2:** Remainder of the DU to full requirement acceptance (its M1 already exited).
- **ROLLOUT:** §19.1 P5: signed APK under the admitted identity, feature flags, recovery on the owner's S24, tested rollback build.
- **RETIREMENT:** §19.1 P6: remove old frontend only after full parity and readback, in its own reviewable branch with negative tests.

## 6. Waves (what may run in parallel if the owner adds workers)

Within a phase, packets at the same DAG depth do not depend on each other.

| Phase | Depth | Packets |
|---|---|---|
| P0 | 0 | PKT-001 (DU-00) |
| P0 | 1 | PKT-002 (DU-01) |
| P1 | 2 | PKT-003 (DU-02), PKT-004 (DU-24) |
| P1 | 3 | PKT-005 (DU-03) |
| P1 | 4 | PKT-006 (DU-04) |
| P2 | 2 | PKT-007 (DU-29), PKT-008 (DU-30), PKT-009 (DU-14a) |
| P2 | 3 | PKT-010 (DU-29a), PKT-011 (DU-14b) |
| P2 | 4 | PKT-012 (DU-28), PKT-013 (DU-14c) |
| P2 | 5 | PKT-014 (DU-05), PKT-015 (DU-07), PKT-016 (DU-12a), PKT-017 (DU-28b), PKT-018 (DU-28e), PKT-019 (DU-15), PKT-020 (DU-08), PKT-021 (DU-21) |
| P2 | 6 | PKT-022 (DU-09), PKT-023 (DU-16) |
| P2 | 7 | PKT-024 (DU-10), PKT-025 (DU-13) |
| P2 | 8 | PKT-026 (DU-11), PKT-027 (DU-14d) |
| P2 | 9 | PKT-028 (DU-06) |
| P3 | 2 | PKT-029 (DU-29), PKT-030 (DU-30), PKT-031 (DU-14a) |
| P3 | 3 | PKT-032 (DU-29a), PKT-033 (DU-14b) |
| P3 | 4 | PKT-034 (DU-28), PKT-035 (DU-29c), PKT-036 (DU-14c), PKT-037 (DU-14f) |
| P3 | 5 | PKT-038 (DU-05), PKT-039 (DU-07), PKT-040 (DU-12a), PKT-041 (DU-28b), PKT-042 (DU-28c), PKT-043 (DU-28e), PKT-044 (DU-14e), PKT-045 (DU-15), PKT-046 (DU-08), PKT-047 (DU-19), PKT-048 (DU-20), PKT-049 (DU-21) |
| P3 | 6 | PKT-050 (DU-09), PKT-051 (DU-12b), PKT-052 (DU-28d), PKT-053 (DU-29b), PKT-054 (DU-16), PKT-055 (DU-18) |
| P3 | 7 | PKT-056 (DU-10), PKT-057 (DU-12), PKT-058 (DU-13), PKT-059 (DU-17) |
| P3 | 8 | PKT-060 (DU-10b), PKT-061 (DU-10c), PKT-062 (DU-11), PKT-063 (DU-14d) |
| P3 | 9 | PKT-064 (DU-06), PKT-065 (DU-10d) |
| P4 | 10 | PKT-066 (DU-22) |
| P4 | 11 | PKT-067 (DU-23) |
| P4 | 12 | PKT-068 (DU-25) |
| P4 | 13 | PKT-069 (DU-26) |
| P5 | 14 | PKT-070 (DU-MR) |
| P6 | 14 | PKT-071 (DU-MR) |

## 7. Open questions by packet

Generated from the decision record, so packet numbers here are always current. Freeze lists cite this section instead of copying packet numbers.

| Question | Gate | Packets |
|---|---|---|
| OQ-01 | live | PKT-012 (DU-28 M1), PKT-034 (DU-28 M2) |
| OQ-02 | start | PKT-012 (DU-28 M1), PKT-034 (DU-28 M2) |
| OQ-03 | live | PKT-012 (DU-28 M1), PKT-034 (DU-28 M2) |
| OQ-05 | start | PKT-001 (DU-00 FULL) |
| OQ-06 | start | PKT-009 (DU-14a M1), PKT-031 (DU-14a M2) |
| OQ-07 | start | PKT-012 (DU-28 M1), PKT-034 (DU-28 M2) |
| OQ-08 | live | PKT-013 (DU-14c M1), PKT-036 (DU-14c M2) |
| OQ-09 | start | PKT-013 (DU-14c M1), PKT-036 (DU-14c M2) |
| OQ-11 | start | PKT-009 (DU-14a M1), PKT-031 (DU-14a M2), PKT-044 (DU-14e FULL) |
| OQ-12 | start | PKT-044 (DU-14e FULL) |
| OQ-13 | start | PKT-042 (DU-28c FULL) |
| OQ-14 | start | PKT-024 (DU-10 M1), PKT-056 (DU-10 M2) |
| OQ-15 | start | PKT-007 (DU-29 M1), PKT-029 (DU-29 M2) |
| OQ-16 | start | PKT-010 (DU-29a M1), PKT-032 (DU-29a M2) |
| OQ-17 | start | PKT-061 (DU-10c FULL) |
| OQ-18 | start | PKT-007 (DU-29 M1), PKT-029 (DU-29 M2) |
| OQ-19 | start | PKT-035 (DU-29c FULL) |
| OQ-20 | live | PKT-008 (DU-30 M1), PKT-030 (DU-30 M2) |

## 8. Exit evidence by requirement

A DU's last packet exits only with every listed requirement's key acceptance (blueprint §16.1).

| Requirement | DU | Key acceptance |
|---|---|---|
| VAN-NX-001 | DU-02 | Screenshot/material owner acceptance |
| VAN-NX-002 | DU-03 | No old UI-theme imports |
| VAN-NX-003 | DU-04 | Old route IDs resolve |
| VAN-NX-004 | DU-05 | Priority, freshness and visual/voice tests |
| VAN-NX-005 | DU-06 | No effect on tap; compact device capture |
| VAN-NX-006 | DU-07 | Gesture/permission/device suite |
| VAN-NX-007 | DU-08 | Fail-closed owner action lifecycle |
| VAN-NX-008 | DU-09 | Five working destinations |
| VAN-NX-009 | DU-10 | Real chart source/bridge/device tests |
| VAN-NX-010 | DU-11 | Independent broker/protection receipts |
| VAN-NX-011 | DU-12 | Fast supported symbol access |
| VAN-NX-012 | DU-13 | Verified facts and clear disagreement |
| VAN-NX-013 | DU-14a, DU-14b, DU-14d | §8.9; minimum independent sources per category; checked wording |
| VAN-NX-014 | DU-15 | 78-surface obligations and readback |
| VAN-NX-015 | DU-16 | Source-authenticated nodes/edges and deterministic layout |
| VAN-NX-016 | DU-17 | Assignments and receipts, no fake status |
| VAN-NX-017 | DU-18 | Provider-state bound approval E2E |
| VAN-NX-018 | DU-19 | Every original feature reachable |
| VAN-NX-019 | DU-20 | Physical owner-device/OS tests |
| VAN-NX-020 | DU-21 | Real native scenario execution |
| VAN-NX-021 | DU-22 | Negative/pathological tests |
| VAN-NX-022 | DU-23 | Physical jank/battery/TalkBack tests |
| VAN-NX-023 | DU-24 | Static lint + route/feature bijection |
| VAN-NX-024 | DU-25 | Every applicable F0–F15 gate has receipt |
| VAN-NX-025 | DU-26 | Owner on-device decision, immutable APK |
| VAN-NX-026 | DU-01 | Research-input admission record (`RESEARCH_INPUT_ACCEPTANCE.json`): the 39 REA record IDs and hashes, APK identities, static-only limits and owner acknowledgement; DU-27 supplies the research |
| VAN-NX-027 | DU-28 | §7.4; §18.2 manual-trading cases; demo before live |
| VAN-NX-028 | DU-00 | Every ledger row classified; parity checker fails on an induced omission |
| VAN-NX-029 | DU-24 | Legacy import fails compilation; banned-word and literal-style lints fail when induced |
| VAN-NX-030 | DU-02 | §2.6 table applied in string catalogue and goldens |
| VAN-NX-031 | DU-28b | §7.4.6–§7.4.7; §18.2 handover and add cases |
| VAN-NX-032 | DU-14c | §8.4–§8.5; per-path shadow evidence and owner-signed promotion |
| VAN-NX-033 | DU-14e | §8.10.9; per-class paper and shadow evidence; owner signature per class |
| VAN-NX-034 | DU-28c | §7.4.12; minimum sample; findings cite trades; soft notices never block |
| VAN-NX-035 | DU-28d | §7.4.13; learns from winners and losers; candidates pass deflated Sharpe, PBO and walk-forward before paper |
| VAN-NX-036 | DU-14f | §8.2, §8.4; reachability and terms verified |
| VAN-NX-037 | DU-14b | §8.3; detectors never trade alone |
| VAN-NX-038 | DU-14a | Terms check and live probe per feed |
| VAN-NX-039 | DU-24 | Both proven to fail when deliberately broken |
| VAN-NX-040 | DU-12a | §7.8.1; one subscription per instrument and stream; revisioned recovery |
| VAN-NX-041 | DU-10 | §7.8.2; 500-cycle lifecycle test; S24 budgets |
| VAN-NX-042 | DU-10 | §7.8.2–§7.8.3; renderer swap; bridge fuzzing; forbidden order call |
| VAN-NX-043 | DU-10b | §7.8.4; anchor round-trip; undo/redo; cross-device sync |
| VAN-NX-044 | DU-10c | §7.8.5; no order route; deterministic replay |
| VAN-NX-045 | DU-28e | §7.8.6; per-venue tests; no state collapse; no silent unit rounding |
| VAN-NX-046 | DU-10d | §7.8.7; consent, provenance, no authority effect |
| VAN-NX-047 | DU-12b | §7.8.8–§7.8.9; dedupe across devices; alerts never trade |
| VAN-NX-048 | DU-29 | §7.9.1–§7.9.2 |
| VAN-NX-049 | DU-29 | §7.9.3 |
| VAN-NX-050 | DU-29 | §7.9.4 |
| VAN-NX-051 | DU-29a | §7.9.5, §7.9.10 F-033 regression |
| VAN-NX-052 | DU-29b | §7.9.6–§7.9.8 |
| VAN-NX-053 | DU-01 | §17 F0; Feature Ledger reconciled with Product Truth; record signed (OQ-05) |
| VAN-NX-054 | DU-MR | §19.1 P5–P6; signed APK, tested rollback; retirement only after full parity, with its own negative tests |
| VAN-NX-055 | DU-29c | §7.9.12; timeout → OUTCOME_UNKNOWN never resubmits; redirect never SETTLED; sandbox provider |
| VAN-NX-056 | DU-29 | §7.9.0; no float money (static check fails when induced); typed IDs |
| VAN-NX-057 | DU-29 | §7.9.1; REMOTE_CLOSED only on broker readback |
| VAN-NX-058 | DU-30 | §7.10; PR #92 suite green after consolidation; AGGRESSIVE refuses without admitted edge (gate broken on purpose) |
| VAN-NX-059 | DU-29a | §7.5; a deposit never shown as profit |
| VAN-NX-060 | DU-23 | §15.1; device cases on the S24 |
| VAN-NX-061 | DU-11 | Derived from VATI and broker data with unit and freshness provenance; no unsourced number |
| VAN-NX-062 | DU-11 | Every figure traced to its policy; a fail-open risk path is a P0 blocker |
| VAN-NX-063 | DU-06 | Sources cited; budget not exceeded; stale marked |
| VAN-NX-064 | DU-29 | A local change never claims a broker update |
| VAN-NX-065 | DU-14d | Provenance on every element; no authority effect |
| VAN-NX-066 | DU-19 | Erasure readback; source deletion is not claimed as model unlearning |
| VAN-NX-067 | DU-19 | Goal changes audited |
| VAN-NX-068 | DU-19 | No silent failed run |
| VAN-NX-069 | DU-21 | Unknown never shown as pass |

