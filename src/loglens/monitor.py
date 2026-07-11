from __future__ import annotations

import atexit
import logging
import queue
import sys
import threading
from typing import List, Optional
import traceback
from loglens.alerts import AlertDispatcher, alerters_from_env, load_dotenv
from loglens.api import Anomaly
from loglens.handler import LogLensHandler
from loglens.models import LogEntry
from loglens.llm import LLMConfig
from loglens.llm.providers import LLMClient
from loglens.pipeline.detector import get_severity
from loglens.pipeline.detector import get_severity


def heuristic_rca_line(a: Anomaly) -> str:
    msg = a.message.lower()
    hints = [
        (("connection refused", "connection reset", "unreachable"),
         "a dependency is down or refusing connections"),
        (("timeout", "timed out"), "a dependency is responding too slowly"),
        (("out of memory", "oom", "memoryerror"), "the process ran out of memory"),
        (("disk", "no space", "i/o error"), "storage/disk trouble"),
        (("permission", "denied", "unauthorized", "forbidden"),
         "an auth/permission problem"),
        (("segfault", "panic", "core dump"), "the process crashed at native level"),
        (("certificate", "ssl", "tls"), "a certificate/TLS problem"),
        (("replication", "split-brain"), "database replication trouble"),
    ]
    for keys, verdict in hints:
        if any(k in msg for k in keys):
            where = a.service if a.service not in ("", "unknown") else "the app"
            return f"{verdict} (seen in {where})"
    if a.reasons:
        return a.reasons[0]
    return f"{a.level} condition in {a.service or 'the app'}"


def ai_rca_line(a: Anomaly, timeout: int = 20) -> Optional[str]:
    try:
        
        cfg = LLMConfig.from_env()
        cfg.max_tokens = 60
        cfg.timeout = timeout
        client = LLMClient(cfg)
        text = client.chat([
            {"role": "system",
             "content": "You are an SRE. Reply with ONE short sentence (max "
                        "20 words) stating the most likely root cause. No "
                        "preamble, no markdown."},
            {"role": "user",
             "content": f"level={a.level} service={a.service} "
                        f"message={a.message} signals={'; '.join(a.reasons)}"},
        ])
        line = " ".join(text.strip().splitlines())[:200]
        return line or None
    except Exception:
        return None

class Monitor:

    def __init__(self, app_name: str, dispatcher: AlertDispatcher,
                 use_ai: bool, capture_crashes: bool,
                 min_alert_level: str, **detector_kwargs):
        self.app_name = app_name
        self.dispatcher = dispatcher
        self.use_ai = use_ai
        self._min_sev = _sev(min_alert_level)
        self._q: "queue.Queue[Optional[Anomaly]]" = queue.Queue(maxsize=1000)
        self._worker = threading.Thread(target=self._drain, daemon=True,
                                        name="loglens-alerts")
        self._worker.start()
        self.handler = LogLensHandler(on_anomaly=self._enqueue,
                                      **detector_kwargs)
        logging.getLogger().addHandler(self.handler)
        self._old_excepthook = None
        if capture_crashes:
            self._old_excepthook = sys.excepthook
            sys.excepthook = self._excepthook
        atexit.register(self.stop)

    def _enqueue(self, a: Anomaly) -> None:
        if get_severity(a.level) > self._min_sev:
            return                       # below the alerting bar
        try:
            self._q.put_nowait(a)
        except queue.Full:
            pass                         # protect the app over the alert

    def _excepthook(self, exc_type, exc, tb) -> None:
        
        frame = traceback.extract_tb(tb)[-1] if tb else None
        where = f"{frame.filename}:{frame.lineno}" if frame else "unknown"
        a = Anomaly(level="FATAL", score=1.0,
                    message=f"uncaught {exc_type.__name__}: {exc} ({where})",
                    service=self.app_name,
                    reasons=["uncaught exception — process crashing"],
                    entry=LogEntry(level="FATAL", service=self.app_name,
                                   message=str(exc), raw=str(exc)))
        # deliver synchronously — the process is about to die
        self.dispatcher.dispatch(a, self._rca_line(a))
        if self._old_excepthook:
            self._old_excepthook(exc_type, exc, tb)

    def _rca_line(self, a: Anomaly) -> str:
        if self.use_ai:
            line = ai_rca_line(a)
            if line:
                return line
        return heuristic_rca_line(a)

    def _drain(self) -> None:
        while True:
            a = self._q.get()
            if a is None:
                return
            try:
                self.dispatcher.dispatch(a, self._rca_line(a))
            except Exception:
                pass                     # alerting must never hurt the app

    def stats(self) -> dict:
        s = self.dispatcher.stats()
        s.update(self.handler.summary())
        return s

    def stop(self) -> None:
        try:
            logging.getLogger().removeHandler(self.handler)
        except Exception:
            pass
        if self._old_excepthook is not None:
            sys.excepthook = self._old_excepthook
            self._old_excepthook = None
        try:
            self._q.put_nowait(None)
        except Exception:
            pass


def _sev(level: str) -> int:
    return get_severity(level)


def init(app_name: str = "app", *, dotenv: str = ".env",
         rca: bool = True, capture_crashes: bool = True,
         min_alert_level: str = "ERROR", cooldown: float = 300.0,
         max_per_hour: int = 30, alerters: Optional[List] = None,
         **detector_kwargs) -> Monitor:
    load_dotenv(dotenv)
    channels = alerters if alerters is not None else alerters_from_env(dotenv)
    dispatcher = AlertDispatcher(channels, app=app_name,
                                 cooldown=cooldown, max_per_hour=max_per_hour)
    return Monitor(app_name, dispatcher, use_ai=rca,
                   capture_crashes=capture_crashes,
                   min_alert_level=min_alert_level, **detector_kwargs)