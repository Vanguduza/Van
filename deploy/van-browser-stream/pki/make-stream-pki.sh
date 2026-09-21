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

PKI_DIR="${VAN_BROWSER_PKI_DIR:-/opt/van-browser-stream/pki}"
CONTROL_BIND="${VAN_BROWSER_CONTROL_BIND:?set the private VCN address the control agent binds to}"
DAYS="${VAN_BROWSER_PKI_DAYS:-397}"
WITH_FOREIGN_TEST_CERT=0
[ "${1:-}" = "--with-foreign-test-cert" ] && WITH_FOREIGN_TEST_CERT=1

#: The services allowed to call the agent. Adding a name here is granting a machine the
#: ability to drive the owner's browser; it is not a configuration convenience.
CLIENTS=(
  "browser-harness.trading-core.van.internal"
  "stagehand.trading-core.van.internal"
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
    -subj "/CN=$name/O=VAN/OU=trading-core"
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
    -subj "/CN=browser-harness.trading-core.van.internal"
  # Same common name as a real client on purpose: the agent must reject it on the chain,
  # not on the name, because a name is not a credential.
  openssl x509 -req -in foreign-client.csr -CA foreign-ca.crt -CAkey foreign-ca.key \
    -CAcreateserial -out foreign-client.crt -days 30 -sha256
  rm -f foreign-client.csr
fi

chown -R van-control:van-control "$PKI_DIR" 2>/dev/null || true
chmod 600 "$PKI_DIR"/*.key
chmod 644 "$PKI_DIR"/*.crt

echo
echo "Client key pairs are in $PKI_DIR. Move each one to the Trading Core service that owns"
echo "it and delete it here: a client key that stays on the server it authenticates to is a"
echo "key that anyone with this host has."
