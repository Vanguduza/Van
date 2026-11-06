# Rev1.13 source-state reconciliation — branch and product audit

**Live branch refresh:** 2026-10-18 04:29 UTC, `van-trading-core` Global DIAL MCP. There are 66 advertised branches at 63 distinct head commits, agreeing with the older Rev1.12 inventory; GitHub corroborates main `8eb1889…`, PR101 `a39f241…` and PR100 `0a694a9…`, both open/unmerged. No broad development-branch merge was performed by this study.

The prior Rev1.12 inventory checked 4,634 union source paths and 3,680 UTF-8 blobs in a size-bounded content scan, leaving 26 encoding/size exceptions and uncommitted/runtime scope outside that scan. Rev1.13 does **not** relabel that as a universal line-by-line semantic code review. Earlier PR93 source has been fully materialised and mechanically indexed at exact SHA `dfc1557…`, with semantic analysis still a separate F15 obligation.

## Function-level admission candidates

| Existing branch / PR | Concrete changes worth consideration | Pre-admission blocker / treatment |
|---|---|---|
| PR #93 (canon, `dfc1557…`) | Android controller/gateway/VATI/Browser/voice/task account functions and original UX flows | Function/route/test/provenance admission; no blanket merge or style inheritance |
| PR #101 (`a39f241…`) | Incremental ledger, scoped slippage/rounding, pending-order/lockout candidates, signed decisions | Pending fill stop readback, expiry, blackout race, terminal states, limit-price violation, qualified economic eval and signed policy activation |
| PR #92 (`923ecf9…`) | NORMAL, RISKY and selective AGGRESSIVE signed temperaments | Calibrated independent edge proof; risk ceiling never lifted; no live switch by visual tile |
| PR #95 + #97 (`0e825b…` / `081a54…`) | Muse events, native action/approval states, computer-worker receipt binding | Provider ownership/lease identity, no duplicate approvals or fabricated effects |
| PR #98 (`68394a…`) | Native Android / site owner Muse controls (`MuseOwnerControls`, `MuseRoute`, gateway tasks) | Verify exact credential/scope/lease and genuine action readback; do not design as VNC clone |
| PR #99 (`4ad121…`) | Authenticated Studio page and cinematic-workspace entry | Preserve app/site navigation and capability flow where useful; do not override locked VAN Next material tokens |
| PR #100 (`0a694a…`) | B1 whole-product and B4 engineering-no-waiver corrections | Admit into Product Truth and F15 prep; not a runtime feature; pending review |
| PR #77, #70, JEV-convergence, browser acquisition, character variants | Advisory provenance, existing shared Jev, bounded acquisition, Floating VAN identity | No second authority owner or hidden new external access; compare exact caller versions |

**All other 66-head branches remain candidates in the parent source-tree inventory.** Their absence from the focused table is not owner retirement; PRE-001 must generate a full 66-row disposition and track each surviving unique feature or mark no new independent delta with evidence. Reopened branch heads invalidate only affected contracts, not unrelated accepted functionality.

## Root causes and mandatory repair sequence

- **RC-TRD-01 Ambiguous execution semantics:** stop/limit and price/trigger/fill are conflated across strategy, policy and simulator → exact venue order-type contract, timestamped state reduction and chronological matching, including partial fills.
- **RC-TRD-02 Incomplete pending lifecycle:** pending-order policy can expire later than the sealed template, ignore new event blackout, and display expired/cancelled requests as WORKING → all state changes through one canonical reducer and broker readback.
- **RC-TRD-03 Protection confirmation gap:** pending fill and immediate fill can follow different stop-readback/error sequences → common protection reconciliation state; missing protection is neither healthy nor ignored.
- **RC-TRD-04 Point-in-time admission:** future-bar testing, fixed bid-price spread convention, calendar years mistaken for genuine rolling folds and DSR as "chance of skill" undermine profitability conclusions → qualified evaluator oracle and real frozen fold manifests before strategy research/promotion.
- **RC-RISK-05 Persisted governance:** default-only cooldown/probation values could become effective without owner-signed mandate content → activation digest and persistent strategy/manual/account scope readback.
- **RC-PLATFORM-06 Fragmented branch owners:** PR93, PR95/97/98/99, PR100/101 and old visuals overlap but are not merged → one function-level ledger, one owner action entrypoint and clean presentation isolation.
- **RC-UX-07 Generic dark style is not full app identity:** Graphite V1 five specimens and 16 recipes omit light full-material parity and 234 contexts → engineered dual theme, native-after-BG golden and role-specific composition.
- **RC-EVID-08 Document green is not production green:** 1,287 inherited application contracts were NOT_RUN; inherited F15/BG are unissued → independent receipt validation with exact source/provider/build and owner acceptance.

## Closure policy

Predevelopment `PRE-001/2/3` closes source/decision/evidence *before* code. The 82 backend capabilities and 12 BQ units close **in full** before `BG-001`; new UX cannot build around placeholder APIs or unimplemented brokers. Physical app qualification occurs after implementation and remains separate from predevelopment F15. Backend change after BG invalidates the affected consumer contract/visual acceptance until requalified. No live trading/funds or protected main merge is authorised by documentary acceptance.
