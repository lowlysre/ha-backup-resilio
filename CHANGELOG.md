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
- `scan_interval` option to configure how often the coordinator polls the Resilio Sync API (default 300s, minimum 10s).
- Reauthentication flow, triggered when Resilio rejects the configured credentials.
- Reconfigure flow to update connection details without removing and re-adding the integration.
- Diagnostic and troubleshooting documentation, entity/use-case tables, and automation examples in the README.
- `quality_scale.yaml` self-assessment tracking this integration's alignment with Home Assistant's Integration Quality Scale.
- A repair issue when the configured Resilio folder is missing or renamed, since retrying the poll won't fix it.
- Standalone `resilio-client` CLI (`resilio_client/`) exposing the Resilio WebUI client's `status`/`folders`/`add-folder`/`share-link` operations with no Home Assistant dependency, plus a CI job that runs it against a live `resilio/sync` container on every PR.

### Changed

- `resilio_backup.prune_backups` now registers once at component setup instead of per config entry, so it stays available for as long as any entry is loaded.
- Service and backup-agent failures now raise translatable exceptions instead of plain error strings.

### Fixed

- Sensors and the binary sensor now declare `PARALLEL_UPDATES = 0` since they're coordinator-backed and read-only.
- Authentication failures now raise `ConfigEntryAuthFailed` instead of a generic update failure, so Home Assistant prompts for reauthentication.

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
