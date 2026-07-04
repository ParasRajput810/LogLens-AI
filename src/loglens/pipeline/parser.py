import re
import json
from loglens.models import LogEntry
from typing import Optional

PATTERNS = {
    "JSON": None,  # handled separately
    "NGINX": re.compile(
        r'(?P<ip>\S+) - - \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+)[^"]*" (?P<status>\d+) (?P<bytes>\d+)'
    ),
    "APACHE": re.compile(
        r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+)[^"]*" (?P<status>\d+) (?P<bytes>\d+)'
    ),
    "SYSLOG": re.compile(
        r'(?P<time>\w+\s+\d+\s+[\d:]+) (?P<host>\S+) (?P<service>\S+): (?P<message>.+)'
    ),
    "STANDARD": re.compile(
        r'(?P<time>\d{4}-\d{2}-\d{2}T[\d:]+Z)\s+(?P<level>\w+)\s+\[(?P<service>[^\]]+)\]\s+(?P<message>.+)'
    ),
    "LOGLENS": re.compile(
    r'(?P<time>\d{4}-\d{2}-\d{2}T[\d:]+Z)\s+(?P<level>\w+)\s+(?P<service>\S+)\s+(?P<message>.+)'
),
}

def detect_format(line: str) -> str:
    line = line.strip()
    if not line:
        return "UNKNOWN"
    try:
        json.loads(line)
        return "JSON"
    except Exception:
        pass
    for fmt, pattern in PATTERNS.items():
        if fmt == "JSON":
            continue
        if pattern and pattern.match(line):
            return fmt
    return "PLAINTEXT"

def parse_line(line: str, fmt: str) -> Optional[LogEntry]:
    line = line.strip()
    if not line:
        return None
    try:
        if fmt == "JSON":
            data = json.loads(line)
            return LogEntry(
                timestamp=str(data.get("timestamp", data.get("time", ""))),
                level=str(data.get("level", data.get("severity", "INFO"))).upper(),
                service=str(data.get("service", data.get("logger", "unknown"))),
                message=str(data.get("message", data.get("msg", line))),
                raw=line,
                metadata={k: v for k, v in data.items() if k not in ("timestamp", "time", "level", "severity", "service", "logger", "message", "msg")},
            )
        if fmt == "STANDARD":
            m = PATTERNS["STANDARD"].match(line)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level=m.group("level").upper(),
                    service=m.group("service"),
                    message=m.group("message"),
                    raw=line,
                )
        if fmt in ("NGINX", "APACHE"):
            m = PATTERNS[fmt].match(line)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level="INFO" if int(m.group("status")) < 400 else "ERROR",
                    service=fmt.lower(),
                    message=f'{m.group("method")} {m.group("path")} {m.group("status")}',
                    raw=line,
                    metadata={"ip": m.group("ip"), "status": m.group("status")},
                )
        if fmt == "SYSLOG":
            m = PATTERNS["SYSLOG"].match(line)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level="INFO",
                    service=m.group("service"),
                    message=m.group("message"),
                    raw=line,
                )
        if fmt == "LOGLENS":
            m = PATTERNS["LOGLENS"].match(line)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level=m.group("level").upper(),
                    service=m.group("service"),
                    message=m.group("message").strip(),
                    raw=line,
                )
        return LogEntry(
            timestamp="",
            level="INFO",
            service="unknown",
            message=line,
            raw=line,
        )
    except Exception:
        return None  # malformed line — skip silently