# resilio-backup-store CLI E2E fixture

Standalone docker-compose fixture that runs the `resilio-backup-store` CLI
(`custom_components/resilio_backup/resilio_backup_store/`) against a folder a real, unlicensed `resilio/sync`
container actively manages. Second slice of lowlysre/ha-backup-resilio#2's
CLI extraction + E2E ask (the first slice, the WebUI client CLI, is in
`tools/cli_e2e/`): validates the `create`/`list`/`restore`/`prune`/`delete`
commands against a directory Resilio is actually watching, instead of only a
plain temp directory.

Unlike `tools/cli_e2e`, this fixture bind-mounts a host directory
(`./data`) into the container's `/mnt/sync` instead of using a named Docker
volume, so the CLI running on the host and the Resilio agent running in the
container operate on the exact same files.

Runs on every PR as the `backup-store-e2e` job in
`.github/workflows/combined.yaml`.

## Running locally

```powershell
mkdir tools/backup_store_e2e/data
docker compose -f tools/backup_store_e2e/docker-compose.yml up -d
pip install -e .

# Let Resilio track the folder the CLI will write into.
resilio-client add-folder --host 127.0.0.1 --port 8889 --username admin --password backup-store-e2e-secret --path /mnt/sync/folders/backups

# Create, list, restore, prune, and delete a backup in that same folder.
echo "hello" > archive.tar
resilio-backup-store create --backup-path tools/backup_store_e2e/data/folders/backups --backup-id b1 --metadata "{\"date\": \"2026-08-30T23:00:00+00:00\"}" --input archive.tar
resilio-backup-store list --backup-path tools/backup_store_e2e/data/folders/backups
resilio-backup-store restore --backup-path tools/backup_store_e2e/data/folders/backups --backup-id b1 --output restored.tar
resilio-backup-store prune --backup-path tools/backup_store_e2e/data/folders/backups --max-backups 0
resilio-backup-store delete --backup-path tools/backup_store_e2e/data/folders/backups --backup-id b1

docker compose -f tools/backup_store_e2e/docker-compose.yml down -v
rm -r tools/backup_store_e2e/data archive.tar restored.tar
```

As with `tools/cli_e2e`, the container can accept connections before
`rslsync` has finished initializing, so retry `resilio-client status` a few
times before trusting a connection failure.
