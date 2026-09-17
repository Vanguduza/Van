# Owner supply list — blocks v1.0

VAN remains `0.5.0-dev`. Do **not** tag `v1.0` until every item below is green with evidence.

## Must supply (owner / environment)

| # | Item | Why it blocks | How to unblock |
|---|---|---|---|
| 1 | Dedicated Gemini API/runtime credential | Live Hermes canary failed closed with `AUTH_REQUIRED`; no usable `GOOGLE_API_KEY` / `GEMINI_API_KEY` exists in the VAN profile | Create a Google-account-owned Gemini/AI Studio API key, store it only in the VAN/Hermes secret plane, then rerun the retained live canary and record `READY` evidence |
| 2 | Stable named Cloudflare Tunnel token + HTTPS hostname | Physical Android cannot use loopback gateway | Provision a named tunnel mapped to `http://127.0.0.1:8787`; run the fail-closed installer/public health canary |
| 3 | Physical Samsung device (USB) | No authorized host currently sees an ADB device | Plug in device, run `python tools/certification/device_cert_probe.py --install`, complete `docs/DEVICE_ACCEPTANCE_CHECKLIST.md` |
| 4 | Artist `.riv` matching `visual-authority/rive_contract.json` **or** explicit Canvas interim accept | No authored VAN `.riv` is present | Deliver `.riv` **or** owner-sign Canvas interim in visual acceptance matrix |
| 5 | Owner visual acceptance | EXTERNAL review gate | Sign `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` |
| 6 | Production keystore + `android/keystore.properties` | Release signing fails closed without owner signing material | Create/secure keystore; configure from `android/keystore.properties.example` (never commit secrets) |
| 7 | Cloud/Enterprise Google scope decision | Notebook Enterprise / ADK-A2A are unavailable without eligible Cloud runtime | Supply Cloud project/runtime if required for v1.0, otherwise explicitly exclude these optional capabilities from v1 scope |

Hermes host reachability (previously items 1–2) is **closed** — see below.

## Already closed (do not re-block)

- Google Intelligence Mesh ancestor `5b111e8` on `main` (re-verified as ancestor 2026-09-15)
- Live Hermes gate COMPLETE — certified on `dial-hermes-control` by commits `2656b93` (*Certify live VAN Hermes runtime*) and `1a0c85f` (*Close repository acceptance and Project Truth*), merged via `a578c12` (PR #3) — re-verified 2026-09-15 as ancestors of `origin/main` at `a994597`, with no Hermes commits landed after it. Ledger: `docs/PRODUCTION_ACCEPTANCE_LEDGER.md#live-hermes-certification-2026-09-15`. Hermes certification is owned by the ChatGPT run; this agent stood down from install/doctor at owner direction.
- Hermes host reachability from this workstation (former owner-supply items 1–2) — OCI `DIALRECOVERY` session + bastion allowlist (`66.9.173.77/32`) + `MANAGED_SSH` to `10.0.0.184` established and SSH login as `ubuntu` (sudo) confirmed live Hermes runtime under `/home/ubuntu/.hermes`. Evidence: `artifacts/release/hermes_recert_probe.json`. Note the `Bastion` instance-agent plugin on `dial-hermes-control` was `STOPPED` and had to be enabled before `MANAGED_SSH` would attach.
- Google readiness is evidence-scoped: `workspace_api` and Stitch are `READY`; other Google capabilities remain at their independently evidenced state
- Antigravity delegated worker authentication and live generation are certified
- Canonical GitHub Actions workflow `.github/workflows/van-ci.yml` is live and repeatedly green; no workflow-scope token is an owner-supply gate
- Project Truth mounts for van/dial/dde/gtr/goat/aeci (offline cache)
- Cross-project isolation + audit before/after tests
- Fail-closed: unsigned release, health honesty, Truth PUT auth, Google default unverified, Rive→Canvas
- Debug Android assemble/lint/unit tests

## READY rule

Never treat `CONFIGURED` as live. `READY` requires an evidence pointer starting with `live://`, `hermes://`, or `receipt://` recorded through the Google identity broker.
