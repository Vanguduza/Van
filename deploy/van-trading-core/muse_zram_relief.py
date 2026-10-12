#!/usr/bin/python3
"""Idempotent boot-time recovery for the memory-constrained VAN Muse host.

Only owns two LZ4 zram devices. Does not inspect/change application processes,
Muse sessions, VPN, firewall, routing, Docker, credentials, or browser profiles.
An existing unexpected zram layout is a refusal, never an automatic reset.
"""
from __future__ import annotations

import os
import subprocess
import sys

SIZE = 2 * 1024 * 1024 * 1024
DEVICES = ("/dev/zram0", "/dev/zram1")
BIN = {
    "modprobe": "/usr/sbin/modprobe",
    "zramctl": "/usr/sbin/zramctl",
    "mkswap": "/usr/sbin/mkswap",
    "swapon": "/usr/sbin/swapon",
}


class ZramRefusal(RuntimeError):
    pass


def run(*args: str) -> str:
    response = subprocess.run(list(args), text=True, capture_output=True, timeout=25, check=False)
    if response.returncode:
        raise ZramRefusal("command_failed:" + os.path.basename(args[0]))
    return response.stdout.strip()


def swap_names(output: str) -> set[str]:
    """swapon --show can expose optional columns; the device is column one."""
    return {line.split()[0] for line in output.splitlines() if line.strip()}


def observe_swaps() -> set[str]:
    return swap_names(run(BIN["swapon"], "--show", "--noheadings"))


def state_path(dev: str) -> str:
    return "/sys/block/" + os.path.basename(dev)


def verify_existing(dev: str) -> bool:
    path = state_path(dev)
    if not os.path.isdir(path):
        return False
    try:
        size = int(open(path + "/disksize", encoding="ascii").read().strip())
        algorithms = open(path + "/comp_algorithm", encoding="ascii").read().strip().split()
    except (OSError, ValueError) as exc:
        raise ZramRefusal("device_state_unreadable") from exc
    if size != SIZE or "[lz4]" not in algorithms:
        raise ZramRefusal("foreign_or_incorrect_zram_device:" + os.path.basename(dev))
    return True


def ensure_device(dev: str, active: set[str]) -> None:
    path = state_path(dev)
    if dev in active:
        if not verify_existing(dev):
            raise ZramRefusal("active_zram_missing:" + os.path.basename(dev))
        return

    # Do not overwrite data, swap signatures, or a pre-existing nonzero-sized
    # device whose ownership cannot be established.
    if os.path.isdir(path):
        current_size = int(open(path + "/disksize", encoding="ascii").read().strip())
        if current_size:
            raise ZramRefusal("unmanaged_existing_zram:" + os.path.basename(dev))
        run(BIN["zramctl"], "--algorithm", "lz4", "--size", "2G", dev)
    else:
        allocated = run(BIN["zramctl"], "--find", "--algorithm", "lz4", "--size", "2G")
        if allocated != dev:
            raise ZramRefusal("unexpected_created_zram_device")

    run(BIN["mkswap"], "-L", "dialmuse" + os.path.basename(dev)[4:], dev)
    run(BIN["swapon"], "--priority", "150", dev)


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        raise ZramRefusal("root_required")
    if argv not in ([], ["--check"]):
        raise ZramRefusal("arguments_forbidden")
    active = observe_swaps()
    if argv == ["--check"]:
        for dev in DEVICES:
            if dev not in active or not verify_existing(dev):
                raise ZramRefusal("expected_swap_not_active:" + os.path.basename(dev))
        print("DIAL_MUSE_ZRAM_READY", len(DEVICES), "devices", SIZE)
        return 0

    if not os.path.isdir("/sys/module/zram"):
        run(BIN["modprobe"], "zram", "num_devices=2")
    for dev in DEVICES:
        ensure_device(dev, active)
        active = observe_swaps()
    for dev in DEVICES:
        if dev not in active or not verify_existing(dev):
            raise ZramRefusal("swap_activation_not_verified")
    print("DIAL_MUSE_ZRAM_READY", len(DEVICES), "devices", SIZE)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (ZramRefusal, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        print("DIAL_MUSE_ZRAM_REFUSED:", type(exc).__name__, str(exc)[:150], file=sys.stderr)
        raise SystemExit(1)
