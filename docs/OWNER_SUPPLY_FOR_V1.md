# Owner supply list — blocks v1.0

VAN remains `0.5.0-dev`. Do **not** tag `v1.0` until every item below is green with evidence.

## Must supply (owner / environment)

| # | Item | Why it blocks | How to unblock |
|---|---|---|---|
| 1 | Google Workspace live canaries | Mesh is `CONFIGURED` from Hermes attestation, not `READY` | Prove Gmail/Calendar/Drive/Contacts/Tasks via refresh→access + revoke; record `live://…` / `receipt://…` evidence |
| 2 | Gemini runtime live canary | Same: `CONFIGURED` ≠ `READY` | Hermes Gemini turn with retained receipt → mark READY |
| 3 | Antigravity generation quota | Auth OK; live generation `CAPACITY_LIMITED` | Provider quota recovery or accept Jules-only development until then |
| 4 | Physical Samsung device (USB) | `adb devices` empty | Plug in device, run `python tools/certification/device_cert_probe.py --install`, complete `docs/DEVICE_ACCEPTANCE_CHECKLIST.md` |
| 5 | Artist `.riv` matching `visual-authority/rive_contract.json` **or** explicit Canvas interim accept | No `van.riv` / `van_runtime.riv` in APK assets | Deliver `.riv` **or** owner-sign Canvas interim in visual acceptance matrix |
| 6 | Owner visual acceptance | EXTERNAL review gate | Sign `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` |
| 7 | Production keystore + `android/keystore.properties` | Release signing fail-closed without it | Create keystore; copy from `android/keystore.properties.example` (never commit secrets) |
| 8 | GitHub token with `workflow` scope | Cannot install `.github/workflows/ci.yml` | `gh auth refresh -h github.com -s workflow` then `python tools/ci/install_github_workflow.py --apply --commit-push` |
| 9 | Cloud/Enterprise Google (optional for v1.0 if unused) | `gemini_notebook_enterprise` / `a2a_adk` UNAVAILABLE | Supply Cloud project + runtime **or** formally exclude from v1.0 scope |

Hermes host reachability (previously items 1–2) is **closed** — see below.

## Already closed (do not re-block)

- Google Intelligence Mesh ancestor `5b111e8` on `main` (re-verified as ancestor 2026-09-15)
- Live Hermes gate COMPLETE — certified on `dial-hermes-control` by commits `2656b93` (*Certify live VAN Hermes runtime*) and `1a0c85f` (*Close repository acceptance and Project Truth*), merged via `a578c12` (PR #3). Ledger: `docs/PRODUCTION_ACCEPTANCE_LEDGER.md#live-hermes-certification-2026-09-15`. Hermes certification is owned by the ChatGPT run; this agent stood down from install/doctor at owner direction.
- Hermes host reachability from this workstation (former owner-supply items 1–2) — OCI `DIALRECOVERY` session + bastion allowlist (`66.9.173.77/32`) + `MANAGED_SSH` to `10.0.0.184` established and SSH login as `ubuntu` (sudo) confirmed live Hermes runtime under `/home/ubuntu/.hermes`. Evidence: `artifacts/release/hermes_recert_probe.json`. Note the `Bastion` instance-agent plugin on `dial-hermes-control` was `STOPPED` and had to be enabled before `MANAGED_SSH` would attach.
- Hermes-hosted Google auth imported as `CONFIGURED` (not READY)
- Project Truth mounts for van/dial/dde/gtr/goat/aeci (offline cache)
- Cross-project isolation + audit before/after tests
- Fail-closed: unsigned release, health honesty, Truth PUT auth, Google default unverified, Rive→Canvas
- Debug Android assemble/lint/unit tests

## READY rule

Never treat `CONFIGURED` as live. `READY` requires an evidence pointer starting with `live://`, `hermes://`, or `receipt://` recorded through the Google identity broker.
