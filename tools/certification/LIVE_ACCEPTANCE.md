# Live health evidence

For the selected owner-core deployment, run the separate pre-phone collector on
`van-trading-core` through its existing admitted deployment recipe:

```bash
python3 tools/certification/pre_phone_host_acceptance.py \
  --config-root <bound-owner-service-config> --state-root <bound-owner-service-state> \
  --android-profile <verified-release-packet>/android-owner-core.properties \
  --expected-sha <approved-clean-source-SHA> --out <recipe-evidence>/pre-phone-host.json
```

This selects no historical endpoint and takes no client-certificate key. It reads
the effective `google-workspace.env`, `gateway.env`, optional `trading-commander.env`,
then `owner-core.env` last, and verifies their hashes against the installed deployment
metadata before any request. It requires a dedicated single-scope `runtime` machine
credential in `VAN_INTERNAL_CONTROL_SCOPED_TOKENS` and a separate single-scope
`observability` credential (either scoped there or `VAN_OBSERVABILITY_TOKEN`). These
may be additional existing operator acceptance credentials; no enrollment credential
is selected. Missing, ambiguous or broad acceptance credentials block the collector.

The collector reads the core loopback health/runtime/automation/browser/operator
routes and the explicit private Hermes `/p/van/health`. It then connects with the
profile's CA and TLS 1.3, without a device certificate, to confirm that public health
and a WebSocket upgrade are refused. The latter is a negative admission observation;
a successful authenticated WSS session still belongs to the physical-phone run.
Receipts contain predicates, status codes and body hashes, never private file values
or health bodies. They retain the session proxy and refuse redirects. A missing route
or TLS-preserving transport fails rather than opening a different network lane.

`PASS_HOST_HEALTH_ONLY` covers exact installed bytes/configuration and these current
observations. It does not verify the governed ingress receipt, live firewall admission,
owner APK signer, fresh provider execution, or device provisioning. All of those fields
remain false. The admitted recipe must independently bind the ingress/source/recovery
receipt, observe private firewall/overlay lanes, verify the release packet, and execute
the service-specific functional canaries before enabling phone provisioning. Current
recorded canaries never substitute for fresh functional actions and independent readback.

The older collector below remains available for an already provisioned admitted
client identity. Supply its explicit endpoint and CA for an owner-core deployment;
its committed historical endpoint default cannot qualify the new profile.

Run `python3 tools/certification/run_live_acceptance.py --out <receipt.json>` from
an authorized runtime that can reach the actual services with TLS verification.
The command returns 2 when any prerequisite is missing or a check fails. It
never generates credentials, provisions devices, changes deployments, or runs
owner commands. Successful output is `PASS_HEALTH_ONLY`, with explicit false
fields for handset, owner-command and deployed-source verification.

Provide these existing scoped credentials through secure environment bindings:

| Variable | Purpose |
|---|---|
| `VAN_INGRESS_TOKEN` | Gateway `/health` ingress credential. |
| `VAN_LIVE_RUNTIME_TOKEN` | Existing gateway internal credential granted only the `runtime` scope. |
| `VAN_OBSERVABILITY_TOKEN` | Existing operator credential with the `observability` scope. |
| `VAN_HERMES_BASE_URL`, `VAN_HERMES_BEARER_TOKEN` | Actual Hermes service/profile access credential; HTTPS remotely, or its documented HTTP loopback listener on an already authorized host execution route. |
| `VAN_LIVE_CLIENT_CERT_FILE`, `VAN_LIVE_CLIENT_KEY_FILE` | Paths to an already admitted client certificate/key; no key is exported from a handset. |
| `VAN_LIVE_GATEWAY_BASE_URL`, `VAN_LIVE_GATEWAY_CA_FILE` | Optional selected gateway and matching public CA; an override requires its own CA file. |

With no gateway override, the runner uses the committed Android endpoint and its
public device CA. It retains the inherited proxy, refuses redirects and credential
bearing URLs, requires TLS 1.3 on the direct gateway link, and never accepts a
proxy certificate as the device CA. A TLS-intercepting proxy cannot establish this
pinned phone path; use an existing supported route that preserves end-to-end TLS.

The checks read actual gateway health, runtime status, automation/browser health,
operator health, and `/p/van/health`. Automation/browser readiness requires
`READY`, permitted production governance, configured egress, the recorded canary
pointer, a fresh verification timestamp (24 hours by default), and matching pinned
runtime versions. `--max-canary-age-seconds` selects the explicit age policy.
Receipts retain status codes and response hashes, not raw health bodies or tokens.
Some supported health handlers update their own degraded-state/audit observations;
these are bounded observations rather than a zero-write forensic read.

This evidence still needs the exact governed deployment receipt/current source
identity, a compatible APK, authorized physical-device provisioning, signed owner
command, actual Hermes/provider execution and readback, and owner-visible terminal
status before end-to-end acceptance can pass. A recorded canary is not a fresh
functional provider or browser action executed by this runner.
