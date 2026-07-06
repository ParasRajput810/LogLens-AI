from __future__ import annotations

import os
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

_RE_TS_ISO = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:z|[+-]\d{2}:?\d{2})?\b",
    re.I,
)
_RE_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_RE_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_RE_NUMTOK = re.compile(r"\b[a-z_]*\d[\w]*\b", re.I)   # any token with a digit
_RE_WS = re.compile(r"\s+")


def mask_template(msg: str) -> str:
    if not msg:
        return "<​empty>"
    s = msg.lower()
    s = _RE_TS_ISO.sub("<​ts>", s)
    s = _RE_UUID.sub("<​uuid>", s)
    s = _RE_IP.sub("<​ip>", s)
    s = _RE_NUMTOK.sub("<​id>", s)
    s = _RE_WS.sub(" ", s).strip()
    return s or "<​empty>"

def auto_workers(file_size: int,
                 available_mem: Optional[int] = None,
                 cpu: Optional[int] = None,
                 mem_per_worker_mb: int = 512,
                 max_cap: int = 16,
                 safety_frac: float = 0.6) -> int:
    cpu = cpu or (os.cpu_count() or 1)
    if available_mem is None:
        try:
            import psutil
            available_mem = psutil.virtual_memory().available
        except Exception:
            available_mem = 2 * 1024 ** 3        
    mem_budget = int(available_mem * safety_frac)
    mem_workers = max(1, mem_budget // (mem_per_worker_mb * 1024 ** 2))
    file_workers = max(1, file_size // (16 * 1024 ** 2))   
    return int(max(1, min(cpu, mem_workers, file_workers, max_cap)))


def split_chunks(path: str, n: int) -> List[Tuple[int, int]]:
    size = os.path.getsize(path)
    if n <= 1 or size == 0:
        return [(0, size)]
    step = size // n
    bounds = [0]
    with open(path, "rb") as f:
        for i in range(1, n):
            f.seek(i * step)
            f.readline()             
            bounds.append(f.tell())
    bounds.append(size)
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)
            if bounds[i] < bounds[i + 1]]


def _process_range(args) -> Dict[Tuple[str, str], list]:
    from loglens.pipeline.parser import detect_format, parse_line
    path, start, end = args
    local: Dict[Tuple[str, str], list] = {}
    fmt: Optional[str] = None
    with open(path, "r", errors="replace") as f:
        f.seek(start)
        pos = start
        for line in f:
            pos += len(line.encode("utf-8", "replace"))
            stripped = line.rstrip("\n")
            if stripped:
                if fmt is None:
                    fmt = detect_format(stripped)
                e = parse_line(stripped, fmt)
                if e is not None:
                    key = (e.level, mask_template(e.message))
                    slot = local.get(key)
                    if slot is None:
                        local[key] = [1, e.message, e.level, e.service]
                    else:
                        slot[0] += 1
            if pos >= end:
                break
    return local


_SEVERITY_WEIGHT = {
    "EMERGENCY": 1.0, "ALERT": 0.95, "CRITICAL": 0.9, "ERROR": 0.8,
    "WARN": 0.5, "NOTICE": 0.2, "INFO": 0.05, "DEBUG": 0.0, "TRACE": 0.0,
}


@dataclass
class Template:
    level: str
    template: str
    count: int
    sample: str
    service: str
    score: float = 0.0

    def is_anomaly(self) -> bool:
        return self.score >= 0.5


@dataclass
class ScanResult:
    total_lines: int
    parsed_lines: int
    templates: List[Template]
    workers: int

    def redundancy(self) -> float:
        u = len(self.templates)
        return 0.0 if self.parsed_lines == 0 else 1 - u / self.parsed_lines

    def anomalies(self) -> List[Template]:
        return [t for t in self.templates if t.is_anomaly()]


def score_templates(merged: Dict[Tuple[str, str], list],
                    total: int) -> List[Template]:
    if total == 0:
        return []
    unique = len(merged)
    low_redundancy = unique > 0.5 * total   

    out: List[Template] = []
    for (level, tmpl), (count, sample, lvl, svc) in merged.items():
        rarity = math.log1p(total / count) / math.log1p(total)   # 0..1
        sev = _SEVERITY_WEIGHT.get(lvl, 0.1)
        if low_redundancy:
            score = 0.75 * sev + 0.25 * rarity    
        else:
            score = 0.55 * rarity + 0.45 * sev
        out.append(Template(level=lvl, template=tmpl, count=count,
                            sample=sample, service=svc,
                            score=round(min(score, 1.0), 4)))
    out.sort(key=lambda t: t.score, reverse=True)
    return out


def scan_file(path: str, workers: Optional[int] = None,
              **auto_kw) -> ScanResult:
    size = os.path.getsize(path)
    w = workers or auto_workers(size, **auto_kw)
    chunks = split_chunks(path, w)
    w = len(chunks)

    merged: Dict[Tuple[str, str], list] = {}
    if w == 1:
        merged = _process_range((path, chunks[0][0], chunks[0][1]))
    else:
        import multiprocessing as mp
        with mp.Pool(w) as pool:
            for local in pool.imap_unordered(
                    _process_range, [(path, s, e) for s, e in chunks]):
                for k, v in local.items():
                    slot = merged.get(k)
                    if slot is None:
                        merged[k] = v
                    else:
                        slot[0] += v[0]

    parsed = sum(v[0] for v in merged.values())
    templates = score_templates(merged, parsed)
    return ScanResult(total_lines=parsed, parsed_lines=parsed,
                      templates=templates, workers=w)


def analyze(path: str, workers: Optional[int] = None, **auto_kw) -> dict:
    res = scan_file(path, workers=workers, **auto_kw)
    anomalies = res.anomalies()
    return {
        "file": path,
        "workers": res.workers,
        "parsed_lines": res.parsed_lines,
        "unique_templates": len(res.templates),
        "redundancy": round(res.redundancy(), 4),
        "anomaly_count": len(anomalies),
        "top_anomalies": [
            {"score": t.score, "level": t.level, "count": t.count,
             "service": t.service, "sample": t.sample[:200]}
            for t in anomalies[:20]
        ],
    }