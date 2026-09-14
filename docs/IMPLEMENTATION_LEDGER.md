# VAN Implementation Ledger

**Updated:** 2026-09-14  
**Product root:** `C:\Users\Admin\Documents\Van` → `https://github.com/Vanguduza/Van`  
**Reconstruction note:** Referenced checkpoints `v0.4.0-local` / `3f885cd…` / `8828c7e…` were **not recoverable**. Work proceeds as greenfield reconstruction under mission architecture (gateway → Hermes profile `van`).

## IMPLEMENTED (repository-side)

- Canonical docs: Project Truth, Security Policy, Visual Identity, Rive contract, external gates
- `visual-authority/rive_contract.json` + generated platform PNG asset pack + Canvas fallback path
- Backend gateway: enroll/revoke, signed commands, idempotency, stale-intent expiry, A4/A5 gates, prompt-injection reject, attention, briefing, reminders, notification intelligence (OTP suppress), Google token vault (encrypt/revoke/scrub), Hermes bridge, project truth gate, degraded registry, audit, event replay
- Hermes pack: profile `van` SOUL, skills, policy hook + tests, Bot Chat/councils docs, install/doctor scripts
- Android app `com.dial.van`: overlay service, Command Centre, encrypted queue, notification listener, share intent, voice/TTS cue clock hooks, biometric A4 gate, onboarding, Rive contract enums + Canvas fallback, degraded model; debug APK assembles; unit tests for contract/queue
- CI workflow, release metadata generator, scenario tests, speech-sync tests

## PARTIAL

- Google Workspace live HTTP transport (vault + fail-closed ready; live API needs credentials)
- Hermes live Bot Mode / councils / message_agent (pack + bridge ready; host unreachable)
- Artist-authored `.riv` (contract + Canvas fallback; Rive file external)
- Android lint/build certified in CI image (local lint/assemble exercised)

## EXTERNAL GATE

- Prior commit history recovery (if exists on another host)
- Live Hermes SSH (`dial-hermes-control` timed out from this workstation)
- Google OAuth consent + client secrets
- Separate Gemini API credential on Hermes
- Physical Samsung flagship certification + soak
- Owner visual acceptance of golden captures
- Signed production keystore / Play-adjacent signing (sideload debug APK available)

## BROKEN

- _(none currently known in reconstructed tree after lint fix)_

## MISSING

- Live Project Truth mounts for dial/dde/gtr/goat/aeci with real SHA capture
- Production signing + AAB
- Full 17-scenario live evidence pack (repo-side automated subset present)

## SUPERSEDED

- Embedded-Termux second agent (`van-agent` / S24 plan) where it conflicts with Hermes-owned execution
- Consumer Gemini web / Google One as Gemini credential
