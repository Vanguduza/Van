# VAN whole-system audit evidence

Canonical report: `docs/VAN_WHOLE_SYSTEM_IMPLEMENTATION_AUDIT_AND_CERTIFICATION_REV_1.md`
Machine-readable register: `findings.json` (schema `van-system-audit-findings/1`)

Repository state: branch `claude/van-system-audit-ysgtcd`, HEAD `dff38a0`, version `0.5.0-dev`.
Audit date 2026-09-18. **No production code was modified by this audit.**

## Layout

| Path | Contents |
|---|---|
| `repository/` | HEAD, git log, remote branches, per-area file and line counts |
| `runtime/` | in-process gateway boot probe and the full mounted route list |
| `command-execution/` | the owner-command lifecycle probe, plus its raw output with Hermes down and with a local stand-in Hermes accepting runs |
| `security/` | authority-boundary probes (internal token escalation, reasoning kernel, owner model, mission verification) and their raw output |
| `tests/` | the three Python suite results at HEAD |
| `architecture/` | backend gateway core: route table, command lifecycle, mission core, storage, stubs |
| `android/` | Android components, information architecture, networking, command path, tests |
| `aura/` | floating bot, aura rendering, semantic state, visual evidence, doc conformance |
| `browser/` | Browser Fabric, n8n, workflow compiler, Temporal, computer-use fabric |
| `cognition/` | cognition, context, memory, learning — also the source for the context and memory sections |
| `google/` | Google credential planes, transports, Notebook providers, VEKL and Obsidian adapters |
| `hermes/` | Hermes boundary, MCP shim, policy hook, model-role matrix, attestations |
| `infrastructure/` | production topology, security threat model, observability, test architecture |
| `trading/` | trading topology, risk authority, transports, ledger, trade-state propagation |
| `voice/` | wake, capture, ASR, TTS, transcript provenance, mission binding |

Deep-dive files are not duplicated across folders. The cognition file covers context and memory; the
Google file covers VEKL and Obsidian; the infrastructure file covers security, observability and tests.

## Reproducing the probes

```bash
cd backend && pip install -r requirements.txt
python3 ../evidence/van-system-audit/command-execution/probe_command_lifecycle.py down
python3 ../evidence/van-system-audit/command-execution/probe_command_lifecycle.py fake_hermes
python3 ../evidence/van-system-audit/security/probe_authority_boundaries.py
python3 ../evidence/van-system-audit/security/probe_mission_verification.py
```

Each probe runs the real FastAPI application in-process against a throwaway SQLite database and
touches no external system. They are read-only with respect to the repository.

## What this evidence does NOT contain

No live Hermes run, no live Google API call, no live broker order, no browser worker session, no
on-device screenshot, no Android instrumentation run, and no regenerated visual boards. Each of those
required a dependency unavailable in this environment, and every affected finding is marked
**NOT VERIFIED** rather than **NOT IMPLEMENTED** in the canonical report.
