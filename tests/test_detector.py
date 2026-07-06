import numpy as np
import pytest

from loglens.models import LogEntry
from loglens.pipeline.detector import (
    detect, detect_anomalies, cluster_summary,
    get_severity, DetectorConfig,
)


def make_entry(msg: str, level: str = "INFO", service: str = "svc") -> LogEntry:
    return LogEntry(
        timestamp="2024-01-15T10:00:00Z",
        level=level,
        service=service,
        message=msg,
        raw=msg,
    )


def dummy_vectors(n: int, dim: int = 16, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random((n, dim)).astype(np.float32)



def test_empty_input():
    res = detect([], np.zeros((0, 16)))
    assert res.summary()["entries"] == 0
    assert len(res.groups) == 0


def test_severity_mapping():
    assert get_severity("FATAL") < get_severity("ERROR")
    assert get_severity("ERROR") < get_severity("WARN")
    assert get_severity("WARN") < get_severity("INFO")
    assert get_severity("SOMETHING_UNKNOWN") == 6  # default



def test_critical_always_flagged():
    entries = [make_entry(f"routine heartbeat {i}", "INFO") for i in range(30)]
    entries.append(make_entry("kernel panic unrecoverable", "FATAL"))
    vecs = dummy_vectors(len(entries))
    res = detect(entries, vecs)
    assert res.flagged[-1], "FATAL entry should be flagged"
    assert res.scores[-1] == 1.0


def test_routine_info_not_flooding_anomalies():
    entries = [make_entry(f"request served ok {i % 5}", "INFO") for i in range(50)]
    vecs = dummy_vectors(len(entries))
    res = detect(entries, vecs)
    assert int(res.flagged.sum()) < len(entries) // 2


def test_error_keyword_boosts_score():
    entries = [make_entry(f"user login ok {i}", "INFO") for i in range(20)]
    err = make_entry("database connection refused timeout", "ERROR")
    entries.append(err)
    vecs = dummy_vectors(len(entries))
    res = detect(entries, vecs)
    assert res.scores[-1] > res.scores[0]


def test_anomaly_groups_have_templates():
    entries = [make_entry(f"disk read ok {i}", "INFO") for i in range(20)]
    for _ in range(6):
        entries.append(make_entry("payment failed: card declined", "ERROR"))
    vecs = dummy_vectors(len(entries))
    res = detect(entries, vecs)
    assert res.groups, "should produce at least one anomaly group"
    top = res.groups[0]
    assert top.template
    assert top.count >= 1
    assert isinstance(top.reasons, list) and top.reasons


def test_incident_mode_triggers_on_high_severe_share():
    entries = ([make_entry("service crash error", "ERROR") for _ in range(6)]
               + [make_entry("ok", "INFO") for _ in range(4)])
    vecs = dummy_vectors(len(entries))
    res = detect(entries, vecs)
    assert res.incident_mode is True
    assert res.incident_note


def test_detect_anomalies_wrapper():
    entries = [make_entry(f"ok {i}", "INFO") for i in range(15)]
    entries.append(make_entry("fatal segfault", "FATAL"))
    vecs = dummy_vectors(len(entries))
    normal, anomalies, labels = detect_anomalies(entries, vecs)
    assert len(anomalies) >= 1
    assert len(normal) + len(anomalies) <= len(entries) + 1  # sanity
    assert len(labels) == len(entries)


def test_cluster_summary_shape():
    labels = np.array([0, 0, 1, -1, -1, 1])
    flagged = np.array([False, False, True, True, True, False])
    s = cluster_summary(labels, flagged)
    assert s["clusters"] == 2
    assert s["noise_points"] == 2
    assert s["anomalies"] == 3


def test_config_from_sensitivity():
    low = DetectorConfig.from_sensitivity("low")
    high = DetectorConfig.from_sensitivity("high")
    assert low.flag_threshold > high.flag_threshold