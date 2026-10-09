#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${VAN_COMPUTER_WORKER_IMAGE:-van-computer:openmuse-r1}"
STATE_DIR="${VAN_COMPUTER_WORKER_STATE_DIR:-/var/lib/van/computer-worker}"

command -v docker >/dev/null 2>&1 || {
  echo "refused: docker is not installed" >&2
  exit 2
}
docker info >/dev/null 2>&1 || {
  echo "refused: docker daemon is unavailable" >&2
  exit 2
}

install -d -m 0700 "$STATE_DIR"
docker build --pull=false --tag "$IMAGE" "$ROOT/services/van_computer_worker"

image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
case "$image_id" in
  sha256:*) ;;
  *) echo "refused: Docker returned an unexpected image id" >&2; exit 2 ;;
esac

# A rebuild invalidates the old receipt before qualification starts.
rm -f "$STATE_DIR/qualification.json"
printf 'built %s as %s\n' "$IMAGE" "$image_id"
printf 'next: sudo VAN_COMPUTER_WORKER_IMAGE=%q VAN_COMPUTER_WORKER_STATE_DIR=%q bash %q\n' \
  "$IMAGE" "$STATE_DIR" "$ROOT/deploy/van-computer-worker/qualify.sh"
