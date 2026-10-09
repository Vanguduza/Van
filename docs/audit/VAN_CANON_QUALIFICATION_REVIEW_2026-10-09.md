# VAN canon qualification and remaining handset inputs — 2026-10-09

## Outcome and source identity

The consolidated application is published on
codex/van-canon-consolidation-2026-10-08 at
4ad31883d57ab518ba9af414aa849db6e240eb71, draft PR #93.
Main remains 8eb1889822fc8a83f219977c15340172e16acd91.
This is source integration and qualification, not a main merge, signed owner
release, production gateway deployment or corrected handset installation.

The final remote refresh examined 54 remote-tracking refs. No additional branch
changes appeared during the final qualification period. The preceding branch
audit and source reconciliation covered Jev/OpenMuse, memory, cognitive work,
Candidate B, web acquisition, overlays, VATI and scoped security work. Some
historical branches were superseded or selectively reconciled; this does not
claim every historical branch was merged wholesale.

## Current changes

Command Centre is the launcher; manual owner pairing is removed from the app
flow. The approved Candidate B icon and an embedded source SHA are present.
The integrated source also reconciles schema version 55, browser owner control,
provider observation, immutable producer identity, mission terminal publication,
and the related native browser-services integration.

The latest runtime fixes bind automation verification to independently observed
run/input/artifact values, preserve browser task terminal states, hold a broader
unmeasured browser goal at VERIFYING/UNVERIFIABLE, preserve actual escalation
lease attribution, and keep advisory decisions from granting wider scope.
Real TLS 1.3 certificate rejection remains enforced; late certificate alerts
now become safe typed DIAL unavailability for ordinary and streaming requests.

## Qualification evidence

| Scope | Source / result | Limit |
| --- | --- | --- |
| Full backend | f68022fd: 4,929 passed, 1 failed, 142 skipped; 5,072 cases | Completed with the real late TLS alert defect |
| Focused DIAL verification after fix | 170 passed | Includes real positive mTLS and certificate rejection on GET/SSE, proxy, credential and attention contracts |
| Full contracts | f68022fd: 1,363 passed, 3 failed, 7 skipped, 2 xfailed | Two stale registries and one real branch-history gate |
| Refreshed registry contracts | 19 passed after both refreshes; latest r246 | Resolves both stale-source snapshot failures |
| Final Android | 4ad31883: compilation, 203 unit tests, assembly and lint passed | Debug build, not the owner release |
| Native Artemis adapter | 18 contract tests passed; fresh account/read matched the requested subscription | No new handset inference or acceptance claimed |
| Framework mechanics | 47 mechanics cases and 2 corrected CI path cases passed | Real branch admission remains failed |

The backend and full contract runs were completed on an immutable f68022fd
worktree. The later source changes are the small TLS error-handling fix and its
real transport tests, source-registry refreshes and append-only ledger rows.
The focused checks qualify those changes. A new whole-backend pass at 4ad31883
is not claimed.

## Final debug APK

Package: com.dial.van; version code 7; version 0.6.0-canon-rc1; ABI arm64-v8a.
The APK launcher matches the current source manifest:
com.dial.van.command.CommandCentreActivity.
BuildConfig contains the exact final source SHA. Signature inspection succeeds
and identifies the Android debug signer.

SHA-256:
e84eb8ed6e0cb923f229a80bf2aed96e2021dac648a48ef7a4fe07f812e755d6.
Size: 319,796,920 bytes. It was not installed. The historical debug gateway
profile does not bind this APK to the admitted owner core release.

## Direct Artemis

The installed adapter, launcher and all profile files match the consolidation
source byte for byte. The direct runtime now lives in
/home/ubuntu/.local/share/van/artemis-subscription/runtime-4ad31883d57ab51;
the owned current symlink was switched atomically, preserving its predecessor.
All 20 configured native roles and fallback entries select gpt-5.6-sol.
A fresh supported account/read returns ChatGPT,
tapiwaguduza@gmail.com, plan prolite.

Earlier retained real vision and native factory/tool/stream checks succeeded
through that account. This resume validated source equality and account binding;
it did not repeat those inference checks or claim current handset acceptance.
No login was copied, no API billing was enabled, and upstream native
driver/controller source was preserved. The launcher retains private wireless
ADB at loopback port 5039. Engineering used Commander and exact owner-direct
DIAL; Oracle Admin and the Hermes engineering queue were not used.

## Remaining review and runtime inputs

Project Truth is a real outstanding admission issue. Main does not contain the
framework or baseline registry. The existing Programme A baseline is already
an ancestor of main and the consolidation; no history reset is needed.
Draft PR #94 proposes adoption of the existing framework with unchanged
baselines, and contains an exact separate intake review manifest.
The final committed audit reports 214 findings. Prospective verification
against the unadopted framework base reports 791 findings. That result does
not constitute admission. No new authorization record was minted.

Repository tools/ci/README.md requires the owner's initial adoption review and
separate trusted authorization intake before the code it authorizes.
This packet does not approve either act or enable GitHub branch protections.

The existing production APK signing configuration/identity, core deployment
profile with actual HTTPS ingress capability and pinned CA, connectivity
verification anchors and one-use owner device provisioning handoff are not
bound to a final owner release packet. A bounded metadata search on dial-control
found only its Android debug keystore; the bounded core search found no release
profile or signing candidates. These searches do not claim every possible
storage location has been searched. Existing key/configuration locations are
needed; no new production trust or signing identity was created.

The existing van-gateway service is active on van-trading-core from its prior
runtime. It was not switched to this consolidation and its production database
was not migrated. DDS being unfinished did not block the builds or reversible
tests performed here.

At 04:23:29 UTC, 2026-10-09, the supplied wireless endpoint
10.66.66.2:35749 refused TCP connections from van-trading-core.
The previous bounded wireless tunnel is inactive and absent. Existing ADB
pairing keys were preserved. The current Wireless debugging connection
IP:port is needed to reconnect; the old pairing code is not a current connection
port.

The phone still has the rejected earlier APK. Current-canon physical acceptance
remains 0/826. This work does not grant trading authority, erase phone data,
replace PKI or report synthetic tests as physical acceptance.
