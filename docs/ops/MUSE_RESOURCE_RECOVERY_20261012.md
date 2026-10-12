# DIAL Muse host memory recovery — 2026-10-12

**Status:** implementation candidate; only owner-authorized typed estate operations may deploy. This is an additive host availability mitigation, not qualification of the Muse browser-approval product.

## Verified failure

At 2026-10-12, van-trading-core (2 vCPU, 12.2 GB RAM) authenticated SSH successfully but `dial-muse-health` hung under heavy memory/disk-I/O pressure. Observed initial load 26.6/32.5/37.0, memory PSI some ~35%, I/O PSI some ~99%, no swap, 627 processes and about 7.7 GB charged to `meta-muse-owner-browser.service`. No WireGuard fault was observed.

The owner-authorized typed estate lane ran read-only host diagnostics without reconfiguring the network. Temporary LZ4 zram /dev/zram0 (2 GiB, prio 150) reduced the measured 10s IO PSI from ~99% to ~1.4% and memory PSI ~35% to ~0.5%. Current-job Muse health and the Site feed returned GREEN again, and original owner browser/Xvfb/VNC/noVNC service PIDs were unchanged. Second 2 GiB zram device was activated for headroom. The full 4 GiB arrangement is transient until boot-time setup is installed.

## Proposed reboot persistence

Use `deploy/van-trading-core/muse_zram_relief.py` and the standalone `deploy/van-trading-core/systemd/dial-muse-zram-relief.service` installed as:

- `/usr/local/libexec/dial-muse-zram-relief.py`, root:root, 0755.
- `/etc/systemd/system/dial-muse-zram-relief.service`, root:root, 0644.

The helper handles only `/dev/zram0` and `/dev/zram1` with 2 GiB LZ4 each; it refuses unmanaged or mismatched devices, never swaps off a loaded system and does not touch VPN/routes/DNS/firewall/SSH/browser/Docker configurations or existing services.

With signed authorization and baseline evidence, `systemctl daemon-reload`, `systemd-analyze verify`, and `systemctl enable --now dial-muse-zram-relief.service` affect the new unit only. Verify `python3 ... --check`, `swapon --show`, the current source health, service PIDs and unchanged network state. Preserve reversible rollback instructions: disabling the new service prevents future boot activation but deliberately does NOT disable live zram while in use; live swapoff is permitted only after independent memory headroom qualification, never as automatic rollback.

## Qualification

1. Run `pytest -q tests/test_muse_zram_relief.py` and Python compilation.
2. Compare actual VM source hashes to this reviewed branch, deploy only with one-use signed owner estate operations.
3. Verify two swap devices active at 150 priority with 4 GiB total, significant fall in memory/IO PSI, and the canonical pinned Muse health route GREEN on repeated probes.
4. Check original browser/Xvfb/VNC/noVNC/watchdog/SSH/WireGuard identities and PIDs before/after; no protected service restart.
5. Run a harmless READ_ONLY NON_PROJECT Muse task with exact captured artifact and immutable binding; do not equate a GREEN health observation with functional execution.
6. Original Site's interactive Allow/Deny functionality, native Android installation, real provider control confirmation and independent Zuul/release acceptance remain separate gates. Full product qualification must not be claimed until those pass.
