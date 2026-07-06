from dataclasses import dataclass, field


@dataclass
class LogEntry:
    timestamp: str
    level: str
    service: str
    message: str
    raw: str
    metadata: dict = field(default_factory=dict)
    parsed: bool = True