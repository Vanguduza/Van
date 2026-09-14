# Gemini Provider — VAN via Hermes

Profile: **`van`**

## Canonical rule

Hermes profile `van` is the sole VAN agent runtime. VAN's primary reasoning and
orchestration model is **Claude Sonnet 5** through the Anthropic provider.
Gemini is a Google specialist provider beneath Hermes and MUST NOT silently
replace Sonnet 5 as VAN's primary model.

Android and VAN Gateway do not run a parallel Gemini agent loop.

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

For public Gemini APIs, use a Gemini/Google AI Studio or Google Cloud runtime
credential created under infrastructure owned/administered by that same Google
account. For account-native Google products, use the signed-in Google account
session directly. Never substitute an unrelated Google identity.

## Separation of credentials

| Credential plane | Used for | In LLM prompts? |
|---|---|---|
| Workspace OAuth | Gmail, Calendar, Drive, Contacts, Tasks | **Never** |
| Gemini runtime | Gemini, Live, Deep Research, Nano Banana, Veo via Hermes | **Never** |
| Google Cloud/service identity | Optional Notebook Enterprise / ADK/A2A services | **Never** |
| Consumer account session | Notebook, Mixboard, Stitch, Antigravity, Jules, Flow, AI Studio | Cookies/tokens are **never** copied into prompts |

Workspace OAuth MUST NOT be reused as a Gemini runtime credential. Consumer
browser cookies MUST NOT be exported into Hermes. Store runtime credentials in
host environment or a deployment secret manager; do not commit credential files.

## Invocation path

```text
Owner
  → VAN Gateway
  → Hermes profile van / Claude Sonnet 5
  → deterministic Google capability route
  → Gemini specialist provider or Google account-native tool
  → provenance/evidence
  → Hermes
  → VAN
```

## Capability roles

- **Gemini** — preferred Google reasoning and multimodal worker.
- **Gemini Live** — perception/conversation; it does not authorize mutations.
- **Deep Research** — cited investigator; its output is evidence, not Project Truth.
- **Nano Banana / Veo** — artifact generators behind Hermes media capabilities.
- **Notebook / Mixboard / Stitch / Flow / AI Studio** — account-native Google
  surfaces authenticated with the owner's Google account when no stable public
  automation API is available.

Consumer products such as Notebook, Mixboard, Stitch, Antigravity, Jules and Flow
are described in `docs/GOOGLE_INTELLIGENCE_MESH.md` and the associated skills.

## Routing policy

1. VAN general conversation, planning and orchestration stays on Claude Sonnet 5.
2. When a registered Google capability requires model inference, prefer Gemini.
3. When the Google product is account-native, use the owner's signed-in Google
   account session through the approved bridge rather than impersonating an API.
4. Deterministic Workspace CRUD continues through Workspace OAuth and the Google
   broker, not through Gemini free-form actions.
5. Gemini output returns to Hermes as evidence/artifacts and never gains authority.

## Policy and action classes

- Gemini inference alone is usually A1/A2.
- Provider output remains external/untrusted until validated.
- A3/A4 project work requires an explicit capability grant.
- A3/A4 project mutation requires current Project Truth SHA.
- A4 still requires explicit owner approval.
- A5 is always denied.

## Fail closed

- Missing Google-account-owned Gemini runtime credential → `DEGRADED`/`UNAVAILABLE`.
- Wrong/unverified Google principal → `AUTH_REQUIRED` or `UNVERIFIED`.
- Merely configuring a runtime never creates `READY` state.
- Never claim Gemini/Live/Deep Research was used without a provider receipt or retained execution evidence in Hermes logs.
- Never fall back to consumer web-session scraping to imitate an API.
- Never let Gemini become VAN's primary model because a Google capability was selected.
- Never disable VAN audit/policy because a Google path is selected.

## References

- `docs/GOOGLE_INTELLIGENCE_MESH.md`
- `docs/SECURITY_POLICY.md`
- `registries/google_capabilities.json`
- `hermes/mcp/README.md`
- `hermes/skills/google-intelligence/SKILL.md`
