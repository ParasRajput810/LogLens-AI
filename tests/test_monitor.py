import logging
import time

import loglens
from loglens.alerts import AlertDispatcher, load_dotenv, alerters_from_env
from loglens.api import Anomaly
from loglens.monitor import heuristic_rca_line
import sys

class FakeChannel:
    name = "fake"

    def __init__(self, fail: bool = False):
        self.got = []
        self.fail = fail

    def send(self, app, anomaly, rca_line=None):
        if self.fail:
            raise RuntimeError("channel down")
        self.got.append((app, anomaly, rca_line))


def A(msg="db connection refused", level="ERROR", service="db", score=0.9):
    return Anomaly(level=level, score=score, message=msg, service=service,
                   reasons=["severity " + level])


def test_dispatcher_fans_out_and_includes_rca():
    ch1, ch2 = FakeChannel(), FakeChannel()
    d = AlertDispatcher([ch1, ch2], app="api", cooldown=0)
    assert d.dispatch(A(), "pool exhausted")
    assert ch1.got[0][0] == "api" and ch1.got[0][2] == "pool exhausted"
    assert len(ch2.got) == 1


def test_dispatcher_cooldown_dedupes_storms():
    ch = FakeChannel()
    d = AlertDispatcher([ch], app="api", cooldown=300)
    # an error storm: same problem, different ids
    for i in range(50):
        d.dispatch(A(f"db connection refused host=db-{i} order={1000+i}"))
    assert len(ch.got) == 1, "a storm must become ONE alert"
    assert d.suppressed == 49
    # a DIFFERENT problem still gets through
    d.dispatch(A("disk full on /var", level="CRITICAL", service="storage"))
    assert len(ch.got) == 2


def test_dispatcher_hourly_cap():
    ch = FakeChannel()
    d = AlertDispatcher([ch], app="api", cooldown=0, max_per_hour=3)
    for i in range(10):
        d.dispatch(A(f"totally unique problem number{'x' * i}"))
    assert len(ch.got) == 3


def test_dispatcher_channel_failure_is_isolated():
    bad, good = FakeChannel(fail=True), FakeChannel()
    d = AlertDispatcher([bad, good], app="api", cooldown=0)
    assert d.dispatch(A())          # still True: one channel worked
    assert len(good.got) == 1 and d.errors == 1

def test_dotenv_and_alerters_from_env(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGLENS_SLACK_WEBHOOK", raising=False)
    monkeypatch.delenv("LOGLENS_TEAMS_WEBHOOK", raising=False)
    monkeypatch.delenv("LOGLENS_EMAIL_SMTP_HOST", raising=False)
    monkeypatch.delenv("LOGLENS_EMAIL_TO", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# channels\n"
        "LOGLENS_SLACK_WEBHOOK=https://hooks.slack.example/abc\n"
        "LOGLENS_EMAIL_SMTP_HOST=smtp.example.com\n"
        "LOGLENS_EMAIL_TO=oncall@x.com, dev@x.com\n")
    chans = alerters_from_env(str(env))
    names = sorted(c.name for c in chans)
    assert names == ["email", "slack"]
    email = [c for c in chans if c.name == "email"][0]
    assert email.to == ["oncall@x.com", "dev@x.com"]

def test_heuristic_rca_line():
    assert "refusing connections" in heuristic_rca_line(A())
    assert "memory" in heuristic_rca_line(A("worker killed: out of memory"))
    assert "slowly" in heuristic_rca_line(A("payment timeout after 30s"))

def test_init_alerts_on_anomaly_with_rca_line():
    ch = FakeChannel()
    m = loglens.init(app_name="checkout", alerters=[ch], cooldown=0,
                     min_window=5, rescore_every=10)
    lg = logging.getLogger("checkout.orders")
    lg.setLevel(logging.DEBUG)
    try:
        for i in range(20):
            lg.info("order processed ok %d", i % 3)
        lg.critical("database connection refused during checkout")
        m.handler.flush()
        deadline = time.time() + 5
        while not ch.got and time.time() < deadline:
            time.sleep(0.05)            
    finally:
        m.stop()
    assert ch.got, "alert must reach the channel"
    app, anomaly, rca_line = ch.got[0]
    assert app == "checkout"
    assert anomaly.level == "CRITICAL"
    assert rca_line and "connection" in rca_line.lower()


def test_init_min_alert_level_filters():
    ch = FakeChannel()
    m = loglens.init(app_name="svc", alerters=[ch], cooldown=0,
                     min_alert_level="CRITICAL", min_window=3,
                     rescore_every=5)
    lg = logging.getLogger("svc.x")
    lg.setLevel(logging.DEBUG)
    try:
        for i in range(10):
            lg.info("ok %d", i)
        lg.error("payment gateway timeout order=1")   # ERROR < CRITICAL bar
        m.handler.flush()
        time.sleep(0.3)
    finally:
        m.stop()
    assert ch.got == []


def test_init_captures_uncaught_crash():
    
    ch = FakeChannel()
    m = loglens.init(app_name="svc", alerters=[ch], cooldown=0, min_window=5)
    try:
        try:
            raise ValueError("boom during startup")
        except ValueError:
            sys.excepthook(*sys.exc_info())     # what Python does on crash
    finally:
        m.stop()
    assert ch.got, "crash must produce an alert"
    _, anomaly, rca_line = ch.got[0]
    assert anomaly.level == "FATAL" and "ValueError" in anomaly.message
    assert rca_line


def test_init_stop_detaches_cleanly():
    root = logging.getLogger()
    before = list(root.handlers)
    m = loglens.init(app_name="tmp", alerters=[], min_window=5)
    assert len(root.handlers) == len(before) + 1
    m.stop()
    assert list(root.handlers) == before