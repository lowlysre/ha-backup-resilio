# resilio-client CLI E2E fixture

Standalone docker-compose fixture that runs the `resilio-client` CLI
(`resilio_client/`) against a real, unlicensed `resilio/sync` container. First
slice of lowlysre/ha-backup-resilio#2's CLI extraction + E2E ask: validates the
`status`/`folders`/`add-folder` commands against Resilio's actual behavior
instead of only mocked responses. A full backup/restore CLI is a deferred
follow-up.

Runs on every PR as the `resilio-client-e2e` job in
`.github/workflows/combined.yaml`, as a matrix across the `resilio_version`
tags below, so a WebUI API change in a specific Resilio Sync release doesn't
silently slip past CI.

## Version matrix

The image tag is controlled by the `RESILIO_IMAGE_TAG` environment variable
(default `2.8.1` if unset), read by `docker-compose.yml`. CI currently pins:

- `2.8.1` — current stable release (also tagged `latest` upstream)
- `2.7.3` — previous widely-deployed release
- `2.7.2` — older widely-deployed release

See [Docker Hub](https://hub.docker.com/r/resilio/sync/tags) for the full list
of tags Resilio publishes.

## Running locally

```powershell
docker compose -f tools/cli_e2e/docker-compose.yml up -d
pip install -e .
resilio-client status --host 127.0.0.1 --port 8888 --username admin --password cli-e2e-secret
resilio-client folders --host 127.0.0.1 --port 8888 --username admin --password cli-e2e-secret
resilio-client add-folder --host 127.0.0.1 --port 8888 --username admin --password cli-e2e-secret --path /mnt/sync/folders/e2e
docker compose -f tools/cli_e2e/docker-compose.yml down -v
```

To run against a specific version instead of the default, set
`RESILIO_IMAGE_TAG` before starting the container:

```powershell
$env:RESILIO_IMAGE_TAG = "2.7.3"
docker compose -f tools/cli_e2e/docker-compose.yml up -d
```

The container can accept TCP connections before `rslsync` has finished
agreeing to the EULA and initializing, so the first few requests can fail even
though the port is already open; retry `status` a few times with a short delay
before trusting a connection failure.
