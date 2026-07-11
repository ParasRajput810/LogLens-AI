from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from loglens.models import LogEntry

_MASKS = [
    (re.compile(r"0x[0-9a-fA-F]+"), "<​HEX>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<​UUID>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<​IP>"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|kb|mb|gb)?\b", re.I), "<​NUM>"),
]


def template_of(message: str) -> str:
    t = message
    for rx, token in _MASKS:
        t = rx.sub(token, t)
    return t.strip().lower()


@dataclass
class AnomalyGroup:
    level: str
    service: str
    template: str
    sample: str                      
    count: int = 0
    max_score: float = 0.0
    indices: List[int] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


def group_anomalies(anomalies: Sequence[LogEntry],
                    scores: Optional[Sequence[float]] = None,
                    reasons: Optional[Sequence[List[str]]] = None) -> List[AnomalyGroup]:
    groups: Dict[tuple, AnomalyGroup] = {}
    for i, a in enumerate(anomalies):
        key = (a.level.upper(), a.service, template_of(a.message))
        g = groups.get(key)
        if g is None:
            g = groups[key] = AnomalyGroup(
                level=a.level.upper(), service=a.service,
                template=key[2], sample=a.message)
        g.count += 1
        g.indices.append(i)
        if scores is not None and i < len(scores):
            g.max_score = max(g.max_score, float(scores[i]))
        else:
            g.max_score = max(g.max_score, float(getattr(a, "anomaly_score", 0.0)))
        if reasons is not None and i < len(reasons) and not g.reasons:
            g.reasons = list(reasons[i])
        elif not g.reasons:
            g.reasons = list(getattr(a, "anomaly_reasons", []) or [])
    out = list(groups.values())
    out.sort(key=lambda g: (g.max_score, g.count), reverse=True)
    return out


def group_summaries(groups: Sequence[AnomalyGroup], cap: int = 40) -> List[str]:
    lines = []
    for g in groups[:cap]:
        why = f" | signals: {'; '.join(g.reasons)}" if g.reasons else ""
        lines.append(f"[{g.level}] {g.service} (x{g.count}, score {g.max_score:.2f}): "
                     f"{g.sample[:160]}{why}")
    return lines