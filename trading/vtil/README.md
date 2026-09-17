# VTIL — VAN Trading Intelligence Layer (on borrowed DIAL VEKL infrastructure)

Canonical authority: `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md` Part E §E.4.

| Path | Role |
|---|---|
| `registry/ENGINEERING_RESOURCE_SOURCE_REGISTRY.json` | Trading knowledge sources in DIAL's VEKL source schema (T0 VAN policy, T1 BLS/Fed/ALFRED/CFTC/CME/Cboe/WGC/MetaQuotes/Deriv/Nautilus/LEAN/Databento, T4 community discovery-only). |
| `registry/ENGINEERING_RESOURCE_REGISTRY.json` | Reference resources with trading task classes, explicit `selection_purpose`, and `PLACE_ORDER` in every `forbidden_effects`. |
| `registry/ENGINEERING_SKILL_REGISTRY.json` | Empty by design: no executable trading skill is admitted. |
| `registry/TASK_CLASS_SIGNAL_POLICY.json` | Trading task-class vocabulary as registry-owned prose/path rules, so DIAL's classifier code is reused unchanged. |
| `tools/resolve_probe.mjs` | Mirrors DIAL's two hard-coded registry directory names and runs DIAL's unmodified resolver against this registry; exits non-zero unless every golden case is satisfied. |

Run: `DIAL_REPO=/path/to/dial-new node trading/vtil/tools/resolve_probe.mjs` (also wrapped by `trading/tests/test_vtil_borrow.py`).

Invariants: no source allows sensitive data or executable content; no resource can place an order, change a mandate or promote a strategy; community sources are corroboration/discovery only; the T0 policy resource always binds.
