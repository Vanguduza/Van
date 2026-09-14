# VAN Profile — Expected MCP / Capability Servers

Hermes profile **`van`** is the sole agent runtime. Credentials are brokered through the VAN gateway or provider runtime; raw secrets never enter prompts. A missing server/capability fails closed.

## Core

| Server | Purpose | Credential model |
|---|---|---|
| `van-gateway` | Owner auth, grants, Google planner, evidence, attention/reminders, health | Device-signed; no secret passthrough |
| `filesystem` (scoped) | Registered project files | Path allowlist + Project Truth + grants |
| `git` (scoped) | SHA/evidence/diff/write | Read default; writes require grant |

## Google Workspace — gateway mediated

| Capability | Purpose | Gate |
|---|---|---|
| `google-gmail` | Mail read/draft/send | A2 read; A4 send |
| `google-calendar` | Events read/write | A2/A3; irreversible/external effects as A4 |
| `google-drive` | File metadata/content | External content is untrusted |
| `google-contacts` | Contact resolution | A2 |
| `google-tasks` | Task reads/writes | A2/A3 |

Workspace refresh tokens are encrypted in the gateway and exchanged for short-lived access tokens before API calls. Neither token is visible to Hermes prompts.

## Google intelligence mesh

The canonical capability registry is `registries/google_capabilities.json`. Hermes requests deterministic plans through the VAN gateway before invoking Google specialists.

| Capability | Role | Credential plane |
|---|---|---|
| `gemini` | Reasoning/multimodal | Gemini runtime |
| `gemini_live` | Live voice/screen perception | Gemini runtime |
| `deep_research` | Cited autonomous investigation | Gemini runtime |
| `gemini_notebook` | Personal source-grounded research | Consumer session |
| `gemini_notebook_enterprise` | Programmatic notebook/source lifecycle | Google Cloud/service |
| `mixboard` | Divergent visual ideation | Consumer session |
| `stitch` | UI design convergence | Consumer session |
| `antigravity` | Complex development worker | Consumer/developer session |
| `jules` | Bounded GitHub maintenance worker | Consumer/developer session |
| `workspace_api` | Deterministic Workspace actions | Workspace OAuth |
| `workspace_studio` | Multi-step Workspace-native workflows | Consumer session |
| `nano_banana` | Image generation/editing | Gemini runtime |
| `veo` | Video generation | Gemini runtime |
| `flow` | Human-facing video creative surface | Consumer session |
| `ai_studio` | Google model prototyping | Consumer session |
| `a2a_adk` | External Google-agent interoperability | Cloud/service |

A configured consumer session is not automatically `READY`. Recorded certification evidence is required before VAN claims successful live use.

## Provider routing

Gemini is a Hermes provider route, not a second assistant. Antigravity/Jules are workers. Google ADK/A2A peers are external workers. All remain subordinate to the `van` profile, action classes, Project Truth, grants and evidence rules.

## Configuration checklist

1. No committed secrets.
2. Register the canonical owner Google principal with `tools/google/configure_google_identity.py`.
3. Configure each credential plane independently.
4. Use `tools/google/certify_google_mesh.py` to inspect readiness.
5. `CONFIGURED` means wiring exists; `READY` requires certification evidence.
6. Missing capability => `DEGRADED`; never simulate results.
7. Consumer cookies/session tokens may not be exported or injected into prompts.

## References

- `docs/GOOGLE_INTELLIGENCE_MESH.md`
- `hermes/profile/van/config.yaml`
- `hermes/providers/gemini.md`
