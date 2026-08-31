"""A minimal fake aiohttp session/response for testing resilio_client.client.

Avoids depending on ``aioresponses`` (which can lag behind aiohttp releases,
see e.g. incompatibilities with very recent aiohttp versions) by directly
faking the small surface ``ResilioClient`` actually uses:
``session.get(...)`` as an async context manager yielding a response with
``.status``, ``.headers``, ``async .text()``, and ``async .json()``.

Responses are queued and consumed in call order, mirroring the fixed
request sequence each ``ResilioClient`` method makes (token fetch, then the
action call, occasionally followed by a retried action call).
"""

from __future__ import annotations

from collections.abc import Mapping
import json as json_module
from typing import Any


class FakeResponse:
    """A queued fake aiohttp response."""

    def __init__(
        self,
        status: int = 200,
        *,
        json: Any = None,
        text: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Store the canned response data."""
        self.status = status
        self.headers = headers or {}
        self._json = json
        self._text = text if text is not None else (json_module.dumps(json) if json is not None else "")

    async def text(self) -> str:
        """Return the canned response body as text."""
        return self._text

    async def json(self, content_type: str | None = None) -> Any:
        """Return the canned response body decoded as JSON."""
        del content_type
        return self._json if self._json is not None else json_module.loads(self._text)

    async def __aenter__(self) -> "FakeResponse":
        """Enter as an async context manager, mirroring aiohttp's request flow."""
        return self

    async def __aexit__(self, *_exc_info: object) -> bool:
        """Exit the async context manager."""
        return False


class FakeExceptionResponse:
    """A queued fake response that raises when the request is actually made."""

    def __init__(self, exc: BaseException) -> None:
        """Store the exception to raise."""
        self._exc = exc

    async def __aenter__(self) -> None:
        """Raise the stored exception, mirroring a failed real request."""
        raise self._exc

    async def __aexit__(self, *_exc_info: object) -> bool:
        """Exit the async context manager."""
        return False


class FakeSession:  # pylint: disable=too-few-public-methods
    """A fake ``aiohttp.ClientSession`` that serves queued GET responses in order."""

    def __init__(self, responses: list[Any]) -> None:
        """Store the response queue and an empty call log."""
        self._queue = list(responses)
        self.calls: list[tuple[str, Mapping[str, Any] | None]] = []

    def get(self, url: str, *, params: Mapping[str, Any] | None = None, **_kwargs: Any) -> Any:
        """Record the call and return the next queued response."""
        self.calls.append((url, params))
        if not self._queue:
            raise AssertionError(f"No more fake responses queued for GET {url}")
        return self._queue.pop(0)
