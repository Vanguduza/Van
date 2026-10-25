# Better Remote Commander / VAN OCI

Target: existing van-trading-core, Ubuntu 24.04 ARM64 A1.Flex, 2 OCPU/12 GiB.

This additive change stages an outbound Better Remote Commander agent only. It does NOT deploy a relay, change OCI firewall rules or tunnels, restart any trading process, expose a new ingress port, replace the existing Desktop Commander, enable a new service, or grant the device agent administrative permissions.

## Immutable source and runtime
* Upstream: https://github.com/shahidx0x/better-remote-commander
* Git SHA: cbe511702dd0147650353c29ac6ab1decd8afda1
* Agent and shared packages: 2.0.2; frozen pnpm lockfile
* Node >=22.13, upstream Corepack pnpm 11.24.0
* New non-login service account: vanbrc; no sudo/docker/vati group; separately owned writable workspace

## Installation, owner-authorized target-host execution only

Run the exact scripts from a verified source checkout **on van-trading-core** with a valid owner-approved OCI Run Command / typed estate-admin authority, and only after assessing VM capacity:

    sudo bash deploy/van-trading-core/better-remote-commander/install-agent.sh --dry-run
    sudo bash deploy/van-trading-core/better-remote-commander/install-agent.sh --apply
    sudo bash deploy/van-trading-core/better-remote-commander/qualify-agent.sh

The installer checks hostname, ARM architecture, Node version, available memory and disk, pinned source SHA, package versions, privilege boundary and managed systemd unit collision. It adds van-brc-agent.service but does not enable or start it. It never modifies VATI, Supabase, live trading sessions, WireGuard, existing Commander access, or networking. GitHub CI passing is NOT evidence of VM installation.

## Activation requires an authenticated HTTPS relay

Configure a separate owner-approved BRC relay with HTTPS and OAuth before attempting device pairing. Create a root-owned mode-0600 /etc/van-brc/agent.env containing BRC_RELAY=https://YOUR_AUTHORIZED_DOMAIN and no password or API token. Run the pinned agent under vanbrc with the restricted allow-dir /var/lib/van-brc/work/Van, approve the displayed pairing code from the relay dashboard and then enable the agent:

    sudo systemctl enable --now van-brc-agent.service

Qualify by verifying actual remote device registration, OAuth login, a harmless remote file read and process command, per-call audit log and revocation. Do not report REMOTE_READY without evidence. The new systemd unit has NoNewPrivileges, empty capabilities, ProtectSystem, ProtectHome, MemoryMax=768M and CPUQuota=50%. File allow-dir does not constrain arbitrary shell arguments; the OS service account and systemd sandbox are critical.

## Rollback

    sudo systemctl disable --now van-brc-agent.service

Revoke the paired device via the authenticated relay. Retain VATI and the existing Commander configuration. No deletion is performed by the installer.

## Verified blocker, 2026-10-21

The DIAL repository's GitHub OCI recovery workflow is deliberately limited to recovery and is not a general installer. The available GitHub-hosted runners did not start a job; the self-hosted dial-control runner executed our read-only diagnostic but had no OCI_RECOVERY_* secrets, no OCI_INSTANCE_VAN_TRADING_CORE or OCI_RECOVERY_COMPARTMENT_OCID variables, no readable OCI config and no valid VAN SSH session. Its github-admin sudo grant is limited to a protected helper and must not be bypassed. A separately admitted, source-pinned owner OCI delivery operation and credentials need provisioning before VM installation.

Current evidence status: GITHUB_INSTALLER_PREPARED; VM_INSTALL_NOT_EXECUTED; PAIRING_NOT_STARTED.

## Verified installation and host qualification — 2026-10-25

**Actual VAN guest operations now complete; no longer a CI-only installation plan.**
After the ChatGPT custom-MCP administrator manually refreshed the approved
Global DIAL tool list, the read-only `dial_estate_exec_receipt` endpoint
returned the original 2026-10-24 dry-run outcome:
`action_902be279-a607-4a04-b942-17249f300a5a`,
`COMPLETED`, terminal=true, exit_code=0,
`BRC_INSTALL_PLAN=READY`.

With the newer pinned PR source at
`f1b33cf80a457db09470398f64dda1134a9b80ee` (installer blob
`521e6036928c7782a2293680f6353af66ad2cfe1`), the
independently authorized `--dry-run` also completed successfully:
`action_ad5aaaa3-c88f-42a6-af35-3a474c7b3046`,
terminal=true, exit_code=0, `BRC_INSTALL_PLAN=READY`,
`run_state=NOT_MODIFIED`.

An exact one-use signed `--apply` on `van-trading-core` then
**succeeded with an independent Root-signed terminal receipt**:
`action_5714b9d9-c8a0-4da0-9c3f-0c90af28995c`,
terminal=true, exit_code=0,
`BRC_AGENT_INSTALL=INSTALLED_NOT_PAIRED`,
`service_enabled=disabled`,
`BRC_TRADING_SERVICES=UNTOUCHED`.
The upstream packages were pinned to BRC 2.0.2 and compiled as `vanbrc`.

The separate pinned `qualify-agent.sh` completed with
`action_0aedb6a8-0c46-4c53-b58f-dc4f3bb3100a`,
terminal=true, exit_code=0:
`BRC_AGENT_PACKAGE=VERIFIED`,
`BRC_AGENT_SERVICE=INSTALLED_NOT_ENABLED`,
`BRC_OAUTH_PAIRING=NOT_STARTED`,
`BRC_MCP_REMOTE_ACCESS=NOT_VERIFIED`,
`BRC_QUALIFICATION=SOURCE_AND_HOST_ISOLATION_PASS`.
This is **installation and local isolation qualification only**, not proof
of a healthy, paired, remotely reachable MCP agent. No relay address or
OAuth device approval was supplied. Do not enable the service, write a
guessed relay URL, change firewall/VATI/production trading, or claim
`REMOTE_READY` until a separate approved HTTPS relay, OAuth pairing
and remote harmless-command tests are verified.

The prior 2026-10-21 blocker section above is retained as historical
evidence; its then-current "VM_INSTALL_NOT_EXECUTED" status is superseded
by these actual 2026-10-25 signed guest receipts.

