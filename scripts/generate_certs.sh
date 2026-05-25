#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 <out-dir> <server-name> <host> [host...]" >&2
  exit 1
fi

out_dir=$1
server_name=$2
shift 2

mkdir -p "$out_dir"
ca_key="$out_dir/ca.key"
ca_cert="$out_dir/ca.crt"
server_key="$out_dir/server.key"
server_csr="$out_dir/server.csr"
server_cert="$out_dir/server.crt"
server_ext="$out_dir/server.ext"
client_ext="$out_dir/client.ext"

openssl genrsa -out "$ca_key" 4096
openssl req -x509 -new -nodes -key "$ca_key" -sha256 -days 3650 \
  -subj "/CN=Geppetto Config CA" -out "$ca_cert"

openssl genrsa -out "$server_key" 4096
openssl req -new -key "$server_key" -subj "/CN=$server_name" -out "$server_csr"
cat >"$server_ext" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$server_name
EOF
openssl x509 -req -in "$server_csr" -CA "$ca_cert" -CAkey "$ca_key" -CAcreateserial \
  -out "$server_cert" -days 825 -sha256 -extfile "$server_ext"

cat >"$client_ext" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth
EOF

for host_name in "$@"; do
  client_key="$out_dir/$host_name.key"
  client_csr="$out_dir/$host_name.csr"
  client_cert="$out_dir/$host_name.crt"

  openssl genrsa -out "$client_key" 4096
  openssl req -new -key "$client_key" -subj "/CN=$host_name" -out "$client_csr"
  openssl x509 -req -in "$client_csr" -CA "$ca_cert" -CAkey "$ca_key" -CAcreateserial \
    -out "$client_cert" -days 825 -sha256 -extfile "$client_ext"
done

rm -f "$server_csr" "$server_ext" "$client_ext" "$out_dir"/*.csr
