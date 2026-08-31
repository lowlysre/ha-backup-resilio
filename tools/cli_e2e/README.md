# resilio-client CLI E2E fixture

Standalone docker-compose fixture that runs the `resilio-client` CLI
(`resilio_client/`) against a real, unlicensed `resilio/sync` container. First
slice of lowlysre/ha-backup-resilio#2's CLI extraction + E2E ask: validates the
`status`/`folders`/`add-folder` commands against Resilio's actual behavior
instead of only mocked responses. A full backup/restore CLI and a
multi-version container matrix are deferred follow-ups.

Runs on every PR as the `resilio-client-e2e` job in
`.github/workflows/combined.yaml`.

## Running locally

```powershell
docker compose -f tools/cli_e2e/docker-compose.yml up -d
pip install -e .
resilio-client status --host 127.0.0.1 --port 8888 --username admin --password cli-e2e-secret
resilio-client folders --host 127.0.0.1 --port 8888 --username admin --password cli-e2e-secret
resilio-client add-folder --host 127.0.0.1 --port 8888 --username admin --password cli-e2e-secret --path /mnt/sync/folders/e2e
docker compose -f tools/cli_e2e/docker-compose.yml down -v
```

The container can accept TCP connections before `rslsync` has finished
agreeing to the EULA and initializing, so the first few requests can fail even
though the port is already open; retry `status` a few times with a short delay
before trusting a connection failure.
