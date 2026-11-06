#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 2; }
[[ -f /etc/van-muse-sandbox.env ]] || exit 2
# shellcheck disable=SC1091
set -a; . /etc/van-muse-sandbox.env; set +a

PROFILE_IMG=/var/lib/van-muse-sandbox/profile.ext4
DOWNLOAD_IMG=/var/lib/van-muse-sandbox/downloads.ext4

ensure_fs() {
  local img="$1" target="$2" max_mib="$3" label="$4"
  local expected_bytes=$((max_mib * 1024 * 1024))
  install -d -m 0700 "$target"

  if [[ ! -f "$img" ]]; then
    truncate -s "$expected_bytes" "$img"
    mkfs.ext4 -q -F -m 0 -L "$label" "$img"
    chmod 0600 "$img"
  fi

  local observed_bytes
  observed_bytes="$(stat -c %s "$img")"
  [[ "$observed_bytes" -eq "$expected_bytes" ]] || {
    echo "$img size drift: expected=$expected_bytes observed=$observed_bytes; explicit migration required" >&2
    exit 3
  }

  if ! mountpoint -q "$target"; then
    mount -o loop,rw,nosuid,nodev,noexec "$img" "$target"
  fi
  mount -o remount,loop,rw,nosuid,nodev,noexec "$target"
  chown 10001:100 "$target"
  chmod 0700 "$target"

  local opts fstype
  opts="$(findmnt -no OPTIONS --target "$target")"
  fstype="$(findmnt -no FSTYPE --target "$target")"
  [[ "$fstype" == ext4 ]] || { echo "$target must be ext4, got $fstype" >&2; exit 4; }
  for required in rw nosuid nodev noexec; do
    grep -qw "$required" <<<"${opts//,/ }" || {
      echo "$target missing mount option $required: $opts" >&2
      exit 5
    }
  done
}

ensure_fs "$PROFILE_IMG" "$MUSE_SANDBOX_PROFILE_DIR" "$MUSE_SANDBOX_PROFILE_MAX_MIB" van-muse-profile
ensure_fs "$DOWNLOAD_IMG" "$MUSE_SANDBOX_DOWNLOAD_DIR" "$MUSE_SANDBOX_DOWNLOAD_MAX_MIB" van-muse-downloads
