# VAN-ARTEMIS-OWNERSHIP-PROPOSAL-001 — Artemis model adapter ownership

**Status:** PROPOSAL — not owner-signed. An agent raised this; only the owner decides it.
**Raised:** 2026-10-09, VAN canon audit of `codex/van-canon-consolidation-2026-10-08`.

## Conflict

DIAL decision `DEC-051` (dial-development-system `agent-system/registries/DECISION_LOG.json`):
"ARTEMIS is DIAL's Android testing harness on dial-control under Hermes; VAN hosts only an owner
console; results are TEST_EVIDENCE candidates."

The VAN consolidation also carries `tools/artemis_subscription/` — a custom model-provider profile,
an MCP launcher and a `sitecustomize` hook that rebind all 20 native Artemis roles to `gpt-5.6-sol`
through the owner's ChatGPT subscription, installed on `dial-control`
(`tools/artemis_subscription/README.md`). That is VAN owning the harness's model binding, which is
more than an owner console.

Nothing was changed by this proposal. The adapter remains in place and documented as it is.

## Options for the owner

1. **Amend DEC-051:** VAN may own an Artemis model-provider adapter that runs on dial-control, with
   Artemis itself, its controllers, device lock, task lifecycle and verification remaining DIAL's.
2. **Move the adapter to dial-development-system:** relocate `tools/artemis_subscription/` beside
   the Artemis plane DIAL owns, leaving VAN with only the owner console
   (`backend/van_gateway/artemis/console.py`).

Recommendation: option 2 keeps one owner per concern (DIAL `DEC-024`); option 1 is lower effort.

## Owner decision

decision: null
owner_signature_status: UNSIGNED
