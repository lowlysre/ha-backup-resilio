# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Custom icons for the peer count, file count, and sync state sensors.
- Config flow now explains what the backup path and Resilio folder are for,
  warns (without blocking) when the entered backup path doesn't match the
  selected Resilio folder's own path, and posts a peer-invite link (with a
  QR code) as a persistent notification once the entry is created.
- `scan_interval` option to configure how often the coordinator polls the Resilio Sync API (default 60s, minimum 10s).
- Reauth flow: rejected credentials now prompt for a password update instead of leaving entities unavailable.
- `manifest.json` now declares a minimum supported Home Assistant version (2024.12.0), matching `hacs.json`, so HA core blocks setup on older installs instead of failing at runtime.

## [0.1.0] - 2026-08-30

### Added

- Initial release.
- Config flow to connect to a Resilio Sync agent and select/create the backup folder.
- `backup` platform storing, listing, downloading and deleting Home Assistant
  backups inside a Resilio Sync managed folder, with automatic pruning based on
  a configurable retention count.
- Sensors for sync state, folder size, file count and connected peers.
- Binary sensor reporting Resilio folder connectivity/health.
- `resilio_backup.prune_backups` service to manually trigger pruning.
