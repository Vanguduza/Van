#!/usr/bin/env bash
#
# P2-AND-016 — record which key signed the APK that leaves CI.
#
# The hypothesis for the owner's install failure is a signature mismatch between runs, and
# nothing in the run said what the signature was, so it could not be tested without the
# phone. This writes the certificate beside the APK and into the artefact: two runs can then
# be compared directly, and the owner can tell whether the build they are installing can
# upgrade the one they already have.
set -euo pipefail

apk_dir="${1:?usage: record_apk_signing_identity.sh <apk-dir> [output-file]}"
out="${2:-$apk_dir/signing-identity.txt}"

apk="$(find "$apk_dir" -maxdepth 1 -name '*.apk' | sort | head -n 1)"
if [ -z "$apk" ]; then
  echo "signing-identity: no APK in $apk_dir. The build step is supposed to have made one." >&2
  exit 1
fi

apksigner=""
for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}"; do
  [ -n "$sdk" ] || continue
  candidate="$(find "$sdk/build-tools" -maxdepth 2 -name apksigner 2>/dev/null | sort -V | tail -n 1)"
  if [ -n "$candidate" ]; then
    apksigner="$candidate"
    break
  fi
done
[ -n "$apksigner" ] || apksigner="$(command -v apksigner || true)"

if [ -z "$apksigner" ]; then
  echo "signing-identity: apksigner not found. keytool cannot read this APK: minSdk is 31," >&2
  echo "signing-identity: so the build signs with v2/v3 only and there is no JAR manifest" >&2
  echo "signing-identity: for keytool to print." >&2
  exit 1
fi

"$apksigner" verify --print-certs "$apk" > "$out"

# An empty or unexpected output would otherwise publish a file that looks like evidence and
# says nothing — the same shape as a search that silently matches nothing.
if ! grep -q 'SHA-256 digest' "$out"; then
  echo "signing-identity: apksigner printed no certificate digest for $apk." >&2
  cat "$out" >&2
  exit 1
fi

echo "signing-identity: $apk"
cat "$out"

# Character Forge M5 — bind the APK to the exact shipped Rive bytes when present.
manifest="visual-authority/rive/manifest.json"
rive_entry="assets/van.riv"
if unzip -l "$apk" "$rive_entry" >/dev/null 2>&1; then
  tmp_rive="$(mktemp)"
  trap 'rm -f "$tmp_rive"' EXIT
  unzip -p "$apk" "$rive_entry" > "$tmp_rive"
  rive_sha256="$(sha256sum "$tmp_rive" | awk '{print $1}')"
  echo "rive_sha256=$rive_sha256" >> "$out"
  if [ -f "$manifest" ]; then
    expected="$(python3 - "$manifest" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["rive_sha256"])
PY
)"
    if [ "$rive_sha256" != "$expected" ]; then
      echo "signing-identity: APK Rive SHA $rive_sha256 differs from release manifest $expected" >&2
      exit 1
    fi
  fi
elif [ -f "$manifest" ]; then
  echo "signing-identity: release manifest exists but $rive_entry is missing from APK" >&2
  exit 1
fi
