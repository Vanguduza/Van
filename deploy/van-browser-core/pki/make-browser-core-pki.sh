#!/usr/bin/env bash
#
# Owner decision 2026-09-29 §1 — the van-browser-core edge PKI, and nothing else's.
#
# A private CA used only for the mTLS edge in front of the van-browser-core workers. It is
# deliberately separate from the trading bridge PKI (deploy/van-trading-core/pki), the
# Browser Stream Host control PKI (deploy/van-browser-stream/pki), the owner device root,
# the device HMAC and the Gateway internal control token. Sharing a CA with any of those
# would let a compromise of the browser zone mint an identity another zone trusts.
#
# The CA issues exactly the client identities listed in CLIENTS. Chain validation at the
# edge is therefore the caller check: a certificate from this CA *is* one of these callers.
set -euo pipefail

PKI_DIR="${VAN_BROWSER_CORE_PKI_DIR:-/etc/van-browser-core/pki}"
EDGE_BIND="${VAN_BROWSER_CORE_EDGE_BIND:?set the private overlay address the edge binds to}"
DAYS="${VAN_BROWSER_CORE_PKI_DAYS:-397}"
WITH_FOREIGN_TEST_CERT=0
[ "${1:-}" = "--with-foreign-test-cert" ] && WITH_FOREIGN_TEST_CERT=1

case "$EDGE_BIND" in
  0.0.0.0|::|127.*|localhost|"") echo "refused: VAN_BROWSER_CORE_EDGE_BIND must be a specific private address" >&2; exit 2 ;;
esac

#: Callers admitted to the edge. Adding one grants a machine the ability to drive the
#: browser zone; it is an owner-visible decision, not a convenience.
CLIENTS=(
  "van-gateway.van-browser-core-client.van.internal"
)

umask 077
mkdir -p "$PKI_DIR"
cd "$PKI_DIR"

if [ -f ca.crt ]; then
  echo "ca.crt exists; refusing to reissue. Re-keying invalidates every caller at once." >&2
  exit 2
fi

openssl ecparam -name prime256v1 -genkey -noout -out ca.key
openssl req -x509 -new -key ca.key -sha256 -days "$DAYS" -out ca.crt \
  -subj "/CN=VAN Browser Core Edge CA/O=VAN/OU=van-browser-core"

openssl ecparam -name prime256v1 -genkey -noout -out edge.key
openssl req -new -key edge.key -out edge.csr -subj "/CN=van-browser-core-edge/O=VAN/OU=van-browser-core"
printf 'subjectAltName=IP:%s\nextendedKeyUsage=serverAuth\n' "$EDGE_BIND" > edge.ext
openssl x509 -req -in edge.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out edge.crt -days "$DAYS" -sha256 -extfile edge.ext
rm -f edge.csr edge.ext

for name in "${CLIENTS[@]}"; do
  openssl ecparam -name prime256v1 -genkey -noout -out "client-$name.key"
  openssl req -new -key "client-$name.key" -out "client-$name.csr" -subj "/CN=$name/O=VAN/OU=van-browser-core-client"
  printf 'extendedKeyUsage=clientAuth\n' > "client-$name.ext"
  openssl x509 -req -in "client-$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out "client-$name.crt" -days "$DAYS" -sha256 -extfile "client-$name.ext"
  rm -f "client-$name.csr" "client-$name.ext"
  echo "issued $name"
done

if [ "$WITH_FOREIGN_TEST_CERT" = 1 ]; then
  openssl ecparam -name prime256v1 -genkey -noout -out foreign-ca.key
  openssl req -x509 -new -key foreign-ca.key -sha256 -days 30 -out foreign-ca.crt -subj "/CN=Not The VAN Browser Core Edge CA"
  openssl ecparam -name prime256v1 -genkey -noout -out foreign-client.key
  openssl req -new -key foreign-client.key -out foreign-client.csr -subj "/CN=${CLIENTS[0]}"
  openssl x509 -req -in foreign-client.csr -CA foreign-ca.crt -CAkey foreign-ca.key \
    -CAcreateserial -out foreign-client.crt -days 30 -sha256
  rm -f foreign-client.csr
fi

# The CA key signs nothing at runtime; move it offline after issuance.
chown root:van-browser-edge edge.key edge.crt ca.crt 2>/dev/null || true
chmod 0640 edge.key
chmod 0644 ./*.crt
chmod 0600 ca.key client-*.key

echo
echo "Move client-*.key/.crt to the van-gateway host (VAN_BROWSER_CORE_CLIENT_{CERT,KEY}_FILE,"
echo "VAN_BROWSER_CORE_CA_FILE) and delete them here. Move ca.key offline."
