# Troubleshooting

## Known limitations

- **No push updates.** The undocumented `/gui/` API has no webhook or streaming support, so sensor state is only as fresh as the last 60-second poll.
- **No device discovery.** Resilio Sync doesn't advertise itself over the network (no zeroconf/SSDP/DHCP), so setup always requires manually entering `host`/`port`.
- **Single Resilio folder per config entry.** Each config entry tracks one Resilio folder; add another entry to back up to a second folder.
- **No update entity.** This integration cannot update the Resilio Sync agent's software itself; do that from the Resilio app or OS package manager.
- **Free-tier API only.** Resilio's documented, license-gated `/api/v2` isn't used; see [Resilio's API](how-it-works.md#resilios-api) for why, and for what that means if Resilio changes the WebUI's internal API.

## Setup fails with "Failed to connect to the Resilio API"

This means Home Assistant couldn't reach `host`:`port` at all.

1. Confirm the Resilio Sync WebUI/HTTP API is enabled and listening on a reachable address; see [Before you start](../README.md#before-you-start).
2. Confirm no firewall between Home Assistant and the Resilio agent blocks the configured port.
3. If `use_ssl` is enabled, confirm the agent is actually serving HTTPS on that port.

## Setup fails with "The Resilio credentials were rejected"

The WebUI username/password entered don't match the Resilio agent's configured credentials. Re-check them in the Resilio Sync WebUI settings.

## The integration shows as needing reauthentication

Home Assistant detected that the Resilio API started rejecting the configured credentials (e.g. the WebUI password was changed). Follow the reauthentication prompt in **Settings > Devices & services** to enter the new password without losing your existing folder/backup configuration.

## Backups aren't showing up on other peers

This integration only writes the local backup file and lets Resilio Sync replicate it. Check the Resilio Sync app/WebUI for the folder's actual sync status and peer connectivity; replication issues are outside this integration's control.

## Removing the integration

1. Open **Settings > Devices & services**.
2. Find the **Resilio Backup** entry and select **Delete**.

Deleting the entry stops Home Assistant from writing new backups to `backup_path` and removes its entities; it does not delete files already written there, and it does not change anything in Resilio Sync itself (the folder keeps syncing outside of Home Assistant).
