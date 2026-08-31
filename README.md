# Resilio Backup

[![Build](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/combined.yaml/badge.svg)](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/combined.yaml)
[![HACS](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hacs.yml/badge.svg)](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hassfest.yml/badge.svg)](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hassfest.yml)
[![Coverage](https://coveralls.io/repos/github/lowlysre/ha-backup-resilio/badge.svg?branch=main)](https://coveralls.io/github/lowlysre/ha-backup-resilio?branch=main)
[![Quality Scale: Platinum](https://img.shields.io/badge/quality%20scale-%F0%9F%8F%86-e5e4e2)](custom_components/resilio_backup/quality_scale.yaml)

`resilio_backup` exposes a [Resilio Sync](https://www.resilio.com/individuals/) managed folder as a Home Assistant backup location. Home Assistant writes the local backup files, Resilio Sync replicates them to peers, and the integration reports sync health back into Home Assistant.

> [!NOTE]
> This is a HACS integration, so it's not eligible for an official core [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/) badge. The badge above is a self-assessment against that same checklist; see [`quality_scale.yaml`](custom_components/resilio_backup/quality_scale.yaml) for the rule-by-rule breakdown.

> [!WARNING]
> Resilio Sync is a third-party product. Use it at your own risk.

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom repository.
   - Category: `Integration`
3. Install `Resilio Backup`.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/resilio_backup` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

## Before you start

The Resilio Sync agent must have its WebUI/HTTP API **enabled, network-reachable from Home
Assistant, and password-protected** — this isn't automatic on every install:

- Linux and NAS builds expose it by default; Windows/macOS desktop apps usually need it turned
  on explicitly (`webui.listen`) since they don't run as a service.
- It listens on `127.0.0.1` unless configured to listen on a LAN address, so a Resilio agent
  running on a different machine than Home Assistant needs that changed too.
- Mobile (iOS/Android) Resilio Sync apps sync files but do not expose this API at all, so they
  can't be used as the target for this integration.

## Setup

1. Open **Settings > Devices & services**.
2. Add **Resilio Backup**.
3. Enter:
   - `host`
   - `port`
   - `username`
   - `password`
   - `use_ssl`
   - `verify_ssl`
4. Pick an existing Resilio folder or choose **Create a new folder**.
5. Confirm `backup_path`.

`backup_path` is the filesystem path Home Assistant writes to. In the simple local case it matches the Resilio folder path. If the API is remote or reverse proxied, use the path the Home Assistant process can actually reach.

## Usage

After setup, this location shows up under **Settings > System > Backups**. Core and Container backups written there land in the configured directory and then sync through Resilio.

The integration also creates:

- `sensor` entities for sync state, folder size, file count, connected peers, and last updated
- a `binary_sensor` for connectivity

## Use cases

- **Off-site copy of Core/Container backups.** Point `backup_path` at a Resilio-synced folder so every backup Home Assistant writes automatically replicates to a NAS, a remote server, or another peer, no extra automation required.
- **Multi-site redundancy.** Add the same Resilio folder as a backup location on more than one Home Assistant instance so each keeps a synced copy of the others' backups.
- **Sync health monitoring.** The sensors and binary sensor let you build automations or dashboards around backup replication, e.g. alerting when a backup hasn't synced to peers within an expected window.

## Entities

| Entity | Platform | Description |
| --- | --- | --- |
| Sync state | `sensor` | Current Resilio Sync state for the folder: `in_sync`, `syncing`, `paused`, `error`, or `unknown` |
| Folder size | `sensor` | Total size of the synced folder, in bytes |
| File count | `sensor` | Number of files currently in the synced folder |
| Peer count | `sensor` | Number of connected Resilio peers for the folder |
| Configured peer count | `sensor` | Number of Resilio peers configured for the folder, connected or not |
| Last updated | `sensor` | Timestamp of the last successful poll of the Resilio API |
| Connectivity | `binary_sensor` | Whether the Resilio API was reachable on the last poll |

## Data updates

All entities are backed by a single [`DataUpdateCoordinator`](https://developers.home-assistant.io/docs/integration_fetching_data/) that polls the Resilio `/gui/` API on the `scan_interval` option (default 60 seconds, minimum 10). There is no push/webhook support (Resilio Sync's WebUI API doesn't offer one), so entity state can lag actual sync activity by up to that interval.

## Automation examples

Notify if a folder falls out of sync for more than 10 minutes:

```yaml
automation:
  - alias: "Notify on Resilio sync stall"
    trigger:
      - trigger: state
        entity_id: sensor.resilio_sync_resilio_local_sync_state
        to: "error"
        for:
          minutes: 10
    action:
      - action: notify.mobile_app
        data:
          message: "Resilio backup sync has been failing for 10+ minutes."
```

Prune old backups on a schedule instead of relying on `prune_enabled`:

```yaml
automation:
  - alias: "Weekly Resilio backup prune"
    trigger:
      - trigger: time
        at: "03:00:00"
    condition:
      - condition: time
        weekday:
          - sun
    action:
      - action: resilio_backup.prune_backups
```

## Options

- `max_backups`
  - Number of backups to keep per configured location
  - `0` means unlimited
- `prune_enabled`
  - Enables or disables automatic pruning after upload
- `scan_interval`
  - Seconds between polls of the Resilio Sync API for folder status
  - Defaults to `60`, minimum `10`

## Service

### `resilio_backup.prune_backups`

Runs retention pruning immediately for every loaded Resilio Backup entry.

No service fields are required.

## How it works

Each backup uses two files in the configured directory:

- `<backup_id>.tar`
  - the raw Home Assistant backup archive
- `<backup_id>.json`
  - backup metadata that rebuilds the backup list without reopening the tarball

This integration only writes the local files, tracks metadata, applies retention, and reports status. Resilio Sync still handles the actual peer-to-peer transfer.

### Resilio's API

Resilio Sync's documented [`/api/v2`](https://github.com/bt-sync/sync_api_sample) REST API is gated behind a paid Business license; a free-tier install rejects it with an HTTP 400 and no body, confirmed against a live agent.

This integration instead drives the same undocumented `/gui/` endpoint the Sync WebUI itself uses: it mints a CSRF token from `/gui/token.html` (Basic Auth) plus the session cookie that comes back with it, then attaches both to every `action=` query call. That's the same approach taken by the reverse-engineered clients [`rslsync`](https://github.com/zhongkechen/python-resilio-sync-unofficial) and [`resilio-sync-cli`](https://github.com/PythonNut/resilio-sync-cli), which remain the only working references for this API; Resilio has never published it. `api.py`'s `_async_fetch_token` and `_async_request` implement this, including a one-shot retry to remint the token if a session expires mid-use.

Every `/gui/` action response is a flat dict with a `status` field, where `200` means success; a non-200 status is a logical failure even on an HTTP 200 response.

## Known limitations

- **No push updates.** The undocumented `/gui/` API has no webhook or streaming support, so sensor state is only as fresh as the last 60-second poll.
- **No device discovery.** Resilio Sync doesn't advertise itself over the network (no zeroconf/SSDP/DHCP), so setup always requires manually entering `host`/`port`.
- **Single Resilio folder per config entry.** Each config entry tracks one Resilio folder; add another entry to back up to a second folder.
- **No update entity.** This integration cannot update the Resilio Sync agent's software itself; do that from the Resilio app or OS package manager.
- **Free-tier API only.** Resilio's documented, license-gated `/api/v2` isn't used; see [Resilio's API](#resilios-api) above for why, and for what that means if Resilio changes the WebUI's internal API.

## Troubleshooting

### Setup fails with "Failed to connect to the Resilio API"

This means Home Assistant couldn't reach `host`:`port` at all.

1. Confirm the Resilio Sync WebUI/HTTP API is enabled and listening on a reachable address; see [Before you start](#before-you-start).
2. Confirm no firewall between Home Assistant and the Resilio agent blocks the configured port.
3. If `use_ssl` is enabled, confirm the agent is actually serving HTTPS on that port.

### Setup fails with "The Resilio credentials were rejected"

The WebUI username/password entered don't match the Resilio agent's configured credentials. Re-check them in the Resilio Sync WebUI settings.

### The integration shows as needing reauthentication

Home Assistant detected that the Resilio API started rejecting the configured credentials (e.g. the WebUI password was changed). Follow the reauthentication prompt in **Settings > Devices & services** to enter the new password without losing your existing folder/backup configuration.

### Backups aren't showing up on other peers

This integration only writes the local backup file and lets Resilio Sync replicate it. Check the Resilio Sync app/WebUI for the folder's actual sync status and peer connectivity; replication issues are outside this integration's control.

## Removing the integration

1. Open **Settings > Devices & services**.
2. Find the **Resilio Backup** entry and select **Delete**.

Deleting the entry stops Home Assistant from writing new backups to `backup_path` and removes its entities; it does not delete files already written there, and it does not change anything in Resilio Sync itself (the folder keeps syncing outside of Home Assistant).

