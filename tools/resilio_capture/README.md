# Resilio Sync capture fixture

Standalone docker-compose fixture for capturing real `/gui/` WebUI API responses
from Resilio Sync, used to fix lowlysre/ha-backup-resilio#4 without a live agent.
Split off from lowlysre/ha-backup-resilio#2's larger CLI/E2E-harness ask, see
lowlysre/ha-backup-resilio#9.

Runs on every PR as the `resilio-capture` job in
`.github/workflows/combined.yaml`: it stands up two unlicensed `resilio/sync`
containers, replays `custom_components/resilio_backup/api.py`'s token/cookie
flow against them, and runs the real `folder_state.derive_sync_state` against
what comes back. An upstream Resilio Sync change that drops or renames a field
`coordinator.py` depends on fails that job instead of silently reporting the
wrong `sync_state` again.

## Running locally

```powershell
docker compose -f tools/resilio_capture/docker-compose.yml up -d
pip install -r tools/resilio_capture/requirements.txt
python tools/resilio_capture/capture.py
docker compose -f tools/resilio_capture/docker-compose.yml down -v
```

`capture.py` creates a shared folder, lets a second peer join it, then drops
that peer. Each captured `getsyncfolders` response is written to
`tests/fixtures/resilio_gui/`. Secrets and ids are real (not yet redacted) after
a local run; the checked-in copies had those replaced by fixed placeholders
before committing, since CI never commits its own run's output.

## What the capture found

There's no `state` field anywhere in a real folder object, so `coordinator.py`'s
old `folder.get("state", "unknown")` guess was never going to match. The real
connectivity/progress signal is a mix of fields, now handled by
`custom_components/resilio_backup/folder_state.py`'s `derive_sync_state`:

- `onlinepeerscount` (int): connected peer count, `peers` (list) already carries
  each peer's own `isonline` flag
- `paused` (bool)
- `error` (int, `0` when clean), `errors` (list), `warnings` (list)
- `down_status`/`up_status` (int, percent complete, `100` when idle/caught up)

`status` (an int, `7` in every capture here) didn't change across
disconnected/connected/solo scenarios in this fixture, so it looks like a
folder-type/permission bitmask rather than a sync-progress indicator. Confirming
that, and catching an actual in-progress transfer (`down_status`/`up_status`
under 100) or a real folder-level error, needs a slower peer link or a
deliberately broken permission, neither of which this fixture forces yet.
