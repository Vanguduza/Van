# Gemini Provider — VAN via Hermes

Profile: **`van`**

## Canonical rule

Hermes profile `van` is the sole VAN agent runtime. Gemini is a provider and
specialist capability beneath Hermes. Android and VAN Gateway do not run a
parallel Gemini agent loop.

## Google Account Sovereignty

All Google capabilities used by VAN must trace ownership, entitlement or
infrastructure administration to the owner's canonical Google account.
Credential separation does not imply identity separation.

```text
Owner Google Account
 ├── consumer entitlements / sessions
 ├── Workspace OAuth delegation
 ├── Google Cloud project/service identity
 └── Gemini runtime credential used by Hermes
```

## Separation of credentials

| Credential plane | Used for | In LLM prompts? |
|---|---|---|
| Workspace OAuth | Gmail, Calendar, Drive, Contacts, Tasks | **Never** |
| Gemini runtime | Gemini, Live, Deep Research, Nano Banana, Veo via Hermes | **Never** |
| Google Cloud/service identity | Optional Notebook Enterprise / ADK/A2A services | **Never** |
| Consumer account session | Notebook, Mixboard, Stitch, Antigravity, Jules, Flow, AI Studio | Cookies/tokens are **never** copied into prompts |

Store runtime credentials in host environment or a deployment secret manager.
Do not commit credential files.

## Invocation path

```text
Owner
  → VAN Gateway
  → Hermes profile van
  → deterministic Google capability route
  → Gemini/provider worker
  → provenance/evidence
  → Hermes
  → VAN
```

## Capability roles

- **Gemini** — reasoning and multimodal worker.
- **Gemini Live** — perception/conversation; it does not authorize mutations.
- **Deep Research** — cited investigator; its output is evidence, not Project Truth.
- **Nano Banana / Veo** — artifact generators behind Hermes media capabilities.

Consumer products such as Notebook, Mixboard, Stitch, Antigravity, Jules and Flow
are described in `docs/GOOGLE_INTELLIGENCE_MESH.md` and the associated skills.

## Policy and action classes

- Gemini inference alone is usually A1/A2.
- Provider output remains external/untrusted until validated.
- A3/A4 project work requires an explicit capability grant.
- A3/A4 project mutation requires current Project Truth SHA.
- A4 still requires explicit owner approval.
- A5 is always denied.

## Fail closed

- Missing Gemini runtime credential → `DEGRADED`/`UNAVAILABLE`.
- Merely configuring a runtime never creates `READY` state.
- Never claim Gemini/Live/Deep Research was used without a provider receipt or retained execution evidence in Hermes logs.
- Never fall back to consumer web-session scraping to imitate an API.
- Never disable VAN audit/policy because a Google path is selected.

## References

- `docs/GOOGLE_INTELLIGENCE_MESH.md`
- `docs/SECURITY_POLICY.md`
- `registries/google_capabilities.json`
- `hermes/mcp/README.md`
- `hermes/skills/google-intelligence/SKILL.md`
