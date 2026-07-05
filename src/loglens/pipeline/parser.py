from __future__ import annotations

import json
import re
from typing import Iterable, Iterator, Optional

from loglens.models import LogEntry

PATTERNS = {
    "JSON": None,  # handled separately
    "NGINX": re.compile(
        r'(?P<ip>\S+) - - \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+)[^"]*" (?P<status>\d+) (?P<bytes>\d+)'
    ),
    "APACHE": re.compile(
        r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+)[^"]*" (?P<status>\d+) (?P<bytes>\d+)'
    ),
    "SYSLOG": re.compile(
        r'(?P<time>\w+\s+\d+\s+[\d:]+) (?P<host>\S+) (?P<service>\S+?):? (?P<message>.+)'
    ),
    "STANDARD": re.compile(
        r'(?P<time>\d{4}-\d{2}-\d{2}T[\d:]+Z)\s+(?P<level>\w+)\s+\[(?P<service>[^\]]+)\]\s+(?P<message>.+)'
    ),
    "LOGLENS": re.compile(
        r'(?P<time>\d{4}-\d{2}-\d{2}T[\d:]+Z)\s+(?P<level>\w+)\s+(?P<service>\S+)\s+(?P<message>.+)'
    ),
}


_PRI_RE = re.compile(r"^<(\d{1,3})>\s*")
_FACILITY_SEV_RE = re.compile(
    r"\b(?:kern|user|mail|daemon|auth(?:priv)?|syslog|lpr|news|uucp|cron|ftp"
    r"|local[0-7])\.(emerg|alert|crit|err|error|warning|warn|notice|info"
    r"|debug)\b",
    re.IGNORECASE,
)
SYSLOG_SEVERITY = {
    0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL", 3: "ERROR",
    4: "WARN", 5: "NOTICE", 6: "INFO", 7: "DEBUG",
}
_TEXT_SEVERITY = {
    "emerg": "EMERGENCY", "alert": "ALERT", "crit": "CRITICAL",
    "err": "ERROR", "error": "ERROR", "warning": "WARN", "warn": "WARN",
    "notice": "NOTICE", "info": "INFO", "debug": "DEBUG",
}


def _syslog_level(line: str) -> str:
    m = _PRI_RE.match(line)
    if m:
        return SYSLOG_SEVERITY[int(m.group(1)) % 8]
    m = _FACILITY_SEV_RE.search(line)
    if m:
        return _TEXT_SEVERITY[m.group(1).lower()]
    return "INFO"


def status_to_level(status: int) -> str:
    if status in (503, 504):
        return "CRITICAL"
    if status >= 500:
        return "ERROR"
    if status == 404:
        return "INFO"
    if status >= 400:
        return "WARN"          
    return "INFO"


def detect_format(line: str) -> str:
    line = line.strip()
    if not line:
        return "UNKNOWN"
    probe = _PRI_RE.sub("", line)          
    if probe.startswith(("{", "[")):
        try:
            json.loads(probe)
            return "JSON"
        except ValueError:
            pass
    for fmt, pattern in PATTERNS.items():
        if fmt == "JSON":
            continue
        if pattern and pattern.match(probe):
            return fmt
    return "PLAINTEXT"


def parse_line(line: str, fmt: str) -> Optional[LogEntry]:
    line = line.strip()
    if not line:
        return None
    try:
        if fmt == "JSON":
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return LogEntry(
                timestamp=str(data.get("timestamp", data.get("time", ""))),
                level=str(data.get("level", data.get("severity", "INFO"))).upper(),
                service=str(data.get("service", data.get("logger", "unknown"))),
                message=str(data.get("message", data.get("msg", line))),
                raw=line,
                metadata={k: v for k, v in data.items()
                          if k not in ("timestamp", "time", "level",
                                       "severity", "service", "logger",
                                       "message", "msg")},
            )
        if fmt == "STANDARD":
            m = PATTERNS["STANDARD"].match(line)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level=m.group("level").upper(),
                    service=m.group("service"),
                    message=m.group("message").strip(),
                    raw=line,
                )
        if fmt in ("NGINX", "APACHE"):
            m = PATTERNS[fmt].match(line)
            if m:
                status = int(m.group("status"))
                return LogEntry(
                    timestamp=m.group("time"),
                    level=status_to_level(status),         
                    service=fmt.lower(),
                    message=f'{m.group("method")} {m.group("path")} {status}',
                    raw=line,
                    metadata={"ip": m.group("ip"), "status": m.group("status")},
                )
        if fmt == "SYSLOG":
            stripped = _PRI_RE.sub("", line)
            m = PATTERNS["SYSLOG"].match(stripped)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level=_syslog_level(line),              
                    service=m.group("service").rstrip(":"),
                    message=m.group("message").strip(),
                    raw=line,
                )
        if fmt == "LOGLENS":
            m = PATTERNS["LOGLENS"].match(line)
            if m:
                return LogEntry(
                    timestamp=m.group("time"),
                    level=m.group("level").upper(),
                    service=m.group("service").strip("[]"), 
                    message=m.group("message").strip(),
                    raw=line,
                )
        return LogEntry(
            timestamp="", level="INFO", service="unknown",
            message=line, raw=line, parsed=False,
        )
    except Exception:
        return LogEntry(
            timestamp="", level="INFO", service="unknown",
            message=line, raw=line, parsed=False,
        )


_CONTINUATION_RE = re.compile(
    r"^[ \t]+\S"
    r"|^(?:at\s+\S"
    r"|Caused by:"
    r"|\.\.\.\s*\d+\s+more"
    r"|Traceback \(most recent call last\)"
    r"|File \")"
)

_MAX_CONTINUATION = 200      


class StreamParser:
    
    def __init__(self, fmt: Optional[str] = None):
        self.forced_fmt = fmt
        self.sticky: Optional[str] = fmt
        self.first_format: Optional[str] = None
        self._pending: Optional[LogEntry] = None
        self._pending_continuations = 0
        self.stats = {"lines": 0, "blank": 0, "continuations": 0,
                      "fallback": 0, "format_switches": 0}

    def _sticky_matches(self, line: str) -> bool:
        fmt = self.sticky
        if fmt is None:
            return False
        if fmt == "JSON":
            return line.lstrip().startswith("{")
        if fmt in ("PLAINTEXT", "UNKNOWN"):
            return False
        pattern = PATTERNS.get(fmt)
        return bool(pattern and pattern.match(_PRI_RE.sub("", line)))

    def _format_for(self, line: str) -> str:
        if self.forced_fmt:
            return self.forced_fmt
        if self._sticky_matches(line):
            return self.sticky                      
        detected = detect_format(line)              
        if detected in ("PLAINTEXT", "UNKNOWN"):
            return self.sticky or detected
        if self.sticky is not None and detected != self.sticky:
            self.stats["format_switches"] += 1
        self.sticky = detected
        return detected

    def feed(self, line: str) -> Optional[LogEntry]:
        self.stats["lines"] += 1
        if not line.strip():
            self.stats["blank"] += 1
            return None

        if (self._pending is not None
                and self._pending_continuations < _MAX_CONTINUATION
                and _CONTINUATION_RE.match(line)):       
            self._pending.message += " | " + line.strip()
            self._pending.raw += "\n" + line.rstrip("\n")
            self._pending_continuations += 1
            self.stats["continuations"] += 1
            return None

        fmt = self._format_for(line)
        if self.first_format is None:
            self.first_format = fmt
        entry = parse_line(line, fmt)
        if entry is not None and not entry.parsed:
            self.stats["fallback"] += 1

        completed, self._pending = self._pending, entry
        self._pending_continuations = 0
        return completed

    def flush(self) -> Optional[LogEntry]:
        completed, self._pending = self._pending, None
        return completed

    def parse_all(self, lines: Iterable[str]) -> Iterator[LogEntry]:
        for line in lines:
            entry = self.feed(line)
            if entry is not None:
                yield entry
        entry = self.flush()
        if entry is not None:
            yield entry