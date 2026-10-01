#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 2; }
[[ -f /etc/van-muse-sandbox.env ]] || exit 2
# shellcheck disable=SC1091
set -a; . /etc/van-muse-sandbox.env; set +a

for d in "$MUSE_SANDBOX_PROFILE_DIR" "$MUSE_SANDBOX_DOWNLOAD_DIR"; do
  [[ -d "$d" ]] || { echo "missing persistent Muse directory: $d" >&2; exit 3; }
  if ! mountpoint -q "$d"; then
    mount --bind "$d" "$d"
  fi
  mount -o remount,bind,rw,nosuid,nodev,noexec "$d"
  opts="$(findmnt -no OPTIONS --target "$d")"
  for required in rw nosuid nodev noexec; do
    grep -qw "$required" <<<"${opts//,/ }" || { echo "$d missing mount option $required: $opts" >&2; exit 4; }
  done
done
