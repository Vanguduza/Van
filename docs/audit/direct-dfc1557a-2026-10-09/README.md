# VAN direct continuation at dfc1557a — 9 October 2026

## Outcome

The confirmed application source remains **dfc1557ab99ad8d41cf84714e1bb671e89b045e6**. Direct Commander and owner-direct DIAL execution were available in this session. All five formerly skipped privileged firewall contracts now pass. The owned native Artemis subscription runtime has been rebound to verified files from this source, and the complete 826-case **native wireless** plan has been prepared.

Production is still unqualified. The active core gateway reports a much older deployed SHA, has mTLS disabled and lacks the selected production bindings. No owner release was built or installed in this continuation, and physical execution remains **0/826**.

The application review is [draft PR #93](https://github.com/Vanguduza/Van/pull/93), now advanced without a force push from 4ad31883 to dfc1557a. The separate initial Project Truth framework proposal remains [draft PR #94](https://github.com/Vanguduza/Van/pull/94) at 296d647d8755b6036ddb6bc66a5526b78db07029. Neither PR was merged.

This packet extends the [published source qualification and handoff](https://github.com/Vanguduza/Van/tree/c502cf7ab5c29b262719c4ed7eebf55ac3fe4647/docs/audit/final-dfc1557a). Its documentation commit is an evidence identity; it is not a replacement application SHA.

## Source and test evidence

| Scope | Confirmed evidence | Practical meaning |
|---|---|---|
| Application source | dfc1557ab99ad8d41cf84714e1bb671e89b045e6, clean checkout on dial-control | Current build/review input |
| Backend, published full run | 5,119 passed, five skipped, no failures | Retained qualification, not rerun here |
| Android, published qualification | 1,282 JVM and 203 app tests passed; debug APK and seven arm64 libraries verified | Build/source qualification; no physical instrumentation execution |
| Contracts, published full run | 1,521 passed, one Project Truth admission failure, five privileged skips | Original complete-run result remains preserved |
| Five privileged firewall contracts, direct follow-up | Five passed, zero failures/errors/skips, 33.22 seconds | Resolves those five source contract skips |
| Physical handset cases | 0/826 | No device acceptance claim |
| Owner registry | 42 feature groups, 105 functions, 78 surfaces, 432 endpoints, 251 schemas | Scope includes the complete current registry |

The selected firewall tests were run as root on dial-control at the exact dfc1557a checkout. They exercise nftables and real TCP/UDP probes inside disposable network namespaces: browser UDP/direct TCP refusal, UDP-only off-host DNS, loaded ruleset/qualifier behavior, missing-ruleset refusal, and refusal of a kernel reset as firewall evidence.

The host firewall was not changed. These five passing contracts do not prove production IPv4/IPv6 ordering, OCI security groups/routes, public HTTPS/WSS reachability, client-certificate refusal or the real per-profile browser boundary. The original full-suite result is retained separately rather than relabelled as a new complete run.

Receipts and the actual selected-test log/JUnit are included under `receipts/`.

## Current core observations

The direct read-only observation of van-trading-core at **09:19:34 UTC / 11:19:34 Harare** used the configuration predicates from the confirmed source. It exported only public selectors, booleans, status codes and hashes.

| Item | Actual observation |
|---|---|
| Host and architecture | van-trading-core, aarch64 |
| Active VAN process | van-gateway.service, python -m van_gateway.mtls.serve |
| Runtime directory | /home/ubuntu/.local/share/van/runtime/backend |
| Reported deployed SHA | 85ba485b2e375fcc777308492753a1a08c7f4307 |
| DEPLOYED_SOURCE.json | Absent |
| mTLS enabled | False |
| mTLS directory | Unconfigured; the empty selector is not a certificate directory |
| VAN listener | 127.0.0.1:8787 |
| Google environment file | /home/ubuntu/.config/van/google-workspace.env, zero bytes |
| Owner database | /home/ubuntu/.local/share/van/van_gateway.sqlite3, existing protected state |
| Gateway health subset | Authenticated loopback GET /health returned HTTP 200 |
| Narrow runtime/observability checks | Not dispatched: an unambiguous existing narrow credential for each required scope was unavailable |
| Production profile predicate | False |
| Owner signer / attestation root bindings | Absent from effective runtime settings |
| Core ingress VNIC observation | enp0s6 has 10.0.1.233/24 |
| DIAL overlay observation | wg-dial has 10.77.0.4/32 |
| Memory availability predicate | Passed |

A protected metadata search covered the VAN configuration/state roots on core, then followed the actual running unit and runtime defaults. It found the protected gateway environment and owner database. It did not locate a selected owner-core profile, keystore, core device CA, connectivity signer or installer bindings in those scoped locations. This is a scoped inventory, not a claim that such inputs cannot exist elsewhere.

Historical VAN certificates and a connectivity key selector exist on dial-control. The public server certificate names **62.83.35.103**, the historical dial-control gateway address. These were observed as historical inputs; they were not silently promoted into a production core profile. Private key contents were not exported.

The repository Actions secrets API reports zero secrets. The selected `van-owner-release` environment secrets route returns HTTP 404. This does not rule out another protected operator store; it establishes that the documented GitHub route did not supply release bindings in this session.

The active service, database, production firewall, signing identity and handset state were not changed.

## Canonical source staged on core

A separate, owner-owned candidate checkout is now present at:

`/home/ubuntu/work/van-owner-core-dfc1557a-20261009/source`

It is clean and detached at the exact application SHA. It was fetched directly from the public source repository and staged through the signed owner-direct DIAL execution flow. Its shallow history is sufficient for the candidate source tree; the full source-admission history remains available on dial-control.

The staging receipt explicitly records **STAGED_SOURCE_ONLY**, `deployed: false`, `active_runtime_changed: false`, `owner_database_changed: false` and `production_qualified: false`. Staging prepares the deployment input without turning the older service into a qualified current runtime.

## Native Artemis and the complete handset plan

The launcher `/home/ubuntu/.local/bin/van-artemis-mcp` now resolves through:

`/home/ubuntu/.local/share/van/artemis-subscription/runtime-dfc1557ab99ad8d`

All seven owned adapter files match dfc1557a byte-for-byte. The prior runtime is retained for a reversible rollback. Native vendor source and the existing owner login were not edited or copied.

The retained native subscription qualification binds **gpt-5.6-sol**, all 20 configured roles/fallbacks and **tapiwaguduza@gmail.com**. This continuation verifies unchanged adapter bytes and the source/runtime selection; it does not relabel the retained account/inference tests as fresh provider execution. No API-key billing route was introduced.

The current `tools/certification/artemis_acceptance.py` from dfc1557a prepared the wireless plan using the retained **actual native Artemis MCP schema discovery**, rather than a synthetic contract schema. Its recorded state is **NATIVE_PLAN_PREPARED_NOT_EXECUTED**.

| Plan binding | Value |
|---|---|
| Selected adapter | NATIVE_ARTEMIS_MCP_DIRECT_COMMANDER |
| DDS readiness required | False |
| Backend, product Hermes and ingress | van-trading-core |
| Native Artemis | dial-control |
| Transport | WIRELESS_ADB |
| Physical serial / raw model | RFCX2054F5W / SM-S928B |
| Package | com.dial.van |
| Coverage | 42 features, 105 functions, 78 surfaces, 826 cases |
| Source files hashed by plan | 955 |
| Canonical plan digest | b08e0e49bfbfbb9100d253b4d589d7d99905332eade8926817f7aa9905ade883 |
| Plan file SHA-256 | 97d2325c88686633eace7200716403aae5da3f60a092a2dd9f585a4245a333f5 |

The retained schema was captured on 8 October at the same native vendor runtime. Fresh native schema discovery and fresh handset transport/identity readbacks are pending for execution. The preparation did not start a native device task, contact the handset or dispatch a DDS/Hermes engineering operation.

The producer's default route without `--native-schema` is the explicitly retained legacy DDS adapter. That unselected preparation attempt is not the native acceptance plan and is excluded from this release packet. The included plan used `--native-schema receipts/native-artemis-schemas.json` and verified separate core-Hermes/control-Artemis roles and `dds_readiness_required: false`.

## Cloud setup: concrete pending review change

The published draft receipt records revision **14**, saved but not activated:

`7fe355d1-d734-4ad7-9bd4-954e1ee610c7~cecfgdraft_6ac5f2c2ead881909c4f334c58255a49`

The saved installer SHA-256 is:

`16243ab17f6e3273a26656afb75899155a4f226c05399830de2773bf429ec583`

The saved start-skill SHA-256 is:

`43ac6b86f44584b5bc4ed487c815cb7a1be78f898f5a79f41af75d20f67100ff`

The installer contains **zero references to DIAL_MCP_ACCESS_TOKEN**. The obsolete requirement must be removed in the settings review UI, followed by save and publish. No replacement secret is needed. Preserve the existing installer/start skill, repositories, network settings, unrelated requirements/secrets and connected owner-direct DIAL authentication.

This session exposes no draft-editing/publishing tool. Its browser inventory has no open settings review tab. No cloud save, requirement removal, publication or fresh-task restoration was performed here. The included review-change JSON records the exact intended change and the unperformed actions.

## Remaining concrete inputs and admission

The confirmed source already provides the owner-release compiler, APK provenance verification and signed installer path. It cannot invent the identity and ingress bindings these operations validate.

The next continuation needs the protected **locations or environment references**, not secret contents in chat, for:

- The existing owner APK keystore, alias and independently admitted signer fingerprint.
- The actual CORE_ONLY_V2 operator profile and exact authorized public core ingress scope, plus its public CA/SAN and connectivity key references.
- The existing enrollment/device-CA bindings, narrow runtime/observability/installer credentials, local core product-Hermes binding and actual provider configuration.

The selected core VNIC/interface and existing database path are already observed. They do not independently authorize public ingress or establish ownership of a signing identity.

For source admission, the current full contract run retains its Project Truth failure. The framework-only initial adoption is prepared in PR #94. **tools/ci/README.md lines 162–167** reserves its first landing to the owner's explicit act because the old base checker does not understand the new intake records. Generic continuation was not converted into an owner attestation for the uncovered history. No authorization record, baseline reset, code-owner approval or trusted receipt was fabricated.

The source history intake must be reviewed against the exact application SHA after initial framework adoption. Then the real deployment/network/provider acceptance must bind the selected configuration and owner APK bytes. Only a matching original **PRE_PHONE_PASS** permits the signed owner release installation and physical cases.

The cloud review page must also be opened or linked so the requested requirement removal and publication can be performed through the actual UI.

## Resource recovery and preservation

The exact-command broker initially refused preparation with ENOSPC on dial-control. There was roughly 10 GB of free space but fewer than 800 available inodes. Completed, task-owned Android `tmp` and `intermediates` directories were removed after confirming no active task builds.

The cleanup's whole-APK hash readback stalled in Commander's memory cgroup. Only that owned cleanup process was interrupted, and the operation was completed through owner-direct DIAL with streaming hashes. The retained debug APK hash matches its prior Android qualification receipt. Source, APK outputs, test reports/XML, generated provenance, voice acquisition and the Gradle cache were retained. The final recovery observation had 30,789 free inodes and about 11.9 GB available.

The preserved older debug APK is a historical qualification artifact, not a dfc1557a owner release candidate.

## Continuation sequence

1. Review and explicitly perform the initial framework adoption in PR #94, then complete exact-source history intake.
2. Bind the existing protected owner and CORE_ONLY_V2 operator inputs.
3. Use the staged exact source and existing deployment authority to prepare and qualify the core runtime, local product Hermes, providers, direct mTLS ingress and ordered IPv4/IPv6 firewall/OCI boundary. Preserve state and capture actual refusals/canaries.
4. Build and verify the owner-signed APK with source/configuration/trust provenance inside the signed bytes.
5. Obtain the matching original PRE_PHONE_PASS.
6. Refresh native Artemis schema discovery and paired wireless endpoint/physical serial/raw-model readbacks. Preserve existing ADB pairing and signer/state.
7. Use the signed installer, verify actual SESSION_ADMITTED, and execute all 826 native cases with independent evidence. Trading remains NEVER_ROUTABLE/demo; uncertain writes are inspected before any new action.
8. Remove the obsolete cloud requirement in its actual review UI, save/publish, and verify fresh-task restoration as a separate observation.

All engineering actions in this packet used Commander and/or direct owner DIAL. Oracle Admin and the Hermes engineering queue were not used.

### Evidence-branch authorization state

The new audit files are published as review work through the repository's documented uncovered-row path. The normal pre-commit hook remains enabled; its PROJECT_TRUTH_ALLOW_UNCOVERED option records the gap explicitly. This does not create an owner authorization or pass source admission. The evidence branch can include the hook's append-only LOCAL_CHANGE_LEDGER rows as well as this packet; application source stays dfc1557a, and main is unchanged.
