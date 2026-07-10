#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <host> [base-dir]" >&2
  exit 1
fi

host_name=$1
base_dir=${2:-/etc/geppetto_server}
csr="$base_dir/csr_pending/$host_name.csr"
cert_dir="$base_dir/certs"
cert="$cert_dir/$host_name.crt"
ca_cert="$base_dir/pki/ca.crt"
ca_key="$base_dir/pki/ca.key"

mkdir -p "$cert_dir"
openssl x509 -req -in "$csr" -CA "$ca_cert" -CAkey "$ca_key" -CAcreateserial \
  -out "$cert" -days 825 -sha256
chmod 644 "$cert"
if id geppetto-server >/dev/null 2>&1; then
  chown geppetto-server:geppetto-server "$cert"
fi
echo "$cert"
