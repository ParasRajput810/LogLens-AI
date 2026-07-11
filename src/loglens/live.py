from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from loglens.api import Anomaly, _to_anomaly
from loglens.models import LogEntry
from loglens.pipeline.detector import HARD_FLAG_SEVERITY, get_severity
from loglens.pipeline.parser import StreamParser
from loglens.pipeline.run import RunConfig, run
from loglens.api import rca_for_anomalies
from loglens.api import ask_about_anomalies
from loglens.api import html_for_anomalies

class LiveDetector:

    def __init__(self, window: int = 500, *, rescore_every: int = 50,
                 rescore_seconds: float = 3.0, min_window: int = 10,
                 mode: str = "fast", sensitivity: str = "normal",
                 threshold: Optional[float] = None,
                 fmt: Optional[str] = None,
                 suppress_info: bool = True,
                 config: Optional[RunConfig] = None):
        self.window = window
        self.rescore_every = max(1, rescore_every)
        self.rescore_seconds = rescore_seconds
        self.min_window = min_window
        self.suppress_info = suppress_info
        self.config = config or RunConfig(mode=mode, sensitivity=sensitivity,
                                          threshold=threshold)
        self._parser = StreamParser(fmt=fmt)
        self._win: Deque[Tuple[int, LogEntry]] = deque()
        self._reported: set[int] = set()
        self._seq = 0
        self._since = 0
        self._last = time.monotonic()
        # cumulative stream stats
        self._total = 0
        self._levels: Dict[str, int] = {}
        self._hits = 0
        self._hit_levels: Dict[str, int] = {}
        self._rescore_errors = 0
        self.anomalies: List[Anomaly] = []
        self.max_kept = 5000

    def feed(self, line: str) -> List[Anomaly]:
        e = self._parser.feed(line)
        return self.feed_entry(e) if e is not None else []

    def feed_entry(self, entry: LogEntry) -> List[Anomaly]:
        seq = self._seq
        self._seq += 1
        self._win.append((seq, entry))
        while len(self._win) > self.window:
            old_seq, _ = self._win.popleft()
            self._reported.discard(old_seq)

        self._total += 1
        lvl = entry.level.upper()
        self._levels[lvl] = self._levels.get(lvl, 0) + 1

        out: List[Anomaly] = []
        
        sev = get_severity(entry.level)
        if sev <= 2:
            score = 1.0 if sev <= HARD_FLAG_SEVERITY else 0.95
            a = _to_anomaly(entry, score,
                            [f"{lvl} severity — surfaced immediately"], seq)
            self._mark(seq, a)
            out.append(a)

        self._since += 1
        if self._due():
            out.extend(self._rescore())
        return out

    def flush(self) -> List[Anomaly]:
        tail = self._parser.flush()
        out: List[Anomaly] = []
        if tail is not None:
            out.extend(self.feed_entry(tail))
        out.extend(self._rescore(force=True))
        return out

    def _due(self) -> bool:
        if len(self._win) < self.min_window:
            return False
        return (self._since >= self.rescore_every
                or (time.monotonic() - self._last) >= self.rescore_seconds)

    def _rescore(self, force: bool = False) -> List[Anomaly]:
        self._since = 0
        self._last = time.monotonic()
        if not self._win or (not force and len(self._win) < self.min_window):
            return []
        seqs = [s for s, _ in self._win]
        entries = [e for _, e in self._win]
        try:
            det = run(entries, self.config)
        except Exception:
            
            self._rescore_errors += 1
            return []
        new: List[Anomaly] = []
        for i in range(len(entries)):
            if not det.flagged[i] or seqs[i] in self._reported:
                continue
            if self.suppress_info and self._benign_info(entries[i]):
                self._reported.add(seqs[i])
                continue
            a = _to_anomaly(entries[i], det.scores[i], det.reasons[i],
                            seqs[i])
            self._mark(seqs[i], a)
            new.append(a)
        new.sort(key=lambda a: -a.score)
        return new

    _FAILURE_WORDS = ("error", "fail", "timeout", "refused", "crash",
                      "panic", "oom", "kill", "exception", "denied",
                      "unavailable", "corrupt", "fatal")

    def _benign_info(self, e: LogEntry) -> bool:
        if get_severity(e.level) < 5:      # NOTICE and worse pass through
            return False
        low = e.message.lower()
        return not any(w in low for w in self._FAILURE_WORDS)

    def _mark(self, seq: int, a: Anomaly) -> None:
        self._reported.add(seq)
        self._hits += 1
        if len(self.anomalies) < self.max_kept:
            self.anomalies.append(a)
        lvl = a.level.upper()
        self._hit_levels[lvl] = self._hit_levels.get(lvl, 0) + 1

    @property
    def total(self) -> int:
        return self._total

    @property
    def anomaly_count(self) -> int:
        return self._hits

    def incident(self) -> bool:
        if not self._total:
            return False
        severe = sum(c for lv, c in self._levels.items()
                     if get_severity(lv) <= 3)
        return severe / self._total >= 0.30

    def summary(self) -> Dict[str, object]:
        return {"entries": self._total, "anomalies": self._hits,
                "incident": self.incident(),
                "by_level": dict(self._hit_levels),
                "rescore_errors": self._rescore_errors,
                "window": len(self._win)}


    def rca(self, *, source_name: str = "live watch", **kw):
        
        return rca_for_anomalies(self.anomalies, source_name=source_name, **kw)

    def ask(self, question: str, *, source_name: str = "live watch", **kw):
        
        return ask_about_anomalies(question, self.anomalies,
                                   source_name=source_name, **kw)

    def save_html(self, path: str, *, rca=None,
                  source_name: str = "live watch") -> str:
        
        html = html_for_anomalies(self.anomalies, total_lines=self._total,
                                  source_name=source_name, rca=rca)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path