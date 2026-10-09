#!/usr/bin/env bash
#
# Rev 1.5 §13.3 — the private control-path PKI, and nothing else's.
#
# These credentials authenticate one machine to another. They are deliberately separate
# from every other credential in VAN:
#
#   owner device key        proves the owner's phone. Hardware-backed, never leaves it.
#   device HMAC             proves a command came from that phone.
#   BrowserStreamGrant      lets one device watch one session, for minutes.
#   Gateway internal token  lets Hermes call privileged Gateway routes.
#
# None of them may substitute for any other. The reason is stated as a property rather than
# a preference: compromising the service-to-service path must not yield owner authority, and
# compromising owner authority must not yield the ability to drive the browser directly.
# Sharing a CA between them would make both of those false at once.
#
# The client certificate common names are the identities the Browser Control Agent
# authorises against. There is no other identity source — the agent never reads a caller
# name from a request body, because a name a caller can write is a field, not an identity.
set -euo pipefail

CONTROL_BIND="${VAN_BROWSER_CONTROL_BIND:?set the private VCN address the control agent binds to}"
DAYS="${VAN_BROWSER_PKI_DAYS:-397}"
WITH_FOREIGN_TEST_CERT=0
INSTANCE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-foreign-test-cert) WITH_FOREIGN_TEST_CERT=1; shift ;;
    --instance) [ "$#" -ge 2 ] || { echo 'refused: missing profile instance' >&2; exit 2; }; INSTANCE="$2"; shift 2 ;;
    *) echo 'refused: unknown PKI option' >&2; exit 2 ;;
  esac
done
case "$INSTANCE" in
  public|owner) PKI_DIR="${VAN_BROWSER_PKI_DIR:-/etc/van-browser-stream/profiles/$INSTANCE/control-pki}"; CONTROL_USER="van-control-$INSTANCE" ;;
  "") PKI_DIR="${VAN_BROWSER_PKI_DIR:-/opt/van-browser-stream/pki}"; CONTROL_USER=van-control ;;
  *) echo 'refused: profile instance must be public or owner' >&2; exit 2 ;;
esac
[[ "$DAYS" =~ ^[0-9]+$ ]] && (( DAYS >= 1 && DAYS <= 3650 )) || { echo 'refused: bounded PKI validity required' >&2; exit 2; }
VAN_BROWSER_SELECTED_CONTROL_BIND="$CONTROL_BIND" python3 - <<'BIND'
import ipaddress, os
try:
    address = ipaddress.ip_address(os.environ['VAN_BROWSER_SELECTED_CONTROL_BIND'])
    assert address.version == 4 and address.is_private and not address.is_unspecified and not address.is_loopback and not address.is_multicast
except (ValueError, AssertionError):
    raise SystemExit('refused: literal private control bind required')
BIND

#: The services allowed to call the agent. Adding a name here is granting a machine the
#: ability to drive the owner's browser; it is not a configuration convenience.
CLIENTS=(
  "van-trading-core"
  "browser-harness.trading-core.van.internal"
  "stagehand.trading-core.van.internal"
  "browser-harness.browser-core.van.internal"
  "stagehand.browser-core.van.internal"
)

umask 077
mkdir -p "$PKI_DIR"
cd "$PKI_DIR"

if [ -f ca.crt ]; then
  echo "ca.crt exists; refusing to reissue. Re-keying this CA invalidates every client"
  echo "certificate at once, which is a decision, not a step. Remove it deliberately."
  exit 2
fi

echo "== private CA =="
openssl ecparam -name prime256v1 -genkey -noout -out ca.key
openssl req -x509 -new -key ca.key -sha256 -days "$DAYS" -out ca.crt \
  -subj "/CN=VAN Browser Control CA/O=VAN/OU=browser-stream"

echo "== server certificate for the control agent =="
openssl ecparam -name prime256v1 -genkey -noout -out agent.key
openssl req -new -key agent.key -out agent.csr \
  -subj "/CN=van-browser-control-agent/O=VAN/OU=browser-stream"
# The SAN is the VCN address and nothing else. A certificate that also named the public
# address would let a caller that reached the wrong interface still validate the host.
printf 'subjectAltName=IP:%s\nextendedKeyUsage=serverAuth\n' "$CONTROL_BIND" > agent.ext
openssl x509 -req -in agent.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out agent.crt -days "$DAYS" -sha256 -extfile agent.ext
rm -f agent.csr agent.ext

echo "== client certificates =="
for name in "${CLIENTS[@]}"; do
  openssl ecparam -name prime256v1 -genkey -noout -out "client-$name.key"
  openssl req -new -key "client-$name.key" -out "client-$name.csr" \
    -subj "/CN=$name/O=VAN/OU=van-browser-core"
  printf 'extendedKeyUsage=clientAuth\n' > "client-$name.ext"
  openssl x509 -req -in "client-$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out "client-$name.crt" -days "$DAYS" -sha256 -extfile "client-$name.ext"
  rm -f "client-$name.csr" "client-$name.ext"
  echo "  issued $name"
done

if [ "$WITH_FOREIGN_TEST_CERT" = 1 ]; then
  echo "== foreign test certificate =="
  # Signed by a CA this host has never heard of. qualify.sh presents it and requires the
  # agent to reject it; without one, the "refuses a foreign CA" check can only be reported
  # UNKNOWN, which is not a pass.
  openssl ecparam -name prime256v1 -genkey -noout -out foreign-ca.key
  openssl req -x509 -new -key foreign-ca.key -sha256 -days 30 -out foreign-ca.crt \
    -subj "/CN=Not The VAN Browser Control CA"
  openssl ecparam -name prime256v1 -genkey -noout -out foreign-client.key
  openssl req -new -key foreign-client.key -out foreign-client.csr \
    -subj "/CN=browser-harness.browser-core.van.internal"
  # Same common name as a real client on purpose: the agent must reject it on the chain,
  # not on the name, because a name is not a credential.
  openssl x509 -req -in foreign-client.csr -CA foreign-ca.crt -CAkey foreign-ca.key \
    -CAcreateserial -out foreign-client.crt -days 30 -sha256
  rm -f foreign-client.csr
fi

chown root:root "$PKI_DIR"/*.key
if id "$CONTROL_USER" >/dev/null 2>&1; then
  chown "$CONTROL_USER:$CONTROL_USER" "$PKI_DIR/agent.key" "$PKI_DIR/agent.crt" "$PKI_DIR/ca.crt"
else
  echo 'Role user is not installed yet; generated material remains root-owned for the isolated installer.'
fi
chmod 755 "$PKI_DIR"
chmod 600 "$PKI_DIR"/*.key
chmod 644 "$PKI_DIR"/*.crt

echo
echo "Client key pairs are in $PKI_DIR. Move each one to the van-browser-core service that owns"
echo "it and delete it here: a client key that stays on the server it authenticates to is a"
echo "key that anyone with this host has."
