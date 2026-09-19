#!/usr/bin/env bash
#
# P2-AND-016 — make the debug APK's signing identity the owner's choice rather than the
# runner's accident.
#
# Android generates a debug keystore on first use and keeps it in ~/.android. A CI runner is
# a fresh machine every time, so every run produced a different key, and two consequences
# follow that matter for Gate 14: an APK from one run cannot upgrade an APK from another,
# and any VAN already installed refuses the new one on a signature mismatch. The owner's
# first sideload failed with a bare "App not installed"; that is one of the shapes it takes.
#
# If the owner supplies VAN_DEBUG_KEYSTORE_BASE64 the build uses their key and every run
# produces an upgradable APK. If they have not, this says so plainly rather than leaving the
# build to look identical either way. It never invents a key: a keystore committed to the
# repository would let anyone who has the repository sign an upgrade over the owner's
# install, and an app holding a notification-listener grant and a token vault is not one to
# do that to.
set -euo pipefail

target="${1:-$HOME/.android/debug.keystore}"

if [ -z "${VAN_DEBUG_KEYSTORE_BASE64:-}" ]; then
  echo "debug-keystore: none supplied. This build signs with a keystore generated on this"
  echo "debug-keystore: machine, so its APK cannot upgrade one from any other run, and an"
  echo "debug-keystore: existing VAN install will refuse it on a signature mismatch."
  echo "debug-keystore: set the VAN_DEBUG_KEYSTORE_BASE64 secret to fix that."
  exit 0
fi

mkdir -p "$(dirname "$target")"
tmp="$target.incoming"
trap 'rm -f "$tmp"' EXIT

printf '%s' "$VAN_DEBUG_KEYSTORE_BASE64" | base64 -d > "$tmp"

# Android's debug signing config is not configurable: it opens the store with password
# "android" and reads the alias "androiddebugkey". A keystore that does not answer to those
# would fail at packaging time, several minutes later, with an error about the key rather
# than about the secret. Refusing here names the real cause.
if ! keytool -list -keystore "$tmp" -storepass android -alias androiddebugkey >/dev/null 2>&1; then
  echo "debug-keystore: refused. Android's debug signing config requires a keystore whose" >&2
  echo "debug-keystore: store password is 'android' and which holds the alias" >&2
  echo "debug-keystore: 'androiddebugkey'. The supplied secret does not open that way, and" >&2
  echo "debug-keystore: signing with the runner's own key while reporting the owner's is" >&2
  echo "debug-keystore: worse than not having one." >&2
  exit 1
fi

mv "$tmp" "$target"
trap - EXIT
echo "debug-keystore: restored from VAN_DEBUG_KEYSTORE_BASE64 into $target"
