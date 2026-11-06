# VAN Next — Unified Backend-First Rebuild Rev 1.13

**State:** improved specification package, **not** an issued F15, BG-001, signed owner visual golden, running app, or trading authorisation. Prepared 18 October 2026 after comparing Rev1.12, Rev1.11, the supplied Graphite Command contract and live GitHub/Global DIAL branches.

## Single authority

- **Master blueprint:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_13_20261018.md` (retains Rev1.12 full functionality and adds precise Rev1.13 sections 31–37).
- **One development plan:** `plan/DEVELOPMENT_PLAN.json`, rendered as `plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_13.md`.
- **Visual materials:** `design/VAN_TACTILE_SPATIAL_STYLE_REV2.md`, `design/VAN_MATERIAL_TOKENS_REV2.json`, `design/COMPONENT_RECIPES_REV2.json`, and per-context `design/ALL_234_SURFACE_MATERIAL_ACCEPTANCE_REV1_13.md`.
- **Source and branch evidence:** `consolidation/REV113_REPOSITORY_RECONCILIATION.md` and matching JSON. 66 advertised heads at 63 commits as independently observed on the VM 18 October. Source head for PR101 remains `a39f241b0135cf92cc5a6b9a28af226aa294603d`; main remains `8eb1889822fc8a83f219977c15340172e16acd91`.
- **Preserved original:** `lineage/REV112_MASTER_SOURCE_UNCHANGED.md` and `lineage/REV112_PLAN_SOURCE_UNCHANGED.md`; all other Rev1.12 packaged inputs inherited, plus exact owner Graphite Command v1 source.

## Completion architecture

Predevelopment PRE-001/2 and independent F15 PRE-003 → 82 complete backend capability units → 12 independent backend-verification units → **BG-001 / packet 098** → 3 full-product UX units → 23 native FE units → 5 qualification units → controlled release + tested retirement. No native UI or design golden runs ahead of BG. A backend omission discovered during UX reopens the affected gate.

**Scope:** 237 inherited requirements, 234 contextual screen obligations and 349 historical action entries. Existing 1,287 application acceptance tests are preserved, **41 newly added planned tests**, all **NOT_RUN**. There are 30 proposed tactile component recipes and paired theme roles. Source style tokens are not native accepted goldens.

## Independent spec validation

1. `python verification/verify_rev113.py` checks the complete 131-node graph, F15/BG ordering, 234 style bindings, typed recipes and 1,328 planned tests.
2. `python plan/render_plan.py --check` refuses a stale rendered plan or input provenance after generation.
3. `python verification/verify_unified.py` retains parent review logic where compatible; Rev1.13 independent checks do not claim runtime qualification.

**Do not merge PR #101 automatically**, replace it with an older plan, or use the pending owner signature as a validation shortcut. No application source or live services were modified by this package.
