# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Custom icons for the peer count, file count, and sync state sensors.

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
