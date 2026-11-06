# VAN-ARTEMIS-OWNERSHIP-PROPOSAL-001 — Artemis model adapter ownership

**Status:** DECIDED 2026-10-10 by the owner — option 2 with direct Global DIAL MCP access (DIAL `DEC-079`).
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

decision: OPTION_2_MOVE_TO_DIAL_DEVELOPMENT_SYSTEM_WITH_DIRECT_GLOBAL_DIAL_MCP_ACCESS
owner_signature_status: SIGNED
owner_signed_at: 2026-10-10
owner_words: "transfer ownership of the artemis adapter to dial development system but give dial mcp direct access to the adapter that does not go through hermes"
provenance: Owner instruction in a Claude Code session; no device or cryptographic signature is claimed.

Outcome: the adapter now lives at `Vanguduza/dial-development-system:deploy/netcup/hermes-control/artemis/subscription/`
(moved byte-for-byte; DIAL `DEC-079`, amending `DEC-051`). Global DIAL MCP gets a direct typed route to it that does
not pass through Hermes (`agent-system/registries/GLOBAL_DIAL_MCP_ARTEMIS_DIRECT_ROUTE.json` there). VAN removed
`tools/artemis_subscription/` and `tests/test_artemis_subscription.py` and keeps only its owner console
(`backend/van_gateway/artemis/console.py`).
