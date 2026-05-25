# Geppetto Server

`Geppetto_Server` exposes host-scoped config bundles for `geppetto-auto` agents over mutual TLS.

The service reads a Geppetto config tree such as:

```text
config/
  defaults/
  groups/
  hosts/<hostname>/
  templates/
```

For a request to `/v1/configs/<hostname>/bundle`, it returns a zip file containing:

- `hosts/<hostname>/plan.fops`
- any `.fops` files recursively referenced via `include`
- the full `templates/` directory, when present

This matches the existing Geppetto layout while avoiding a full Git checkout on each host.
Authentication is certificate-based:

- the server presents its own TLS certificate
- the server requires a client certificate signed by your CA
- the client certificate CN must match the requested host name

## Run

```bash
export GEPPETTO_CONFIG_ROOT=/srv/geppetto/config
export GEPPETTO_SERVER_CERT=/srv/geppetto/pki/server.crt
export GEPPETTO_SERVER_KEY=/srv/geppetto/pki/server.key
export GEPPETTO_CA_CERT=/srv/geppetto/pki/ca.crt
geppetto-config-server
```

Optional bind overrides:

```bash
export GEPPETTO_SERVER_HOST=0.0.0.0
export GEPPETTO_SERVER_PORT=8443
```

## Generate certs

```bash
./scripts/generate_certs.sh /srv/geppetto/pki config.example.com host1 host2
```

This creates:

- a local CA
- a server certificate for `config.example.com`
- one client certificate/key pair per host, with the host name as the certificate CN

## Agent config

In `Geppetto`:

```toml
[defaults]
config_service_url = "https://config.example.com"
config_service_path = "/etc/geppetto/config"
config_service_ca_cert = "/etc/geppetto/pki/ca.crt"
config_service_client_cert = "/etc/geppetto/pki/host1.crt"
config_service_client_key = "/etc/geppetto/pki/host1.key"
template_dir = "/etc/geppetto/config/templates"
```

When `plan` is left at the default, `geppetto-auto` will automatically use:

```text
/etc/geppetto/config/hosts/<hostname>/plan.fops
```
