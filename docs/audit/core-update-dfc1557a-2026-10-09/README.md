# VAN Trading Core source update — 9 October 2026

## Completed outcome

The owner-authorized DIAL Admin operation updated the live **van-trading-core** VAN gateway from `85ba485b2e375fcc777308492753a1a08c7f4307` to canonical application source **`dfc1557ab99ad8d41cf84714e1bb671e89b045e6`**.

The canonical installer completed at 10:24 UTC (12:24 Africa/Harare). Independent readback at 10:31 UTC confirmed the exact source, pinned interpreter, running process, authenticated health response and preserved configuration. This supersedes the earlier direct-continuation packet's observation that dfc1557a was only staged.

Engineering used the supported exact-command DIAL Admin prepare/authorize/run flow. No Oracle Admin host or Hermes engineering queue was used. No handset operation or production trading action was performed.

## Verification

| Check | Observed result |
|---|---|
| Canonical installer | Exit 0; PASS van_gateway_preflight; PASS van_gateway_http_ready |
| Deployment provenance | Repository SHA and expected SHA both dfc1557a; source clean |
| Deployed runtime manifest | All 632 files matched their recorded hashes |
| Dependency environment | Exact requirements.lock; pip consistency check passed |
| Running process | PID 3347293; expected locked Python, VAN entry point, runtime working directory and PYTHONPATH |
| Service | Active/running; independent readback restart count 0 |
| Authenticated loopback /health | HTTP 200 |
| Same request without ingress token | HTTP 401 |
| Database | Schema 30 → 55; SQLite quick_check ok |
| Existing configuration | Both actual configuration files unchanged byte for byte |
| Previous runtime | Retained at runtime.previous; SHA 85ba485b |
| Physical cases | 0/826 |
| Full production qualification | Pending; live_qualified remains false |

The dependency lock SHA-256 is `808e30cb3359c908597bab5fc49797a23bf1748d12831b6200f9505a005b40da`. The serving Python is in the immutable environment named by that digest. The previous serving interpreter was not modified by dependency installation.

The process has the existing loopback listener at **127.0.0.1:8787**. This HTTP readiness observation does not qualify public ingress, device mTLS, providers, the owner APK or handset acceptance.

## Database and recovery evidence

Before modifying the live runtime, the exact new Store migration was run against a protected online backup of the owner database. It advanced schema 30 to 55 and retained the row counts and original column values of all **99 existing tables**. SQLite integrity passed. A second migration run made no changes.

After that copy check, the updater acquired its own exclusive update lock and the canonical install lock, copied the old runtime, configuration and unit into a protected checkpoint, stopped only van-gateway.service, and took a consistent quiesced database backup. It preserved the older runtime.previous before calling the canonical installer.

The protected checkpoint is:

`/home/ubuntu/.local/share/van/checkpoints/pre-dfc1557a-r285`

Its database, configuration and runtime contents remain on core. Owner database rows, configuration secrets, approval nonces and private keys are not in this evidence packet.

The live migration completed at schema 55 with no reduction in the original table row counts. The owner database was not replaced or restored. A schema-30 runtime cannot be assumed to support the schema-55 database; this checkpoint is protected recovery evidence, not a claim that automatic rollback is qualified.

## Exact source and repository state

The deployed application source is [dfc1557a](https://github.com/Vanguduza/Van/tree/dfc1557ab99ad8d41cf84714e1bb671e89b045e6). The installer used is [tools/runtime/install_van_gateway_service.sh at that source](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/tools/runtime/install_van_gateway_service.sh).

This packet adds runtime evidence. It does not change the application source identity, forge historical authorizations or declare Project Truth admission GREEN.

The fresh GitHub readback in receipts/repository-state.json records PR #93 at dfc1557a and PR #94 at 296d647d. Both remain open drafts and unmerged. Deployment of the exact reviewed source is completed separately from merging those review branches into main.

## Remaining acceptance boundary

DIAL Admin reachability and privileges are available and were sufficient for this authorized core update. The remaining work is not an admin-access blocker.

Full owner release acceptance still needs the existing owner keystore/alias and admitted signer binding; the actual CORE_ONLY_V2 configuration and authorized public core ingress scope; the corresponding CA, enrollment, connectivity and narrow installer/observability/runtime references; actual local core product-Hermes/provider bindings; and exact-source admission. These identities and bindings were not fabricated by granting admin execution.

The native Artemis subscription runtime on dial-control remains bound to dfc1557a, gpt-5.6-sol and the existing tapiwaguduza@gmail.com subscription selection. The complete native wireless 826-case plan remains prepared. DDS readiness is not required by that selected route. Fresh native schema and paired wireless identity readbacks are still needed when execution is admitted.

The original matching PRE_PHONE_PASS remains required before the signed owner release installation and physical cases. This source update does not issue that receipt or claim a latest APK was installed.

The saved cloud setup remains a separate pending UI operation: remove the unused DIAL_MCP_ACCESS_TOKEN requirement in its actual settings review page, save and publish. No replacement secret is required.

## Receipt provenance

The accompanying JSON receipts record dependency and migration-copy preparation (r283), the canonical live installation and checkpoint (r285), independent live readback (execution r293; core receipt filename retained as r291), listener scope and fresh repository state.

The normal Project Truth hook remains enabled for publication. The documented uncovered-review path records missing admission coverage explicitly; it does not create an owner authorization record or trusted source attestation.
