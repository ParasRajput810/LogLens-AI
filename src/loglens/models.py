from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LogEntry:
    timestamp: str
    level: str
    service: str
    message: str
    raw: str
    metadata: dict = field(default_factory=dict)