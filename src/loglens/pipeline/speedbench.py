from __future__ import annotations

import resource
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

from loglens.pipeline.parser import detect_format, parse_line
from loglens.pipeline.run import run, RunConfig
from loglens.pipeline.turbo import scan_file


@dataclass
class BenchResult:
    mode: str
    lines: int
    seconds: float
    lines_per_s: int
    time_to_first_anomaly: Optional[float]
    anomalies: int
    peak_mb: float


def _peak_mb() -> float:
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return ru / 1024 if sys.platform != "darwin" else ru / (1024 * 1024)


def bench_file(path: str, modes: List[str], workers: int = 4) -> List[BenchResult]:
    results = []

    lines = [l.rstrip("\n") for l in open(path, encoding="utf-8", errors="replace") if l.strip()]
    fmt = detect_format(lines[0]) if lines else "generic"
    entries = [e for e in (parse_line(l, fmt) for l in lines) if e is not None]

    for mode in modes:
        t0 = time.perf_counter()
        ttfa = None
        if mode == "turbo":
            res = scan_file(path, workers=workers)
            n_anom = len(res.anomalies())
            n_lines = res.parsed_lines
        else:
            out = run(entries, RunConfig(mode=mode))
            flagged = list(out.flagged)
            n_anom = sum(bool(f) for f in flagged)
            n_lines = len(entries)
        dt = time.perf_counter() - t0
        if n_anom:
            ttfa = dt  # single-shot pipeline: first insight == full run time
        results.append(BenchResult(
            mode=mode, lines=n_lines, seconds=round(dt, 3),
            lines_per_s=int(n_lines / dt) if dt else 0,
            time_to_first_anomaly=round(ttfa, 3) if ttfa else None,
            anomalies=n_anom, peak_mb=round(_peak_mb(), 1)))
    return results


def to_markdown(results: List[BenchResult], source: str) -> str:
    rows = ["| Mode | Lines | Time (s) | Lines/s | Anomalies | Time-to-insight (s) | Peak RAM (MB) |",
            "|---|---|---|---|---|---|---|"]
    for r in results:
        rows.append(f"| {r.mode} | {r.lines:,} | {r.seconds} | {r.lines_per_s:,} "
                    f"| {r.anomalies} | {r.time_to_first_anomaly or '—'} | {r.peak_mb} |")
    return (f"### LogLens Benchmark — `{source}`\n\n" + "\n".join(rows) +
            "\n\n*Zero setup. One box. No cluster, no indexing pipeline — "
            "compare to Splunk/Hadoop time-to-first-insight measured in minutes-to-hours of setup.*\n")