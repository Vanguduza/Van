# Local candidate qualification — 24 October 2026

## Verdict

**29 tests passed, 0 failures, 0 errors, 0 skips. Source/routing stage only.**
This is not a completed REA investigation or a deployed/qualified Supabase system.

Base: `16af4b93ebbc1971b25626d8ba40d14ac3f80bdf`, draft VAN PR #102.
The two original Python files were materialized from connected GitHub content and verified against their exact Git blob SHAs before execution.

## Original failure and repairs

The original seven-test suite failed once: a substring assertion interpreted a nested `db` dependency as a new top-level PostgreSQL service. The corrected assertion examines only top-level service names; both-project structural verification finds eight project services and no added PostgreSQL service.

Other repaired defects: invalid DNS labels and numeric/type coercion; duplicate JSON keys; unbounded manifest reads; output overwrite/symlink behavior; unknown-host fallback; client-supplied tenant/forwarding headers; misleading HTTP-200 readiness; incorrect Auth external-URL and Storage signing configuration names. Auth configuration now names `API_EXTERNAL_URL` with `/auth/v1`, and Storage names `AUTH_JWT_SECRET` and the project-specific `POSTGREST_URL`. Shared image transformation remains disabled pending tenant-aware qualification.

## What ran

- Seven original tests, including the repaired structural assertion.
- Eighteen added validation, filesystem, deterministic two-project rendering, environment-contract and receipt-hash tests.
- Four actual local Nginx tests using six labelled HTTP stubs: both projects route only to their matching Auth/REST/Storage-labelled stub; foreign or unknown Host is rejected; spoofed tenant/forwarding headers are removed/replaced; readiness/Realtime/Functions remain HTTP 503.
- Python bytecode compilation and a separate YAML parse/structural check.

Environment: Python 3.13.5, Nginx 1.26.3, temporary loopback servers. The generated image remains the existing candidate tag, Nginx 1.27.5-alpine; that container image was not run. HTTP stubs neither authenticate users nor implement Supabase. No Supabase container, PostgreSQL database, RLS policy, OAuth flow, real JWT, or real user data participated.

## Native gates attempted

`dial_investigation_submit` for the pinned Gustavo source request returned `NATIVE_REA_INVESTIGATION_PORT_NOT_BOUND`. No native job/result receipt was created.

The estate status reported the `van-trading-core` identity reachable. A one-use grant for an exact **read-only** Python preflight was issued, but execution returned `QUALIFIED_REMOTE_ACTION_OWNER_REQUIRED`. The preflight did not run; available RAM/disk, container health and service definitions were not measured. Do not treat identity reachability or grant issuance as successful execution.

Work Tracker context acknowledgement returned a caller/receipt mismatch. No Work Tracker mutation was made; this repository report records the engineering outcome without inventing tracker acceptance.

## Next required evidence

The hard gates in README/INTEGRATION_GATES remain open: real REA results, qualified VM execution, whole-VAN backup restoration, database bootstrap, unique per-project database roles/key/issuer/realm isolation, actual cross-project token/RLS/Storage tests, shared-service integration, production API admission/TLS, boot-model reconciliation, and Nissan GTR cutover rehearsal. The draft must not be merged or deployed on this local result alone.

## Sources checked

- VAN pinned donor Compose `8eb1889822fc8a83f219977c15340172e16acd91`, Auth environment lines 110–155 and Storage environment lines 332–394.
- Supabase self-hosting Docker and API external-URL documentation; Nginx official request-processing documentation.
- Local exact test logs and source hashes in the accompanying artifacts.

## SHA-256 tested file identities

- `tools/render.py`: `b6889b9580f518304dd6d3a51c3a32de273e851f788b4613be722dfb057c0986`
- `tests/test_render.py`: `a76c55dfea2a6973474f970c995a450716edc34c00f347ee54d21b9809d43d26`
- `tests/test_hardening.py`: `eede0c901023c1b07e31244f5e8bbd0bb83835042af866785aa1ca5d07c95fe8`
- `tests/test_routing_local.py`: `429867a2da03892b6ac99dfa67cb8fe24f80e9730d44d515b1dc5bb20b140af4`
- `projects.rehearsal.json`: `b8ae6d7768cf189ce7a11c568d6431fb49ac9da947d1e074706aba07eca4d040`
- `README.md`: `177da79b36f51ce298079578975bcdc819fcf3b886d1cb0283531fb348408490`
