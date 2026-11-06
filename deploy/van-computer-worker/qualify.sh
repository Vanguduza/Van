#!/usr/bin/env bash
set -euo pipefail

IMAGE="${VAN_COMPUTER_WORKER_IMAGE:-van-computer:openmuse-r1}"
STATE_DIR="${VAN_COMPUTER_WORKER_STATE_DIR:-/var/lib/van/computer-worker}"
NAME="van-computer-qualify-$$"
VOLUME="van-computer-qualify-$$"
REPORT="$STATE_DIR/qualification.json"
WORK="$(mktemp -d)"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || { echo "refused: docker missing" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "refused: docker unavailable" >&2; exit 2; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "refused: image missing" >&2; exit 2; }

image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
docker volume create "$VOLUME" >/dev/null
docker create --name "$NAME" \
  --network none --read-only --user 1000:1000 --cap-drop ALL \
  --security-opt no-new-privileges --memory 512m --memory-swap 512m \
  --pids-limit 128 --cpus 1.0 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777 \
  --mount "type=volume,src=$VOLUME,dst=/workspace" \
  --workdir /workspace --env HOME=/workspace --env LANG=C.UTF-8 \
  --entrypoint /usr/bin/sleep "$IMAGE" infinity >/dev/null
docker start "$NAME" >/dev/null

inspect="$(docker inspect "$NAME")"
python3 - "$inspect" "$VOLUME" <<'PY'
import json, sys
item=json.loads(sys.argv[1])[0]
volume=sys.argv[2]
host=item["HostConfig"]; config=item["Config"]; mounts=item["Mounts"]
assert config["User"]=="1000:1000"
assert config["WorkingDir"]=="/workspace"
assert host["ReadonlyRootfs"] is True
assert host["Privileged"] is False
assert "ALL" in host["CapDrop"] and not host.get("CapAdd")
assert "no-new-privileges" in host["SecurityOpt"]
assert host["NetworkMode"]=="none"
assert int(host["Memory"])==536870912
assert int(host["MemorySwap"])==536870912
assert 0 < int(host["PidsLimit"]) <= 128
assert not host.get("Binds") and not host.get("Devices")
assert len(mounts)==1
m=mounts[0]
assert m["Type"]=="volume" and m["Name"]==volume and m["Destination"]=="/workspace" and m["RW"] is True
PY

# Root is actually read-only and /workspace is actually writable.
if docker exec "$NAME" sh -c 'touch /should-not-write' >/dev/null 2>&1; then
  echo "refused: container root filesystem is writable" >&2
  exit 2
fi
printf 'hello\n' | docker exec -i "$NAME" python3 /opt/van/files.py write --path /workspace/proof.txt >/dev/null
value="$(docker exec "$NAME" python3 /opt/van/files.py read --path /workspace/proof.txt)"
[ "$value" = "hello" ] || { echo "refused: workspace file round-trip failed" >&2; exit 2; }

# Persistence is the feature: recreate a container around the same volume and prove the
# workspace survived, while the root filesystem did not become storage.
docker rm -f "$NAME" >/dev/null
docker create --name "$NAME" \
  --network none --read-only --user 1000:1000 --cap-drop ALL \
  --security-opt no-new-privileges --memory 512m --memory-swap 512m \
  --pids-limit 128 --cpus 1.0 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777 \
  --mount "type=volume,src=$VOLUME,dst=/workspace" \
  --workdir /workspace --env HOME=/workspace --env LANG=C.UTF-8 \
  --entrypoint /usr/bin/sleep "$IMAGE" infinity >/dev/null
docker start "$NAME" >/dev/null
[ "$(docker exec "$NAME" python3 /opt/van/files.py read --path /workspace/proof.txt)" = "hello" ] || {
  echo "refused: workspace did not survive container recreation" >&2
  exit 2
}

docker exec "$NAME" python3 --version >/dev/null
docker exec "$NAME" node --version >/dev/null
docker exec "$NAME" git --version >/dev/null

install -d -m 0700 "$STATE_DIR"
tmp="$WORK/qualification.json"
IMAGE="$IMAGE" IMAGE_ID="$image_id" python3 - "$tmp" <<'PY'
import datetime, json, os, sys
payload={
  "schema_version":1,
  "status":"PASS",
  "qualified":True,
  "qualified_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "image":os.environ["IMAGE"],
  "image_id":os.environ["IMAGE_ID"],
  "network":"none",
  "user":"1000:1000",
  "read_only_root":True,
  "cap_drop":["ALL"],
  "no_new_privileges":True,
  "workspace_persistent":True,
  "docker_socket_mounted":False,
}
with open(sys.argv[1],"w",encoding="utf-8") as h:
  json.dump(payload,h,indent=2,sort_keys=True); h.write("\n")
PY
install -m 0600 "$tmp" "$REPORT"
printf 'PASS: %s\n' "$REPORT"
