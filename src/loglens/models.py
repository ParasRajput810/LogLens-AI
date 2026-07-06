from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class LogEntry:
    timestamp: str = ""
    level: str = "INFO"
    service: str = "unknown"
    message: str = ""
    raw: str = ""
    parsed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "service": self.service,
            "message": self.message,
            "parsed": self.parsed,
            "metadata": self.metadata,
        }