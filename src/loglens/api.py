from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from loglens.models import LogEntry
from loglens.pipeline.detector import DetectionResult
from loglens.pipeline.parser import StreamParser
from loglens.pipeline.run import RunConfig, run
from loglens.llm import run_ask
from loglens.pipeline.ingestion import stream_command, stream_lines
from loglens.llm import LLMConfig
from loglens.llm import run_rca
from loglens.output.html_report import render_html_report
from loglens.llm import save_report

_LEVEL_WEIGHT = {
    "EMERGENCY": 7, "EMERG": 7, "PANIC": 7, "ALERT": 6, "FATAL": 6,
    "CRITICAL": 5, "CRIT": 5, "ERROR": 4, "ERR": 4, "WARN": 3,
    "WARNING": 3, "NOTICE": 2, "INFO": 1, "DEBUG": 0, "TRACE": 0,
}


@dataclass
class Anomaly:

    level: str
    score: float
    message: str
    service: str = "unknown"
    timestamp: str = ""
    reasons: List[str] = field(default_factory=list)
    raw: str = ""
    index: Optional[int] = None
    entry: Optional[LogEntry] = field(default=None, repr=False)

    @property
    def severity(self) -> int:
        return _LEVEL_WEIGHT.get(self.level.upper(), 2)

    def __str__(self) -> str:
        why = ("  [" + "; ".join(self.reasons) + "]") if self.reasons else ""
        svc = f" {self.service}" if self.service not in ("", "unknown") else ""
        return f"[{self.level}]{svc} (score {self.score:.2f}) {self.message}{why}"

    def to_dict(self) -> Dict[str, Any]:
        return {"level": self.level, "score": round(self.score, 4),
                "message": self.message, "service": self.service,
                "timestamp": self.timestamp, "reasons": list(self.reasons),
                "index": self.index}


def _to_anomaly(e: LogEntry, score: float, reasons, idx) -> Anomaly:
    return Anomaly(level=e.level, score=float(score), message=e.message,
                   service=e.service, timestamp=e.timestamp,
                   reasons=list(reasons), raw=e.raw, index=idx, entry=e)


@dataclass
class AnalysisResult:

    anomalies: List[Anomaly]
    entries: List[LogEntry]
    detection: DetectionResult = field(repr=False)
    incident: bool = False
    incident_note: str = ""
    format: Optional[str] = None

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def groups(self):
        return self.detection.groups

    def by_level(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for a in self.anomalies:
            out[a.level.upper()] = out.get(a.level.upper(), 0) + 1
        return out

    def summary(self) -> Dict[str, Any]:
        return {"entries": self.total, "anomalies": len(self.anomalies),
                "incident": self.incident, "by_level": self.by_level(),
                "format": self.format}

    def __len__(self) -> int:
        return len(self.anomalies)

    def __iter__(self):
        return iter(self.anomalies)


def _wrap(entries: List[LogEntry], det: DetectionResult,
          fmt: Optional[str]) -> AnalysisResult:
    order = np.argsort(-det.scores, kind="stable")
    anomalies = [_to_anomaly(entries[i], det.scores[i], det.reasons[i], int(i))
                 for i in order if det.flagged[i]]
    return AnalysisResult(anomalies=anomalies, entries=entries, detection=det,
                          incident=det.incident_mode,
                          incident_note=det.incident_note, format=fmt)


def analyze_entries(entries, config: Optional[RunConfig] = None,
                    baseline: Optional[dict] = None,
                    fmt: Optional[str] = None) -> AnalysisResult:
    entries = list(entries)
    det = run(entries, config or RunConfig(), baseline=baseline)
    return _wrap(entries, det, fmt)


def _parse(lines: Iterable[str], fmt: Optional[str]):
    parser = StreamParser(fmt=fmt)
    entries = list(parser.parse_all(lines))
    return entries, parser.first_format


def _needs_loop(source: Optional[str]) -> bool:
    return source is not None and (
        source == "stdin" or source.startswith(("http://", "https://", "cmd:")))


def _validate(source, lines, cmd) -> None:
    given = [n for n, v in (("source", source), ("lines", lines),
                            ("cmd", cmd)) if v is not None]
    if len(given) != 1:
        raise ValueError(
            "analyze() takes exactly one of: source, lines, cmd "
            f"(got {', '.join(given) or 'none'})")


async def analyze_async(source: Optional[str] = None, *,
                        lines: Optional[Iterable[str]] = None,
                        cmd: Optional[str] = None,
                        mode: str = "fast",
                        sensitivity: str = "normal",
                        threshold: Optional[float] = None,
                        fmt: Optional[str] = None,
                        config: Optional[RunConfig] = None,
                        baseline: Optional[dict] = None) -> AnalysisResult:
    _validate(source, lines, cmd)
    cfg = config or RunConfig(mode=mode, sensitivity=sensitivity,
                              threshold=threshold)
    if lines is not None:
        entries, detected = _parse(lines, fmt)
    else:
        
        aiter = (stream_command(cmd) if cmd is not None
                 else stream_lines(source))
        parser = StreamParser(fmt=fmt)
        entries = []
        async for line in aiter:
            e = parser.feed(line)
            if e is not None:
                entries.append(e)
        tail = parser.flush()
        if tail is not None:
            entries.append(tail)
        detected = parser.first_format
    # run() is CPU-bound; keep the event loop responsive
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: analyze_entries(entries, cfg, baseline,
                                      fmt or detected))


def analyze(source: Optional[str] = None, *,
            lines: Optional[Iterable[str]] = None,
            cmd: Optional[str] = None,
            mode: str = "fast",
            sensitivity: str = "normal",
            threshold: Optional[float] = None,
            fmt: Optional[str] = None,
            config: Optional[RunConfig] = None,
            baseline: Optional[dict] = None) -> AnalysisResult:
    
    _validate(source, lines, cmd)
    cfg = config or RunConfig(mode=mode, sensitivity=sensitivity,
                              threshold=threshold)

    if lines is not None:
        entries, detected = _parse(lines, fmt)
        return analyze_entries(entries, cfg, baseline, fmt or detected)
    if cmd is None and not _needs_loop(source):
        with open(source, "r", errors="replace") as f:
            entries, detected = _parse((ln.rstrip("\n") for ln in f), fmt)
        return analyze_entries(entries, cfg, baseline, fmt or detected)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(analyze_async(
            source=source, cmd=cmd, fmt=fmt, config=cfg, baseline=baseline))
    raise RuntimeError(
        "analyze() with a URL/stdin/cmd source cannot run inside an active "
        "event loop; use `await analyze_async(...)` instead.")



def _llm_config(provider: str = "", model: str = "", api_key: str = "",
                config=None):
    
    return config or LLMConfig.from_env(provider=provider, model=model,
                                        api_key=api_key)


def rca_for_anomalies(anomalies: List[Anomaly], *, source_name: str = "",
                      provider: str = "", model: str = "",
                      api_key: str = "", config=None):
    
    
    cfg = _llm_config(provider, model, api_key, config)
    return run_rca(
        [a.entry for a in anomalies if a.entry is not None],
        cfg,
        scores=[a.score for a in anomalies],
        reasons=["; ".join(a.reasons) for a in anomalies],
        source_name=source_name,
    )


def ask_about_anomalies(question: str, anomalies: List[Anomaly], *,
                        source_name: str = "", provider: str = "",
                        model: str = "", api_key: str = "", config=None):
    
    cfg = _llm_config(provider, model, api_key, config)
    return run_ask(
        question,
        [a.entry for a in anomalies if a.entry is not None],
        cfg,
        scores=[a.score for a in anomalies],
        reasons=["; ".join(a.reasons) for a in anomalies],
        source_name=source_name,
    )


def html_for_anomalies(anomalies: List[Anomaly], *, total_lines: int,
                       source_name: str = "", rca=None) -> str:
    
    levels: Dict[str, int] = {}
    for a in anomalies:
        levels[a.level.upper()] = levels.get(a.level.upper(), 0) + 1
    return render_html_report(
        source=source_name or "loglens",
        total_lines=total_lines,
        anomalies=[a.entry for a in anomalies if a.entry is not None],
        level_counts=levels,
        rca_markdown=getattr(rca, "report", None) if rca is not None else None,
        rca_meta={"provider": rca.provider, "model": rca.model}
        if rca is not None else None,
        scores=[a.score for a in anomalies],
    )


def _install_result_ai_methods():

    def rca(self, *, provider: str = "", model: str = "", api_key: str = "",
            config=None):
        return rca_for_anomalies(self.anomalies,
                                 source_name=self.format or "analysis",
                                 provider=provider, model=model,
                                 api_key=api_key, config=config)

    def ask(self, question: str, *, provider: str = "", model: str = "",
            api_key: str = "", config=None):
        return ask_about_anomalies(question, self.anomalies,
                                   source_name=self.format or "analysis",
                                   provider=provider, model=model,
                                   api_key=api_key, config=config)

    def save_html(self, path: str, *, rca=None, source_name: str = "") -> str:
        html = html_for_anomalies(self.anomalies, total_lines=self.total,
                                  source_name=source_name or "analysis",
                                  rca=rca)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def save_rca(self, path: str, *, rca=None, **kw) -> str:
        
        rca = rca or self.rca(**kw)
        save_report(rca, path, source_name="analysis")
        return path

    AnalysisResult.rca = rca
    AnalysisResult.ask = ask
    AnalysisResult.save_html = save_html
    AnalysisResult.save_rca = save_rca


_install_result_ai_methods()