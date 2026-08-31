# Usage

After setup, this location shows up under **Settings > System > Backups**. Core and Container backups written there land in the configured directory and then sync through Resilio.

The integration also creates:

- `sensor` entities for sync state, folder size, file count, connected peers, and last updated
- a `binary_sensor` for connectivity

## Use cases

- Off-site copy of Core/Container backups: point `backup_path` at a Resilio-synced folder so every backup Home Assistant writes automatically replicates to a NAS, a remote server, or another peer, no extra automation required.
- Multi-site redundancy: add the same Resilio folder as a backup location on more than one Home Assistant instance so each keeps a synced copy of the others' backups.
- Sync health monitoring: the sensors and binary sensor let you build automations or dashboards around backup replication, e.g. alerting when a backup hasn't synced to peers within an expected window.

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

All entities are backed by a single [`DataUpdateCoordinator`](https://developers.home-assistant.io/docs/integration_fetching_data/) that polls the Resilio `/gui/` API on the `scan_interval` option (default 300 seconds, minimum 10). There is no push/webhook support (Resilio Sync's WebUI API doesn't offer one), so entity state can lag actual sync activity by up to that interval.

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
