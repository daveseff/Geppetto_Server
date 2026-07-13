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
export GEPPETTO_SERVER_BASE=/etc/geppetto_server
geppetto-config-server
```

Help is available either as flags or commands:

```bash
geppetto-config-server --help
geppetto-config-server help
geppetto-config-server init help
geppetto-config-server help cert
geppetto-config-server help cert sign
geppetto-config-server cert help
geppetto-config-server cert sign help
```

With packages installed, run it as a daemon:

```bash
systemctl enable --now geppetto-server
```

On first start, the daemon initializes a local CA and server certificate if
`/etc/geppetto_server/pki/ca.crt` and `/etc/geppetto_server/pki/server.crt`
do not exist. Set `GEPPETTO_SERVER_NAME` in `/etc/geppetto_server/geppetto-server.env`
before first start if the certificate DNS name should be different from the
machine FQDN. Set `GEPPETTO_SERVER_ALT_NAMES` to a comma-separated list when
agents may connect using more than one DNS name, for example:

```bash
GEPPETTO_SERVER_NAME=saturn
GEPPETTO_SERVER_ALT_NAMES=saturn.solar1.net
geppetto-config-server init
systemctl restart geppetto-server
```

`init` preserves the CA but regenerates the server certificate/key when the
existing server certificate does not include the configured DNS names. Use
`init --force` only when you intentionally want to rotate the CA too.

By default the server reads:

- `/etc/geppetto_server/config`
- `/etc/geppetto_server/pki/server.crt`
- `/etc/geppetto_server/pki/server.key`
- `/etc/geppetto_server/pki/ca.crt`
- `/etc/geppetto_server/pki/ca.key`
- `/etc/geppetto_server/csr_pending`
- `/etc/geppetto_server/certs`
- `/var/log/geppetto/geppetto-server.log`

Optional overrides:

```bash
export GEPPETTO_CONFIG_ROOT=/srv/geppetto/config
export GEPPETTO_SERVER_HOST=0.0.0.0
export GEPPETTO_SERVER_PORT=8443
```

## Containers

The server container should persist `/var/lib/geppetto_server`. That path holds:

- `config/`
- `pki/`
- `csr_pending/`
- `certs/`

If you do not persist it, task replacements will generate a new CA and existing
agents will stop trusting the server.

Build the image:

```bash
docker build -t geppetto-server .
```

Run it with a persistent host directory:

```bash
mkdir -p ./docker-data/geppetto_server/config
docker run -d \
  --name geppetto-server \
  -p 8443:8443 \
  -e GEPPETTO_SERVER_NAME=config.example.com \
  -e GEPPETTO_SERVER_ALT_NAMES=config,config.example.com \
  -v "$PWD/docker-data/geppetto_server:/var/lib/geppetto_server" \
  geppetto-server
```

The image:

- runs `geppetto-config-server serve` by default
- writes logs to stdout
- initializes CA/server certificates on first start
- exposes `/health` for container health checks

For local Docker Compose:

```bash
export GEPPETTO_SERVER_NAME=config.example.com
docker compose up -d --build
```

Place your config tree under `./docker-data/geppetto_server/config`.

For ECS/Fargate, the important requirement is that
`/var/lib/geppetto_server` is backed by persistent storage such as EFS. If you
keep the container running as UID/GID `10001`, make sure the mounted path is
writable by that user.

## Generate certs

```bash
./scripts/generate_certs.sh /etc/geppetto_server/pki config.example.com host1 host2
```

Set `GEPPETTO_SERVER_ALT_NAMES` before running the helper to add extra server
certificate SAN entries:

```bash
GEPPETTO_SERVER_ALT_NAMES=config,config.example.com \
  ./scripts/generate_certs.sh /etc/geppetto_server/pki config host1 host2
```

This creates:

- a local CA
- a server certificate for `config.example.com`
- one client certificate/key pair per host, with the host name as the certificate CN

## Agent Enrollment

Agents can bootstrap their own client key and CSR. When cert paths are omitted,
the agent defaults to `/etc/geppetto/pki/ca.crt` and
`/etc/geppetto/pki/<hostname>.{crt,key}`. On first run, if those files are
missing, `geppetto-auto` will:

- download `/v1/ca` into `config_service_ca_cert`
- generate `config_service_client_key`
- generate a CSR next to the client cert path, for example `host1.csr`
- submit the CSR to `/v1/csr/<hostname>`

By default the server stores submitted CSRs in `/etc/geppetto_server/csr_pending` and returns `202 Accepted`. Sign a pending CSR with:

```bash
/home/dave/git/Geppetto_Server/scripts/sign_csr.sh host1 /etc/geppetto_server
```

On the next agent run, the agent submits the same CSR again. If the signed cert exists in `/etc/geppetto_server/certs/host1.crt`, the server returns it and the agent writes it to `config_service_client_cert`.

For labs, set `GEPPETTO_AUTOSIGN=true` on the server to sign CSRs immediately. Do not use autosign for untrusted networks.

## Certificate CLI

The server CLI provides Puppet-style certificate operations:

```bash
sudo geppetto-config-server init
sudo geppetto-config-server init --force
sudo geppetto-config-server cert list
sudo geppetto-config-server cert status host1
sudo geppetto-config-server cert sign host1
sudo geppetto-config-server cert clean host1
```

Packaged installs keep `/etc/geppetto_server` readable only by root and the
`geppetto-server` service user, so certificate management commands normally
need `sudo`.

`init` creates the CA and server certificate if they do not already exist.
`init --force` rotates the CA/server certificate and removes stale signed agent
certificates.
`cert sign` signs a pending CSR from `/etc/geppetto_server/csr_pending`.
`cert clean` removes both the pending CSR and signed cert for the host.

## Packaging

RPM-based systems can use the root spec file:

```bash
rpmbuild -ba geppetto-server.spec
```

Arch-based systems can use:

```bash
cd packaging
makepkg -si
```

The Arch `PKGBUILD` builds from the parent checkout, so it works directly from
`Geppetto_Server/packaging` without manually creating `geppetto_server-0.1.0.tar.gz`.

Both package definitions install:

- `geppetto-config-server`
- `geppetto-server.service`
- `/etc/geppetto_server/geppetto-server.env`
- `/etc/geppetto_server/{config,pki,csr_pending,certs}`
- helper scripts under `/usr/share/geppetto_server/scripts`

## Agent config

In `Geppetto`:

```toml
[defaults]
config_service_url = "https://config.example.com"
config_service_path = "/etc/geppetto/config"
template_dir = "/etc/geppetto/config/templates"
```

When `plan` is left at the default, `geppetto-auto` will automatically use:

```text
/etc/geppetto/config/hosts/<hostname>/plan.fops
```
