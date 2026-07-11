from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from loglens.models import LogEntry


_MASKS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\b0[xX][0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-fA-F]{12,}\b"), "<hex>"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d{2,5})?\b"), "<ip>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][\d:]{5,8}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?\b"), "<ts>"),
    (re.compile(r"\b\d+(\.\d+)?\s*(ms|s|sec|seconds?|min|minutes?|h|hours?"
                r"|kb|mb|gb|tb|kib|mib|gib|bytes?|%)\b", re.IGNORECASE), r"<num>\2"),
    (re.compile(r"\b\d+(\.\d+)?\b"), "<num>"),
    (re.compile(r'"[^"]*"'), "<str>"),
    (re.compile(r"'[^']*'"), "<str>"),
    (re.compile(r"\S*\d\S*"), "<id>"),
]

_WS = re.compile(r"\s+")


def template_key(message: str) -> str:
    t = message.strip()
    for pattern, repl in _MASKS:
        t = pattern.sub(repl, t)
    t = _WS.sub(" ", t).lower()
    return t



_ISO_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})(?P<frac>\.\d+)?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?"
)
_SYSLOG_RE = re.compile(
    r"(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})"
)
_NGINX_RE = re.compile(
    r"(?P<day>\d{2})/(?P<mon>[A-Za-z]{3})/(?P<year>\d{4}):(?P<time>\d{2}:\d{2}:\d{2})"
)
_EPOCH_RE = re.compile(r"^(?P<sec>1\d{9})(?P<ms>\d{3})?(\.\d+)?$")

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def parse_timestamp(ts: str) -> Optional[float]:
    if not ts:
        return None
    ts = ts.strip()

    m = _EPOCH_RE.match(ts)
    if m:
        sec = float(m.group("sec"))
        if m.group("ms"):
            sec += int(m.group("ms")) / 1000.0
        return sec

    m = _ISO_RE.search(ts)
    if m:
        try:
            dt = datetime.strptime(f"{m.group('date')} {m.group('time')}",
                                   "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None

    m = _SYSLOG_RE.search(ts)
    if m:
        try:
            now = datetime.now()
            dt = datetime(now.year, _MONTHS[m.group("mon")], int(m.group("day")))
            h, mi, s = (int(x) for x in m.group("time").split(":"))
            return dt.replace(hour=h, minute=mi, second=s,
                              tzinfo=timezone.utc).timestamp()
        except (ValueError, KeyError):
            return None

    m = _NGINX_RE.search(ts)
    if m:
        try:
            dt = datetime(int(m.group("year")), _MONTHS[m.group("mon")],
                          int(m.group("day")))
            h, mi, s = (int(x) for x in m.group("time").split(":"))
            return dt.replace(hour=h, minute=mi, second=s,
                              tzinfo=timezone.utc).timestamp()
        except (ValueError, KeyError):
            return None

    return None



@dataclass
class TemplateGroup:
    key: Tuple[str, str]                 # (LEVEL, template)
    representative: LogEntry             # first entry seen
    indices: List[int] = field(default_factory=list)   # entry indices

    @property
    def count(self) -> int:
        return len(self.indices)

    @property
    def level(self) -> str:
        return self.key[0]

    @property
    def template(self) -> str:
        return self.key[1]


class TemplateRegistry:

    def __init__(self, entries: Sequence[LogEntry]):
        self.groups: List[TemplateGroup] = []
        self.entry_group: List[int] = [0] * len(entries)  # entry idx -> group idx
        index: Dict[Tuple[str, str], int] = {}
        for i, e in enumerate(entries):
            key = (e.level.upper(), template_key(e.message))
            gi = index.get(key)
            if gi is None:
                gi = len(self.groups)
                index[key] = gi
                self.groups.append(TemplateGroup(key=key, representative=e))
            self.groups[gi].indices.append(i)
            self.entry_group[i] = gi

    def __len__(self) -> int:
        return len(self.groups)

    @property
    def counts(self) -> List[int]:
        return [g.count for g in self.groups]

    def representative_indices(self) -> List[int]:
        """Index (into the original entry list) of each group's representative."""
        return [g.indices[0] for g in self.groups]