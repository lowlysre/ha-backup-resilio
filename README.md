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

> [!NOTE]
> Non-English translations under [`translations`](custom_components/resilio_backup/translations) are AI-generated and may be inaccurate. Corrections via PR against the relevant locale file are welcome and appreciated, or [file a translation issue](../../issues/new?template=translation_bug.yml) if you'd rather flag it than fix it.

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

## Documentation

- **[Usage](docs/usage.md)** — what setup gives you, use cases, entities, data updates, automation examples, options, and the `prune_backups` service.
- **[How it works](docs/how-it-works.md)** — the on-disk backup format, how this integration talks to Resilio's undocumented API, and the standalone CLIs.
- **[Troubleshooting](docs/troubleshooting.md)** — known limitations, common setup errors, and removing the integration.

