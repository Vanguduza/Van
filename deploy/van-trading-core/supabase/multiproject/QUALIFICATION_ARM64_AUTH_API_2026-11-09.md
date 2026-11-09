# ARM64 two-project Auth/API isolation — 9 November 2026

**101/101 real-service checks passed on `van-trading-core`**, using a new, disconnected, disposable PostgreSQL 17.6 cluster with two independent project databases, two actual GoTrue 2.196.0 processes, two PostgREST 14.17 processes and two Nginx gateways. This closes the earlier amd64-only limitation for the core database/Auth/API rehearsal. It does not activate the existing live installation or qualify the remaining shared services.

## Actual tested boundaries

- Generated project Auth, REST and migration logins connected only to their own database. Each was rejected by first-match HBA when targeting the other project, the administrator database or a synthetic legacy database. REST could not become fixture administrator.
- Activation refused a missing HBA prefix, succeeded after the exact prefix was installed only in the temporary cluster, and refused replay. Duplicate bootstrap was rejected.
- Both actual GoTrue instances completed upstream migrations. The same email address had separate user IDs and passwords in the two Auth realms. Correct password login and token refresh succeeded.
- Foreign user JWTs, service-role keys, API keys, passwords and refresh tokens were denied. Tokens signed with the correct key but carrying the wrong issuer or audience were denied.
- An ordinary user could not access Auth administration; REST did not expose the Auth schema. RLS hid a second user's row and rejected a foreign-owner insert, while an in-project service role could access both synthetic rows.
- Wrong Host headers and spoofed routing headers could not change databases. Forty concurrent project requests remained isolated.
- Unqualified Storage, Realtime, Edge, readiness and OAuth callback routes remained closed with HTTP 503.
- The synthetic legacy sentinel and database ACL were unchanged. The host launcher separately confirmed the real eleven live Supabase containers retained their IDs/start times and healthy state.

## Exact execution and provenance

The source generators `tools/bootstrap.py` and `tools/render.py` were unchanged from candidate `b46c978fbe73cca1340f010ab19c808f02d39b05`. `tests/rehearse_native.py` changed only its report: it records actual `platform.machine()` and replaces the old hard-coded untested-ARM64 label with the continuing live-donor/deployment exclusion. Every original assertion remained enabled.

The native report records `runtime_architecture=aarch64`, PostgreSQL `17.6`, 101 checks, no error and cleanup complete. Managed build job `djob_59c051c298a512a60eb3dcc7` succeeded with exit zero; native job `djob_85a5103ec1257ee31d8343ba` succeeded with exit zero in 22.18 seconds. The fixture container used ordinary UID/GID `100:101`, network mode `none`, no published ports, a read-only root filesystem, 768 MiB memory, 0.7 CPU, dropped capabilities and no-new-privileges.

The test image derived from the exact already-installed ARM64 PostgreSQL image. GoTrue binary/migrations and PostgREST binary came from the exact installed image versions, with immutable image and executable hashes retained. Python 3.12.16-r0 and Nginx 1.28.3-r7 were installed only in the test image from the signed Alpine repository. Nginx here is a rehearsal binary, not proof of the candidate production Nginx image. The existing PostgREST image uses glibc; its library directory and loader were copied from a new stopped image-only container and mounted read-only into the fixture. Their 218 file hashes are retained. There were no live DB mounts, host ports or production credentials.

All project secrets, users and row data were generated inside the fixture and discarded. The original rehearsal stopped all child services and removed its temporary cluster; the host launcher then removed the container. The test image and copied runtime libraries were deleted afterward. Logs, exact source, image/package/library hashes, the container boundary, native results and cleanup results are under `evidence/2026-11-09-arm64-auth/`. Source/build files are evidence of this exact test, not production-admitted images.

## Fresh production execution blocker

A separate **read-only** attempt was made through the original signed Global DIAL Root route to determine whether the existing platform-admin SQL principal could protect session logging and inspect HBA rules. Root issued an exact one-use signed grant at control epoch 114. The actual executor then returned **`QUALIFIED_REMOTE_ACTION_OWNER_REQUIRED`**, before SQL execution. No privilege proof or production SQL result was obtained, and this command was not rerouted through another connector. The non-secret original response is retained in `evidence/2026-11-09-business-http/native-root-readonly-probe-refusal.json`.

This current execution-owner refusal is distinct from the earlier live-canary safety refusal; neither has been cleared by the fixture results. No production role, HBA, database, Auth provider, unit or service was changed. Root signing and terminal execution are separate stages.

## Remaining scope

This run and the separate positive GTR business HTTP run are complementary isolated tests. The GTR business schema was not installed in these two Auth projects, and the business run used synthetic JWTs rather than these GoTrue tokens. Combined end-to-end acceptance on a restored GTR project remains to be demonstrated.

Shared Storage, Realtime, Edge, Supavisor, Studio/Meta and the complete canonical lifecycle remain unqualified on ARM64 in this combined topology. Real hosted rows/Auth/session/Storage/R2/Edge/provider-secret recovery, payment providers, four hosted cron jobs, active-writer backup/rollback and production load also remain outstanding. The 77 historical authenticated DML differences are not automatically restored or declared resolved.

**Production remains undeployed; PR #102 remains draft/unmerged.** A currently qualified remote execution owner, reconciled original canary refusal, exact source/Zuul/release acceptance and genuine preservation/recovery proof are still required before live activation or customer-data cutover.
