from __future__ import annotations

import json
import os
import smtplib
import time
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

from loglens.api import Anomaly

_LEVEL_EMOJI = {"EMERGENCY": "🟥", "ALERT": "🟥", "FATAL": "🟥",
                "CRITICAL": "🔴", "ERROR": "🟠", "WARN": "🟡"}
_LEVEL_COLOR = {"EMERGENCY": "#d13438", "FATAL": "#d13438",
                "CRITICAL": "#d13438", "ERROR": "#ff8c00", "WARN": "#ffd700"}


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def _fmt_text(app: str, a: Anomaly, rca_line: Optional[str]) -> str:
    emoji = _LEVEL_EMOJI.get(a.level.upper(), "🔵")
    svc = f" · {a.service}" if a.service not in ("", "unknown") else ""
    lines = [f"{emoji} [{app}] {a.level}{svc} (score {a.score:.2f})",
             a.message]
    if rca_line:
        lines.append(f"↳ likely cause: {rca_line}")
    if a.timestamp:
        lines.append(f"at {a.timestamp}")
    return "\n".join(lines)


class SlackAlerter:

    name = "slack"

    def __init__(self, webhook_url: str, timeout: int = 10):
        self.url = webhook_url
        self.timeout = timeout

    def send(self, app: str, a: Anomaly, rca_line: Optional[str] = None) -> None:
        body = json.dumps({"text": _fmt_text(app, a, rca_line)}).encode()
        req = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=self.timeout).read()


class TeamsAlerter:

    name = "teams"

    def __init__(self, webhook_url: str, timeout: int = 10):
        self.url = webhook_url
        self.timeout = timeout

    def send(self, app: str, a: Anomaly, rca_line: Optional[str] = None) -> None:
        facts = [{"name": "Level", "value": a.level},
                 {"name": "Score", "value": f"{a.score:.2f}"}]
        if a.service not in ("", "unknown"):
            facts.append({"name": "Service", "value": a.service})
        if a.timestamp:
            facts.append({"name": "When", "value": a.timestamp})
        if rca_line:
            facts.append({"name": "Likely cause", "value": rca_line})
        card = {
            "@type": "MessageCard", "@context": "http://schema.org/extensions",
            "themeColor": _LEVEL_COLOR.get(a.level.upper(), "#0078d4"),
            "summary": f"[{app}] {a.level}: {a.message[:80]}",
            "sections": [{
                "activityTitle": f"🚨 LogLens alert — {app}",
                "activitySubtitle": a.message,
                "facts": facts,
            }],
        }
        req = urllib.request.Request(
            self.url, data=json.dumps(card).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=self.timeout).read()


class EmailAlerter:

    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str,
                 to: List[str], sender: str = "", use_tls: bool = True,
                 timeout: int = 15):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.to = to
        self.sender = sender or user
        self.use_tls = use_tls
        self.timeout = timeout

    def send(self, app: str, a: Anomaly, rca_line: Optional[str] = None) -> None:
        msg = MIMEText(_fmt_text(app, a, rca_line))
        msg["Subject"] = f"[LogLens] {app}: {a.level} — {a.message[:70]}"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
            if self.use_tls:
                s.starttls()
            if self.user:
                s.login(self.user, self.password)
            s.sendmail(self.sender, self.to, msg.as_string())


def alerters_from_env(dotenv: str = ".env") -> List:
    load_dotenv(dotenv)
    out: List = []
    slack = os.getenv("LOGLENS_SLACK_WEBHOOK", "").strip()
    if slack:
        out.append(SlackAlerter(slack))
    teams = os.getenv("LOGLENS_TEAMS_WEBHOOK", "").strip()
    if teams:
        out.append(TeamsAlerter(teams))
    host = os.getenv("LOGLENS_EMAIL_SMTP_HOST", "").strip()
    to = [t.strip() for t in os.getenv("LOGLENS_EMAIL_TO", "").split(",")
          if t.strip()]
    if host and to:
        out.append(EmailAlerter(
            host=host,
            port=int(os.getenv("LOGLENS_EMAIL_SMTP_PORT", "587")),
            user=os.getenv("LOGLENS_EMAIL_USER", ""),
            password=os.getenv("LOGLENS_EMAIL_PASSWORD", ""),
            to=to,
            sender=os.getenv("LOGLENS_EMAIL_FROM", ""),
        ))
    return out


class AlertDispatcher:


    def __init__(self, alerters: List, *, app: str = "app",
                 cooldown: float = 300.0, max_per_hour: int = 30):
        self.alerters = alerters
        self.app = app
        self.cooldown = cooldown
        self.max_per_hour = max_per_hour
        self._last_sent: Dict[str, float] = {}
        self._hour_stamps: List[float] = []
        self.sent = 0
        self.suppressed = 0
        self.errors = 0

    @staticmethod
    def _key(a: Anomaly) -> str:
        import re
        masked = re.sub(r"\S*\d\S*", "<id>", a.message.lower())
        return f"{a.level.upper()}|{a.service}|{masked[:120]}"

    def _allowed(self, a: Anomaly) -> bool:
        now = time.time()
        self._hour_stamps = [t for t in self._hour_stamps if now - t < 3600]
        if len(self._hour_stamps) >= self.max_per_hour:
            return False
        key = self._key(a)
        if now - self._last_sent.get(key, 0.0) < self.cooldown:
            return False
        self._last_sent[key] = now
        self._hour_stamps.append(now)
        return True

    def dispatch(self, a: Anomaly, rca_line: Optional[str] = None) -> bool:
        if not self.alerters or not self._allowed(a):
            self.suppressed += 1
            return False
        ok = False
        for al in self.alerters:
            try:
                al.send(self.app, a, rca_line)
                ok = True
            except Exception:
                self.errors += 1
        if ok:
            self.sent += 1
        return ok

    def stats(self) -> Dict[str, int]:
        return {"sent": self.sent, "suppressed": self.suppressed,
                "errors": self.errors,
                "channels": [al.name for al in self.alerters]}