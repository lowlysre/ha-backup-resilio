"""Pure helpers for mapping a raw Resilio `/gui/` folder object to sensor state.

Kept dependency-free (no Home Assistant imports) so CI's docker capture job
can import it directly and check it against a live Resilio Sync response
without installing the full Home Assistant test stack.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def safe_int(value: object, default: int = 0) -> int:
    """Coerce a Resilio field to an int, tolerating shapes the WebUI API doesn't document.

    The `/gui/` action API isn't documented, so a field observed as a scalar in one
    Resilio version can turn out to be a list (e.g. `peers` listing peer objects
    instead of a count) in another. Falling back to `len()` for list/tuple values,
    and to `default` for anything else that doesn't cleanly convert, keeps a single
    unexpected shape from crashing the whole coordinator refresh.
    """
    if isinstance(value, (list, tuple)):
        return len(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def peer_counts(folder: Mapping[str, Any]) -> tuple[int, int]:
    """Return (connected, total) peer counts for a raw Resilio folder object.

    `peers` lists every peer Resilio knows about for the folder, online or
    not; `onlinepeerscount` is Resilio's own count of the ones currently
    connected. A version that folds `peers` into a plain scalar count
    instead of a peer list has no way to tell the two apart, so connected
    and total collapse to that same number.
    """
    total = safe_int(folder.get("peers"))
    if "onlinepeerscount" in folder:
        return safe_int(folder.get("onlinepeerscount")), total
    return total, total


def derive_sync_state(folder: Mapping[str, Any]) -> str:
    """Map a raw Resilio folder object to a `sync_state` sensor value.

    A real `/gui/` folder object has no `state` string at all, confirmed
    against a live capture in tests/fixtures/resilio_gui/ (see
    lowlysre/ha-backup-resilio#9): `error`/`errors`, `paused`, and the
    `down_status`/`up_status` percentages (100 once fully caught up) carry
    the state instead. An error or a manual pause outranks an in-progress
    transfer.
    """
    if folder.get("error") or folder.get("errors"):
        return "error"
    if folder.get("paused"):
        return "paused"
    if safe_int(folder.get("down_status"), 100) < 100 or safe_int(folder.get("up_status"), 100) < 100:
        return "syncing"
    return "in_sync"
