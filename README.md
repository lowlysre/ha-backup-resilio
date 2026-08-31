# Resilio Backup

[![Build](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/combined.yaml/badge.svg)](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/combined.yaml)
[![HACS](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hacs.yml/badge.svg)](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hassfest.yml/badge.svg)](https://github.com/lowlysre/ha-backup-resilio/actions/workflows/hassfest.yml)
[![Coverage](https://coveralls.io/repos/github/lowlysre/ha-backup-resilio/badge.svg?branch=main)](https://coveralls.io/github/lowlysre/ha-backup-resilio?branch=main)

`resilio_backup` exposes a [Resilio Sync](https://www.resilio.com/individuals/) managed folder as a Home Assistant backup location. Home Assistant writes the local backup files, Resilio Sync replicates them to peers, and the integration reports sync health back into Home Assistant.

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

- `sensor` entities for sync state, folder size, file count, and connected peers
- a `binary_sensor` for connectivity

## Options

- `max_backups`
  - Number of backups to keep per configured location
  - `0` means unlimited
- `prune_enabled`
  - Enables or disables automatic pruning after upload

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

