#!/usr/bin/env python3
"""Capture real Resilio Sync `/gui/` WebUI responses for fixture data.

Drives the same undocumented, free-tier `/gui/` endpoint
`custom_components/resilio_backup/api.py` talks to (token.html for a CSRF
token + session cookie, then `action=` query calls) against the two
containers started by `docker-compose.yml` in this directory. Dumps each
captured `getsyncfolders` response as-is, so `coordinator.py`'s field
mapping can be fixed against real shapes instead of guesses (see
lowlysre/ha-backup-resilio#9). Runs in CI (`.github/workflows/combined.yaml`'s
`resilio-capture` job) on every PR so an upstream Resilio Sync change that
drops or renames a field this integration depends on gets caught here rather
than silently breaking `coordinator.py`'s `sync_state` mapping again.

Usage:
    docker compose -f tools/resilio_capture/docker-compose.yml up -d
    python tools/resilio_capture/capture.py
    docker compose -f tools/resilio_capture/docker-compose.yml down -v
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "resilio_gui"


def _load_derive_sync_state():
    """Load `folder_state.derive_sync_state` without importing the package `__init__.py`.

    `custom_components/resilio_backup/__init__.py` pulls in Home Assistant
    (`backup.py`'s `homeassistant.components.backup` import) as soon as the
    package is imported normally. `folder_state.py` itself has no such
    dependency, so it's loaded directly from its file path to keep this
    script (and the CI job that runs it) free of a full HA install.
    """
    module_path = REPO_ROOT / "custom_components" / "resilio_backup" / "folder_state.py"
    spec = importlib.util.spec_from_file_location("resilio_folder_state", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.derive_sync_state


derive_sync_state = _load_derive_sync_state()

LOGIN = "admin"
PASSWORD = "capture-secret"
PEER_A = "http://127.0.0.1:8888/gui"
PEER_B = "http://127.0.0.1:8889/gui"
TOKEN_PATTERN = re.compile(r"id=['\"]token['\"][^>]*>(?P<token>[\w-]+)<")
REQUIRED_FOLDER_KEYS = {"error", "errors", "paused", "down_status", "up_status", "peers", "onlinepeerscount"}


class ResilioCaptureClient:
    """Minimal client for the `/gui/` action API, mirroring `api.py`."""

    def __init__(self, base_url: str, login: str, password: str) -> None:
        self._base_url = base_url
        credentials = base64.b64encode(f"{login}:{password}".encode()).decode()
        self._auth_header = {"Authorization": f"Basic {credentials}"}
        self._token: str | None = None
        self._cookie: str | None = None

    def _fetch_token(self) -> None:
        response = requests.get(
            f"{self._base_url}/token.html",
            headers=self._auth_header,
            params={"t": int(time.time() * 1000)},
            timeout=10,
        )
        response.raise_for_status()
        match = TOKEN_PATTERN.search(response.text)
        cookie = response.headers.get("Set-Cookie")
        if not match or not cookie:
            raise RuntimeError(f"No token/cookie from {self._base_url}: {response.text[:200]}")
        self._token = match.group("token")
        self._cookie = cookie.split(";", 1)[0]

    def reset_token(self) -> None:
        """Drop the cached token, forcing the next `action()` call to re-authenticate."""
        self._token = None

    def action(self, name: str, **params: Any) -> dict[str, Any]:
        """Call a `/gui/` action and return the decoded JSON response."""
        if self._token is None:
            self._fetch_token()
        query = {"token": self._token, "action": name, "t": int(time.time() * 1000), **params}
        headers = {**self._auth_header, "Cookie": self._cookie}
        response = requests.get(f"{self._base_url}/", headers=headers, params=query, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == 401:
            self._token = None
            return self.action(name, **params)
        return payload


def wait_until_ready(client: ResilioCaptureClient, timeout: int = 60) -> None:
    """Poll `getsyncfolders` until the container answers, tolerating a cold start.

    The container's WebUI can accept TCP connections before `rslsync` has
    finished agreeing to the EULA and initializing, so the first few
    requests can 500 even though the port is already open.
    """
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            client.action("getsyncfolders", discovery=1)
            return
        except (requests.RequestException, RuntimeError) as err:
            last_error = err
            client.reset_token()
            time.sleep(2)
    raise RuntimeError(f"container never became ready: {last_error}")


def dump(name: str, payload: dict[str, Any]) -> None:
    """Write a captured response to the fixtures directory."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


def wait_for_folder(client: ResilioCaptureClient, path: str, predicate, timeout: int = 60):
    """Poll `getsyncfolders` until the folder at `path` satisfies `predicate`."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        payload = client.action("getsyncfolders", discovery=1)
        for folder in payload.get("folders", []):
            if folder.get("path") == path:
                last = folder
                if predicate(folder):
                    return payload, folder
        time.sleep(2)
    print(f"timed out waiting on {path!r}, last folder seen: {last}", file=sys.stderr)
    return None, last


def verify_folder_shape(name: str, folder: dict[str, Any]) -> list[str]:
    """Check a captured folder object still has the fields `coordinator.py` relies on.

    This is the actual regression check: it runs the production
    `derive_sync_state` against a live Resilio Sync response, so a Resilio
    upstream change that drops or renames one of `REQUIRED_FOLDER_KEYS`
    fails CI here instead of silently reporting the wrong `sync_state`.
    """
    problems = [f"{name}: missing key {key!r}" for key in REQUIRED_FOLDER_KEYS if key not in folder]
    try:
        state = derive_sync_state(folder)
        print(f"{name}: derive_sync_state -> {state!r}")
    except Exception as err:  # pylint: disable=broad-except
        problems.append(f"{name}: derive_sync_state raised {err!r}")
    return problems


def main() -> None:
    """Capture the four fixture scenarios and verify their shape against `derive_sync_state`."""
    peer_a = ResilioCaptureClient(PEER_A, LOGIN, PASSWORD)
    peer_b = ResilioCaptureClient(PEER_B, LOGIN, PASSWORD)
    shared_path = "/mnt/sync/folders/capture"
    problems: list[str] = []

    wait_until_ready(peer_a)
    wait_until_ready(peer_b)

    # Baseline: no folders yet.
    dump("empty_folders", peer_a.action("getsyncfolders", discovery=1))

    # Create a folder on peer A with a fresh read-write secret, capture it
    # in isolation (no peers connected) before peer B joins.
    peer_a.action("addsyncfolder", path=shared_path, secret="", selectivesync="false", encrypted="false")
    solo_payload = peer_a.action("getsyncfolders", discovery=1)
    dump("solo_no_peers", solo_payload)
    folder = next(f for f in solo_payload["folders"] if f.get("path") == shared_path)
    problems += verify_folder_shape("solo_no_peers", folder)
    secret = folder["secret"]

    # Join the same folder on peer B and wait for it to come online.
    peer_b.action("addsyncfolder", path=shared_path, secret=secret, selectivesync="false", encrypted="false")
    connected_payload, connected_folder = wait_for_folder(
        peer_a, shared_path, lambda f: f.get("onlinepeerscount", 0) > 0, timeout=60
    )
    if connected_payload:
        dump("peer_connected", connected_payload)
        problems += verify_folder_shape("peer_connected", connected_folder)
    else:
        problems.append("peer_connected: peer never came online")

    # Drop peer B's folder while A still has an active share. Each peer
    # assigns its own local folderid for the same shared secret, so peer B's
    # id has to be looked up rather than reused from peer A's.
    peer_b_folders = peer_b.action("getsyncfolders", discovery=1)
    peer_b_folder_id = next(f["folderid"] for f in peer_b_folders["folders"] if f.get("path") == shared_path)
    peer_b.action("removefolder", folderid=peer_b_folder_id, deletedirectory="false", fromalldevices="false")
    disconnected_payload, disconnected_folder = wait_for_folder(
        peer_a, shared_path, lambda f: f.get("onlinepeerscount", 0) == 0, timeout=30
    )
    disconnected_payload = disconnected_payload or peer_a.action("getsyncfolders", discovery=1)
    dump("peer_removed", disconnected_payload)
    if disconnected_folder:
        problems += verify_folder_shape("peer_removed", disconnected_folder)

    if problems:
        print("Resilio API shape check failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        sys.exit(1)

    print("done")


if __name__ == "__main__":
    main()
