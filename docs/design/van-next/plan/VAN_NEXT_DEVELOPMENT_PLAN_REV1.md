# VAN Next — Deterministic Development Plan, Rev 1

**Status:** `DRAFT / AWAITING_OWNER_APPROVAL`. No packet starts until the owner approves this plan.
**Derived from:** `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9B_20261016.md` §16.1, §16.2, §19.1 and `VAN_NEXT_OWNER_DECISIONS_REV1.md` (open questions).

| Input | SHA-256 (full file bytes) |
|---|---|
| `docs/design/van-next/VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9B_20261016.md` | `709c68492bd4e939fff1ffd8deec843bbd605d79bf54d584c62e768a20dfdc9d` |
| `docs/design/van-next/VAN_NEXT_OWNER_DECISIONS_REV1.md` | `488806b5639e5d5b806149ddd849bcf48cf14fcd1128580aea904478ab2ff74d` |
| `docs/design/van-next/plan/generate_plan.py` | `62794a01eb7d3a9a02808ee262f1c6a616924bfb787b2f2ee29730f8392b2d2f` |
| `docs/design/van-next/plan/REQUIREMENT_LOCK_REV1_9B.json` | `9b3954fd896f68467abe91571332f0fa2f4596da8be7c8528fbe4bcdd4809c49` |
| `docs/design/van-next/VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.json` | `34b97daaf8d92951833bc0270998e9ae5159fdeffa078844a8d2d4241cf52d1d` |

Aggregate input digest `fb9eb48dcf299194455143d4381a7a7d5884803beed45cd0f21c7b3ad9a3fb42` = SHA-256 of the blueprint bytes, one newline byte, then the decision-record, generator, requirement-lock and surface-matrix bytes. `PLAN_INPUT_PROVENANCE.json` records these values and the hashes of the generated plan.

**Generator:** `plan/generate_plan.py`. Re-running it on the same inputs gives byte-identical output. `--check` validates the inputs **and** fails if this file is stale; `--selftest` proves each check catches a deliberately broken input.

## 1. Rules

1. **One packet at a time, in sequence order.** A packet starts only when its entry gate holds; the next packet starts only when the current one has exited. Parallel work is allowed only when the owner assigns another worker, and then only to packets of the same wave (§6) whose dependencies have exited.
2. **Entry gate (every packet):** for every code-bearing packet (any unit other than DU-00a, DU-01 and DU-31), a current independent F15 `FORENSIC_BUILD_READY` certificate from DU-31 and a passing deterministic predevelopment gate (PRD-DDP-R2 §19); all dependency packets exited; the packet's acceptance contract written and owner-approved (fields of blueprint §16.4, including exact source SHA, files, negative cases, acceptance commands, rollback); every open question that blocks its start resolved.
3. **Exit gate (every packet):** the contract's acceptance commands pass on a recorded commit; each new gate is broken deliberately and seen to fail before it is trusted; feature preservation holds as in rule 3a; independent review recorded; artifact state at least `REPOSITORY_PROVEN` (§17.1). Device, live and owner-acceptance states are reached in P4–P5 and are never claimed earlier.
3a. **Feature preservation, in two stages** (Rev 1.9b, NXA-04). The parity checker is built by PKT-004 (DU-00b), so it cannot gate earlier packets. **PKT-001–PKT-003 (read-only):** the *preservation-inventory gate* — no source file changes; the frozen heads still resolve to the recorded SHAs; `generate_plan.py --check` passes, so the owner-pinned requirement lock and the 78 legacy surfaces with their owner actions are intact; after DU-00a exits, its Feature Ledger changes only through recorded rows, each with a reason. **PKT-004:** exits only with the parity checker qualified — an induced omission fails it — and no `FEATURE_LOSS` on consolidated `main`. **PKT-005 onward:** every packet's exit requires the parity checker to show no `FEATURE_LOSS`. Validator rule `PARITY_BEFORE_CHECKER` keeps every code-bearing unit downstream of DU-00b.
4. **No code outside a packet.** Work not in an open packet is not done. A discovery that changes scope stops the packet and goes to the owner as a blueprint amendment; the plan is regenerated.
5. **Order key** (deterministic): phase (§19.1) → dependency depth in the §16.2 DAG → lane order of §16.3 → DU number. P2 builds the five §19.1 vertical slices as milestone M1 of each DU in a slice and of every DU those slices depend on; P3 completes each DU (M2), then the remaining DUs in full.
6. **Owner-only steps** are listed per packet and are never assumed: signatures, open-question answers, `OWNER_RETIRE` dispositions, live promotion.

## 2. Validation of the blueprint inputs

- Development Units in the DAG: 51; solid dependency edges: 92; non-blocking (dotted) edges: 2.
- Requirements parsed: 77; open questions parsed: 19.
- Findings: none. The DAG is acyclic; every requirement and every open question maps to a DU in the DAG; every DU has a lane; no DU depends on a later phase; every build unit has a dependency path to DU-25, DU-26 and DU-MR; no code-bearing unit runs before the F15 gate DU-31; every unit a requirement needs is built upstream of it; every code-bearing unit is downstream of the parity checker; no DAG node, requirement or open question is duplicated; the requirement IDs and text and the 78 legacy surfaces' owner actions match the owner-pinned requirement lock.
- DUs with no requirement row (kept, flagged for the freeze list): none.
- DU-27 is not a packet: REA research (static) done under OD-15/16/17. Its admission record is VAN-NX-026, carried by DU-01; its findings are inputs to the DU-10 and DU-29 contracts.

## 3. Plan-level choices awaiting owner approval

These are the only inputs not read from the blueprint.

| DU | Phase | Lane |
|---|---|---|
| DU-00a | P0 | Consolidation |
| DU-00b | P0 | Consolidation |
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
| DU-31 | P0 | Consolidation |
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
| PKT-001 | DU-00a | Read-only inventory: frozen heads, Feature Ledger, classification | P0 | FULL | Consolidation | — | VAN-NX-071 | OQ-05 / — |
| PKT-002 | DU-01 | Product Truth and preservation reconciliation | P0 | FULL | Foundation | PKT-001 | VAN-NX-026, VAN-NX-053 | — / — |
| PKT-003 | DU-31 | Predevelopment closure and independent F15 certificate | P0 | FULL | Consolidation | PKT-002 | VAN-NX-070 | — / — |
| PKT-004 | DU-00b | Source consolidation and parity oracle | P0 | FULL | Consolidation | PKT-003 | VAN-NX-028 | — / — |
| PKT-005 | DU-02 | Visual golden authority + labels | P1 | FULL | Foundation | PKT-004 | VAN-NX-001, VAN-NX-030 | — / — |
| PKT-006 | DU-24 | Anti-loss checker + module isolation | P1 | FULL | Foundation | PKT-004 | VAN-NX-023, VAN-NX-029, VAN-NX-039 | — / — |
| PKT-007 | DU-03 | Clean theme and component system | P1 | FULL | Foundation | PKT-005, PKT-006 | VAN-NX-002 | — / — |
| PKT-008 | DU-04 | Adaptive app shell | P1 | FULL | Foundation | PKT-006, PKT-007 | VAN-NX-003 | — / — |
| PKT-009 | DU-29 | Account lifecycle, linking, edit, delete | P2 | M1 | Trading | PKT-004 | VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-056, VAN-NX-057, VAN-NX-064 | OQ-15, OQ-18 / — |
| PKT-010 | DU-30 | Trading modes | P2 | M1 | Trading | PKT-004 | VAN-NX-058 | — / OQ-20 |
| PKT-011 | DU-14a | Multi-source feeds + health | P2 | M1 | News | PKT-004 | VAN-NX-013, VAN-NX-038 | OQ-06, OQ-11 / — |
| PKT-012 | DU-29a | Funding ledger + flow-adjusted risk | P2 | M1 | Trading | PKT-009 | VAN-NX-051, VAN-NX-059 | OQ-16 / — |
| PKT-013 | DU-14b | Story analysis + headline episodes + history profiles | P2 | M1 | News | PKT-011 | VAN-NX-013, VAN-NX-037 | — / — |
| PKT-014 | DU-28 | Manual trading backend | P2 | M1 | Trading | PKT-004, PKT-012 | VAN-NX-027, VAN-NX-073, VAN-NX-077 | OQ-02, OQ-07 / OQ-01, OQ-03, OQ-21 |
| PKT-015 | DU-14c | Decision paths D1-D7, shadow then live | P2 | M1 | News | PKT-013 | VAN-NX-032 | OQ-09 / OQ-08 |
| PKT-016 | DU-05 | Orb semantics and rendering | P2 | M1 | Orb/Floating | PKT-008 | VAN-NX-004 | — / — |
| PKT-017 | DU-07 | Floating VAN remodel | P2 | M1 | Orb/Floating | PKT-008 | VAN-NX-006 | — / — |
| PKT-018 | DU-12a | Shared market projection | P2 | M1 | Trading | PKT-008 | VAN-NX-040 | — / — |
| PKT-019 | DU-28b | Adds, Hand to VAN, take back | P2 | M1 | Trading | PKT-014 | VAN-NX-031 | — / — |
| PKT-020 | DU-28e | Order vocabulary + venue capabilities | P2 | M1 | Trading | PKT-014 | VAN-NX-045, VAN-NX-074, VAN-NX-075, VAN-NX-076 | — / — |
| PKT-021 | DU-15 | Project data adapter | P2 | M1 | Work Graph | PKT-008 | VAN-NX-014 | — / — |
| PKT-022 | DU-08 | Attention/Approvals | P2 | M1 | Continuity | PKT-008 | VAN-NX-007 | — / — |
| PKT-023 | DU-21 | Browser/Voice/ARTEMIS | P2 | M1 | Continuity | PKT-008 | VAN-NX-020, VAN-NX-069 | — / — |
| PKT-024 | DU-09 | Trading Home | P2 | M1 | Trading | PKT-008, PKT-010, PKT-018 | VAN-NX-008 | — / — |
| PKT-025 | DU-16 | Spatial task graph | P2 | M1 | Work Graph | PKT-021 | VAN-NX-015 | — / — |
| PKT-026 | DU-10 | Rich Chart | P2 | M1 | Trading | PKT-024 | VAN-NX-009, VAN-NX-041, VAN-NX-042 | OQ-14 / — |
| PKT-027 | DU-13 | Analyst | P2 | M1 | Trading | PKT-024 | VAN-NX-012 | — / — |
| PKT-028 | DU-11 | Positions/Orders/Protection | P2 | M1 | Trading | PKT-014, PKT-019, PKT-020, PKT-026 | VAN-NX-010, VAN-NX-061, VAN-NX-062 | — / — |
| PKT-029 | DU-14d | News briefs + News UI | P2 | M1 | News | PKT-013, PKT-015, PKT-027 | VAN-NX-013 | — / — |
| PKT-030 | DU-06 | Compact Quick Hub | P2 | M1 | Orb/Floating | PKT-016, PKT-021, PKT-022, PKT-024, PKT-028 | VAN-NX-005, VAN-NX-063 | — / — |
| PKT-031 | DU-29 | Account lifecycle, linking, edit, delete | P3 | M2 | Trading | PKT-004, PKT-009 | VAN-NX-048, VAN-NX-049, VAN-NX-050, VAN-NX-056, VAN-NX-057, VAN-NX-064 | OQ-15, OQ-18 / — |
| PKT-032 | DU-30 | Trading modes | P3 | M2 | Trading | PKT-004, PKT-010 | VAN-NX-058 | — / OQ-20 |
| PKT-033 | DU-14a | Multi-source feeds + health | P3 | M2 | News | PKT-004, PKT-011 | VAN-NX-013, VAN-NX-038 | OQ-06, OQ-11 / — |
| PKT-034 | DU-29a | Funding ledger + flow-adjusted risk | P3 | M2 | Trading | PKT-012, PKT-031 | VAN-NX-051, VAN-NX-059 | OQ-16 / — |
| PKT-035 | DU-14b | Story analysis + headline episodes + history profiles | P3 | M2 | News | PKT-013, PKT-033 | VAN-NX-013, VAN-NX-037 | — / — |
| PKT-036 | DU-28 | Manual trading backend | P3 | M2 | Trading | PKT-004, PKT-014, PKT-034 | VAN-NX-027, VAN-NX-073, VAN-NX-077 | OQ-02, OQ-07 / OQ-01, OQ-03, OQ-21 |
| PKT-037 | DU-29c | Funds orchestration | P3 | FULL | Trading | PKT-031, PKT-034 | VAN-NX-055 | OQ-19 / — |
| PKT-038 | DU-14c | Decision paths D1-D7, shadow then live | P3 | M2 | News | PKT-015, PKT-035 | VAN-NX-032 | OQ-09 / OQ-08 |
| PKT-039 | DU-14f | Prediction-market expectations | P3 | FULL | News | PKT-035 | VAN-NX-036 | — / — |
| PKT-040 | DU-05 | Orb semantics and rendering | P3 | M2 | Orb/Floating | PKT-008, PKT-016 | VAN-NX-004 | — / — |
| PKT-041 | DU-07 | Floating VAN remodel | P3 | M2 | Orb/Floating | PKT-008, PKT-017 | VAN-NX-006 | — / — |
| PKT-042 | DU-12a | Shared market projection | P3 | M2 | Trading | PKT-008, PKT-018 | VAN-NX-040 | — / — |
| PKT-043 | DU-28b | Adds, Hand to VAN, take back | P3 | M2 | Trading | PKT-019, PKT-036 | VAN-NX-031 | — / — |
| PKT-044 | DU-28c | Behaviour diagnostics | P3 | FULL | Trading | PKT-036 | VAN-NX-034 | OQ-13 / — |
| PKT-045 | DU-28e | Order vocabulary + venue capabilities | P3 | M2 | Trading | PKT-020, PKT-036 | VAN-NX-045, VAN-NX-074, VAN-NX-075, VAN-NX-076 | — / — |
| PKT-046 | DU-14e | Live news trading bundle | P3 | FULL | News | PKT-036, PKT-038, PKT-039 | VAN-NX-033 | OQ-11, OQ-12 / — |
| PKT-047 | DU-15 | Project data adapter | P3 | M2 | Work Graph | PKT-008, PKT-021 | VAN-NX-014 | — / — |
| PKT-048 | DU-08 | Attention/Approvals | P3 | M2 | Continuity | PKT-008, PKT-022 | VAN-NX-007 | — / — |
| PKT-049 | DU-19 | Memory/Automation continuity | P3 | FULL | Continuity | PKT-008 | VAN-NX-018, VAN-NX-066, VAN-NX-067, VAN-NX-068 | — / — |
| PKT-050 | DU-20 | Settings/Connected | P3 | FULL | Continuity | PKT-008 | VAN-NX-019 | — / — |
| PKT-051 | DU-21 | Browser/Voice/ARTEMIS | P3 | M2 | Continuity | PKT-008, PKT-023 | VAN-NX-020, VAN-NX-069 | — / — |
| PKT-052 | DU-09 | Trading Home | P3 | M2 | Trading | PKT-008, PKT-024, PKT-032, PKT-042 | VAN-NX-008 | — / — |
| PKT-053 | DU-12b | Alerts, watchlists, screener | P3 | FULL | Trading | PKT-042 | VAN-NX-047 | — / — |
| PKT-054 | DU-28d | Pattern extraction to candidates | P3 | FULL | Trading | PKT-044 | VAN-NX-035, VAN-NX-072 | — / — |
| PKT-055 | DU-29b | Portfolio, health, statements | P3 | FULL | Trading | PKT-031, PKT-042 | VAN-NX-052 | — / — |
| PKT-056 | DU-16 | Spatial task graph | P3 | M2 | Work Graph | PKT-025, PKT-047 | VAN-NX-015 | — / — |
| PKT-057 | DU-18 | Muse qualified interaction | P3 | FULL | Work Graph | PKT-047 | VAN-NX-017 | — / — |
| PKT-058 | DU-10 | Rich Chart | P3 | M2 | Trading | PKT-026, PKT-052 | VAN-NX-009, VAN-NX-041, VAN-NX-042 | OQ-14 / — |
| PKT-059 | DU-12 | Markets and Watchlists | P3 | FULL | Trading | PKT-042, PKT-052 | VAN-NX-011 | — / — |
| PKT-060 | DU-13 | Analyst | P3 | M2 | Trading | PKT-027, PKT-052 | VAN-NX-012 | — / — |
| PKT-061 | DU-17 | Agent/Handoff flow | P3 | FULL | Work Graph | PKT-056 | VAN-NX-016 | — / — |
| PKT-062 | DU-10b | Indicators, drawings, workspaces | P3 | FULL | Trading | PKT-058 | VAN-NX-043 | — / — |
| PKT-063 | DU-10c | Replay sandbox | P3 | FULL | Trading | PKT-058 | VAN-NX-044 | OQ-17 / — |
| PKT-064 | DU-11 | Positions/Orders/Protection | P3 | M2 | Trading | PKT-028, PKT-036, PKT-043, PKT-045, PKT-058 | VAN-NX-010, VAN-NX-061, VAN-NX-062 | — / — |
| PKT-065 | DU-14d | News briefs + News UI | P3 | M2 | News | PKT-029, PKT-035, PKT-038, PKT-060 | VAN-NX-013 | — / — |
| PKT-066 | DU-06 | Compact Quick Hub | P3 | M2 | Orb/Floating | PKT-030, PKT-040, PKT-047, PKT-048, PKT-052, PKT-064 | VAN-NX-005, VAN-NX-063 | — / — |
| PKT-067 | DU-10d | Chart observations | P3 | FULL | Trading | PKT-062, PKT-065 | VAN-NX-046, VAN-NX-065 | — / — |
| PKT-068 | DU-22 | Cross-domain privacy/failure | P4 | FULL | Qualification | PKT-041, PKT-061, PKT-064, PKT-065, PKT-066 | VAN-NX-021 | — / — |
| PKT-069 | DU-23 | Performance and accessibility | P4 | FULL | Qualification | PKT-068 | VAN-NX-022, VAN-NX-060 | — / — |
| PKT-070 | DU-25 | Integrated verification/Zuul | P4 | FULL | Qualification | PKT-006, PKT-032, PKT-034, PKT-036, PKT-037, PKT-038, PKT-046, PKT-048, PKT-049, PKT-050, PKT-051, PKT-053, PKT-054, PKT-055, PKT-057, PKT-059, PKT-062, PKT-063, PKT-067, PKT-069 | VAN-NX-024 | — / — |
| PKT-071 | DU-26 | Physical S24 + owner acceptance | P4 | FULL | Qualification | PKT-070 | VAN-NX-025 | — / — |
| PKT-072 | DU-MR | Controlled migration/retirement | P5 | ROLLOUT | Qualification | PKT-071 | VAN-NX-054 | — / — |
| PKT-073 | DU-MR | Controlled migration/retirement | P6 | RETIREMENT | Qualification | PKT-071, PKT-072 | VAN-NX-054 | — / — |

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
| P0 | 0 | PKT-001 (DU-00a) |
| P0 | 1 | PKT-002 (DU-01) |
| P0 | 2 | PKT-003 (DU-31) |
| P0 | 3 | PKT-004 (DU-00b) |
| P1 | 4 | PKT-005 (DU-02), PKT-006 (DU-24) |
| P1 | 5 | PKT-007 (DU-03) |
| P1 | 6 | PKT-008 (DU-04) |
| P2 | 4 | PKT-009 (DU-29), PKT-010 (DU-30), PKT-011 (DU-14a) |
| P2 | 5 | PKT-012 (DU-29a), PKT-013 (DU-14b) |
| P2 | 6 | PKT-014 (DU-28), PKT-015 (DU-14c) |
| P2 | 7 | PKT-016 (DU-05), PKT-017 (DU-07), PKT-018 (DU-12a), PKT-019 (DU-28b), PKT-020 (DU-28e), PKT-021 (DU-15), PKT-022 (DU-08), PKT-023 (DU-21) |
| P2 | 8 | PKT-024 (DU-09), PKT-025 (DU-16) |
| P2 | 9 | PKT-026 (DU-10), PKT-027 (DU-13) |
| P2 | 10 | PKT-028 (DU-11), PKT-029 (DU-14d) |
| P2 | 11 | PKT-030 (DU-06) |
| P3 | 4 | PKT-031 (DU-29), PKT-032 (DU-30), PKT-033 (DU-14a) |
| P3 | 5 | PKT-034 (DU-29a), PKT-035 (DU-14b) |
| P3 | 6 | PKT-036 (DU-28), PKT-037 (DU-29c), PKT-038 (DU-14c), PKT-039 (DU-14f) |
| P3 | 7 | PKT-040 (DU-05), PKT-041 (DU-07), PKT-042 (DU-12a), PKT-043 (DU-28b), PKT-044 (DU-28c), PKT-045 (DU-28e), PKT-046 (DU-14e), PKT-047 (DU-15), PKT-048 (DU-08), PKT-049 (DU-19), PKT-050 (DU-20), PKT-051 (DU-21) |
| P3 | 8 | PKT-052 (DU-09), PKT-053 (DU-12b), PKT-054 (DU-28d), PKT-055 (DU-29b), PKT-056 (DU-16), PKT-057 (DU-18) |
| P3 | 9 | PKT-058 (DU-10), PKT-059 (DU-12), PKT-060 (DU-13), PKT-061 (DU-17) |
| P3 | 10 | PKT-062 (DU-10b), PKT-063 (DU-10c), PKT-064 (DU-11), PKT-065 (DU-14d) |
| P3 | 11 | PKT-066 (DU-06), PKT-067 (DU-10d) |
| P4 | 12 | PKT-068 (DU-22) |
| P4 | 13 | PKT-069 (DU-23) |
| P4 | 14 | PKT-070 (DU-25) |
| P4 | 15 | PKT-071 (DU-26) |
| P5 | 16 | PKT-072 (DU-MR) |
| P6 | 16 | PKT-073 (DU-MR) |

## 7. Open questions by packet

Generated from the decision record, so packet numbers here are always current. Freeze lists cite this section instead of copying packet numbers.

| Question | Gate | Packets |
|---|---|---|
| OQ-01 | live | PKT-014 (DU-28 M1), PKT-036 (DU-28 M2) |
| OQ-02 | start | PKT-014 (DU-28 M1), PKT-036 (DU-28 M2) |
| OQ-03 | live | PKT-014 (DU-28 M1), PKT-036 (DU-28 M2) |
| OQ-05 | start | PKT-001 (DU-00a FULL) |
| OQ-06 | start | PKT-011 (DU-14a M1), PKT-033 (DU-14a M2) |
| OQ-07 | start | PKT-014 (DU-28 M1), PKT-036 (DU-28 M2) |
| OQ-08 | live | PKT-015 (DU-14c M1), PKT-038 (DU-14c M2) |
| OQ-09 | start | PKT-015 (DU-14c M1), PKT-038 (DU-14c M2) |
| OQ-11 | start | PKT-011 (DU-14a M1), PKT-033 (DU-14a M2), PKT-046 (DU-14e FULL) |
| OQ-12 | start | PKT-046 (DU-14e FULL) |
| OQ-13 | start | PKT-044 (DU-28c FULL) |
| OQ-14 | start | PKT-026 (DU-10 M1), PKT-058 (DU-10 M2) |
| OQ-15 | start | PKT-009 (DU-29 M1), PKT-031 (DU-29 M2) |
| OQ-16 | start | PKT-012 (DU-29a M1), PKT-034 (DU-29a M2) |
| OQ-17 | start | PKT-063 (DU-10c FULL) |
| OQ-18 | start | PKT-009 (DU-29 M1), PKT-031 (DU-29 M2) |
| OQ-19 | start | PKT-037 (DU-29c FULL) |
| OQ-20 | live | PKT-010 (DU-30 M1), PKT-032 (DU-30 M2) |
| OQ-21 | live | PKT-014 (DU-28 M1), PKT-036 (DU-28 M2) |

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
| VAN-NX-028 | DU-00b | Parity checker fails on an induced omission. Needs: DU-00a, DU-31 |
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
| VAN-NX-065 | DU-10d | Provenance on every element; no authority effect. Needs: DU-10d, DU-14d, DU-13 |
| VAN-NX-066 | DU-19 | Erasure readback; source deletion is not claimed as model unlearning |
| VAN-NX-067 | DU-19 | Goal changes audited |
| VAN-NX-068 | DU-19 | No silent failed run |
| VAN-NX-069 | DU-21 | Unknown never shown as pass |
| VAN-NX-070 | DU-31 | Certificate by an independent verifier; a code-bearing packet whose unit does not depend on DU-31 fails generation (induced) |
| VAN-NX-071 | DU-00a | No source change; every ledger row classified with provenance |
| VAN-NX-072 | DU-28d | §7.4.14; induced: a failing candidate never reaches the owner; a passing candidate cannot change live trading without a signed promotion; a protected-path candidate is held; the weekly run is scheduled and replays identically from the ledger |
| VAN-NX-073 | DU-28 | §7.4.15 #1; induced: a tampered new row, a re-chained old row and a deleted row are caught at once; an in-place old-row edit is caught by the next full verification |
| VAN-NX-074 | DU-28e | §7.4.15 #2; JPY and metals orders fill under normal slippage; slippage beyond the bound is still refused |
| VAN-NX-075 | DU-28e | §7.4.15 #3; randomised both-direction test; induced widening fails |
| VAN-NX-076 | DU-28e | §7.4.15 #4; induced: STOP→LIMIT refused, unsupported type refused, paper limit not filled away from the market; live STOP only after per-venue demo qualification |
| VAN-NX-077 | DU-28 | §7.4.15 lockout design; induced: no expiry, legacy top floor, no rebuild, manual counted in the account scope, no probation and unconditional baseline restore each fail a test |

