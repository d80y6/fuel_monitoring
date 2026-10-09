#!/usr/bin/env bash
# Generate the certificate material MQTT TLS needs.
#
# Why this exists: MQTT_TLS_PORT/MQTT_CA_CERT/MQTT_CLIENT_CERT/MQTT_CLIENT_KEY
# were all empty, so devices and internal services authenticated with plaintext
# credentials. This creates a private CA, a server certificate for the broker and
# a client certificate for the ingestion service.
#
# Usage:
#   scripts/generate_certs.sh [output_dir]     # default infra/emqx/certs
#
# The CA private key never leaves this host. Regenerating invalidates every
# certificate signed by it, which will disconnect all devices.
set -euo pipefail

OUT="${1:-infra/emqx/certs}"
DAYS=3650

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl is required" >&2
  exit 1
fi

mkdir -p "$OUT"
cd "$OUT"

if [[ -f ca.key ]]; then
  echo "CA already exists in $OUT. Remove it deliberately if you mean to rotate;"
  echo "rotating the CA will disconnect every device using these certificates."
  exit 1
fi

echo "==> private CA"
openssl req -x509 -newkey rsa:4096 -sha256 -days "$DAYS" -nodes \
  -keyout ca.key -out ca.pem \
  -subj "/CN=fuel-platform-ca/O=Fuel Platform" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null

echo "==> broker server certificate"
openssl req -newkey rsa:4096 -sha256 -nodes \
  -keyout server.key -out server.csr \
  -subj "/CN=emqx/O=Fuel Platform" 2>/dev/null
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out server.pem -days "$DAYS" -sha256 \
  -extfile <(printf "subjectAltName=DNS:emqx,DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n") 2>/dev/null

echo "==> ingestion client certificate"
openssl req -newkey rsa:4096 -sha256 -nodes \
  -keyout client.key -out client.csr \
  -subj "/CN=fuel-platform-ingest/O=Fuel Platform" 2>/dev/null
openssl x509 -req -in client.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out client.pem -days "$DAYS" -sha256 \
  -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n") 2>/dev/null

rm -f server.csr client.csr ca.srl
chmod 600 ca.key server.key client.key
chmod 644 ca.pem server.pem client.pem

echo
echo "Generated in $(pwd):"
ls -1 .
echo
echo "Next: export the paths so the stack picks them up"
echo "  MQTT_CA_CERT=/opt/emqx/etc/certs/ca.pem          # broker-side trust anchor"
echo "  MQTT_TLS_PORT=8883"
echo "  MQTT_CLIENT_CERT=/opt/emqx/etc/certs/client.pem  # ingestion client"
echo "  MQTT_CLIENT_KEY=/opt/emqx/etc/certs/client.key"
echo "and uncomment the listeners.ssl.default block in infra/emqx/emqx.conf."