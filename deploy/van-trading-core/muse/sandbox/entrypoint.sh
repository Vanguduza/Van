#!/bin/sh
set -eu
[ "$(id -u)" = "0" ] || {
  echo "Muse sandbox supervisor must be root inside gVisor" >&2
  exit 70
}
exec /usr/local/bin/van-muse-supervisor
