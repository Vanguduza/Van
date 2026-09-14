# Gemini Provider — VAN via Hermes

Profile: **`van`**

## Separation of credentials

Gemini uses a **separate runtime API credential** — not Google OAuth workspace tokens, not consumer Gemini web session scraping, not Google One subscription UI automation.

| Credential | Used for | In LLM prompts? |
|---|---|---|
| Google OAuth (gateway) | Gmail, Calendar, Drive API | **Never** |
| Gemini API key / service account (runtime env) | Gemini model calls via Hermes | Key never echoed; routing only |

Store Gemini credential in host env (e.g. `GEMINI_API_KEY` or deployment secret manager). Do not commit `gemini.env` (see repo `.gitignore`).

## Invocation path

```text
Owner → gateway → Hermes profile van → Gemini provider route → response → Van
```

Hermes owns the call. Android does not call Gemini directly. No parallel on-device Gemini agent loop.

## When to prefer Gemini

Prefer Gemini routing (still through Hermes) for:

- Google API / Workspace documentation interpretation
- Google-cloud architecture questions
- Multimodal tasks when gateway attaches attested media (not raw OAuth-backed fetches in prompt)

Use other Hermes-configured models when better suited; preference is not exclusivity.

## Policy and action classes

- Gemini inference alone is typically A1/A2 (read/analysis) depending on external data attached
- Acting on Gemini output (send email, write repo) still requires appropriate A3/A4 gates and Project Truth checks
- Gemini suggestions inside untrusted documents remain untrusted

## Fail closed

- Missing Gemini credential → report `DEGRADED`; do not fake Gemini-specific answers
- Do not claim Gemini was used without provider receipt in Hermes logs
- Do not disable audit/policy because Gemini path is selected

## References

- `docs/SECURITY_POLICY.md` — secrets
- `hermes/mcp/README.md` — `gemini` server
- `hermes/skills/research/SKILL.md`
