"""Queue-backed change publishing."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any


class ChangePublisher:
    """Publishes file-system change events to a queue as JSON messages."""

    def __init__(self, send: Callable[[str], None]) -> None:
        self._send = send

    def publish(self, event: Mapping[str, Any]) -> None:
        self._send(json.dumps(dict(event)))
