"""Thread-safe, persistent storage for all requests."""

import json
import logging
import threading
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bots.message import Message

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class Request:
    """Represents a user's arXiv search subscription."""

    id: tuple[str, ...]
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    owner_id: int
    message: Message

    def to_dict(self) -> dict[str, Any]:
        """Convert the request to a dictionary."""
        data = asdict(self)
        data["message"] = self.message.to_dict()
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Request":
        """Convert a dictionary to a request."""
        return Request(
            uuid=data.get("uuid", str(uuid.uuid4())),
            id=tuple(data["id"]),
            query=data["query"],
            owner_id=data["owner_id"],
            message=Message.from_dict(data["message"]),
        )

    def __eq__(self, other: object) -> bool:
        """Check if the request is equal to another request."""
        if not isinstance(other, Request):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash the request."""
        return hash(self.id)


@dataclass(kw_only=True)
class RequestList:
    """Thread-safe, persistent storage for all requests."""

    requests: dict[str, Request] = field(default_factory=dict)
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def add(self, request: Request) -> bool:
        """Add request if not already present, thread-safe."""
        with self._lock:
            if any(r == request for r in self.requests.values()):
                return False
            self.requests[request.uuid] = request
            return True

    def remove(self, id: str) -> bool:
        """Remove a request by uuid, thread-safe."""
        with self._lock:
            if id not in self.requests:
                return False
            del self.requests[id]
            return True

    @classmethod
    def load_from_file(cls, file_path: Path) -> "RequestList":
        """Load requests from file, return empty if file missing/corrupted."""
        if not file_path.exists():
            return cls(requests={})

        try:
            with file_path.open("r") as f:
                raw = json.load(f)
            return cls(requests={data["uuid"]: Request.from_dict(data) for data in raw})
        except (OSError, json.JSONDecodeError):
            logger.exception("Error loading request file.")
            return cls(requests={})
        except Exception:
            logger.exception("Error loading request file.")
            return cls(requests={})

    def save_to_file(self, file_path: Path) -> None:
        """Save all requests to file, thread-safe."""
        try:
            with self._lock, file_path.open("w") as f:
                json.dump([r.to_dict() for r in self.requests.values()], f, indent=2)

        except Exception:
            logger.exception("Error saving request file")

    def __iter__(self) -> Iterator[Request]:
        """Iterate over the requests."""
        with self._lock:
            return iter(list(self.requests.values()))

    def __len__(self) -> int:
        """Get the number of requests."""
        with self._lock:
            return len(self.requests)

    def __getitem__(self, id: str) -> Request:
        """Get a request by id."""
        with self._lock:
            return self.requests[id]

    def get(self, id: str) -> Request | None:
        """Get a request by id."""
        with self._lock:
            return self.requests.get(id)

    def ids(self) -> list[str]:
        """Get all request ids."""
        with self._lock:
            return list(self.requests.keys())
