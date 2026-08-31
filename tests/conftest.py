"""Pytest fixtures for Resilio Backup."""

from __future__ import annotations

from collections.abc import Generator
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_socket

from custom_components.resilio_backup.api import ResilioApiClient
from tests.common import MOCK_FOLDER, MOCK_OS

REAL_SOCKET = socket.socket


def _safe_socketpair(
    family: int = socket.AF_INET,
    type_: int = socket.SOCK_STREAM,
    proto: int = 0,
):
    """Create a socketpair without going through a patched `socket.socket`."""
    if family == socket.AF_INET:
        host = "127.0.0.1"
    elif family == socket.AF_INET6:
        host = "::1"
    else:
        raise ValueError("Only AF_INET and AF_INET6 are supported")

    listener = REAL_SOCKET(family, type_, proto)
    try:
        listener.bind((host, 0))
        listener.listen(1)
        client = REAL_SOCKET(family, type_, proto)
        try:
            client.setblocking(False)
            try:
                client.connect(listener.getsockname())
            except BlockingIOError:
                pass
            patched_socket = socket.socket
            socket.socket = REAL_SOCKET
            try:
                server, _ = listener.accept()
            finally:
                socket.socket = patched_socket
        finally:
            client.setblocking(True)
    finally:
        listener.close()

    return server, client


socket.socketpair = _safe_socketpair


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in this test session."""
    del enable_custom_integrations
    yield


@pytest.fixture(autouse=True)
def auto_enable_socket(socket_enabled):
    """Allow sockets so the Home Assistant test loop can start on Windows."""
    del socket_enabled
    yield


def pytest_collection_modifyitems(items):
    """Enable sockets for all tests before the loop is created."""
    marker = pytest.mark.enable_socket
    for item in items:
        item.add_marker(marker)


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """Re-enable sockets after the plugin disables them."""
    del item
    pytest_socket.enable_socket()


@pytest.fixture
def mock_client() -> Generator[SimpleNamespace]:
    """Patch the Resilio API client methods."""
    with (
        patch.object(ResilioApiClient, "async_get_os", AsyncMock(return_value=MOCK_OS)) as get_os,
        patch.object(
            ResilioApiClient, "async_get_folders", AsyncMock(return_value=[MOCK_FOLDER])
        ) as get_folders,
        patch.object(
            ResilioApiClient, "async_add_folder", AsyncMock(return_value=MOCK_FOLDER)
        ) as add_folder,
        patch.object(
            ResilioApiClient, "async_get_folder", AsyncMock(return_value=MOCK_FOLDER)
        ) as get_folder,
    ):
        yield SimpleNamespace(
            get_os=get_os,
            get_folders=get_folders,
            add_folder=add_folder,
            get_folder=get_folder,
        )
