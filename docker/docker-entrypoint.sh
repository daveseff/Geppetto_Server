#!/bin/sh
set -eu

export GEPPETTO_SERVER_BASE="${GEPPETTO_SERVER_BASE:-/var/lib/geppetto_server}"
export GEPPETTO_SERVER_LOG_FILE="${GEPPETTO_SERVER_LOG_FILE:-/dev/stdout}"

config_root="${GEPPETTO_CONFIG_ROOT:-$GEPPETTO_SERVER_BASE/config}"
server_cert="${GEPPETTO_SERVER_CERT:-$GEPPETTO_SERVER_BASE/pki/server.crt}"
ca_cert="${GEPPETTO_CA_CERT:-$GEPPETTO_SERVER_BASE/pki/ca.crt}"
pending_csr_dir="${GEPPETTO_PENDING_CSR_DIR:-$GEPPETTO_SERVER_BASE/csr_pending}"
signed_cert_dir="${GEPPETTO_SIGNED_CERT_DIR:-$GEPPETTO_SERVER_BASE/certs}"

mkdir -p \
  "$GEPPETTO_SERVER_BASE" \
  "$config_root" \
  "$(dirname "$server_cert")" \
  "$(dirname "$ca_cert")" \
  "$pending_csr_dir" \
  "$signed_cert_dir"

if [ "$#" -eq 0 ]; then
  set -- geppetto-config-server serve
fi

exec "$@"
