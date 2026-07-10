from __future__ import annotations
import argparse
import json
import os
import sys
import time
from typing import List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import numpy as np                                          
from loglens.models import LogEntry                          
from loglens.pipeline.run import run, RunConfig               


def _load_jsonl(path: str) -> Tuple[List[LogEntry], np.ndarray]:
    entries, labels = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            entries.append(LogEntry(
                timestamp=str(o.get("timestamp", "")),
                level=str(o.get("level", "INFO")),
                service=str(o.get("service", "unknown")),
                message=str(o.get("message", "")),
                raw=line,
            ))
            labels.append(int(o.get("label", 0)))
    return entries, np.array(labels, dtype=bool)


def _load_log_with_sidecar(path: str) -> Tuple[List[LogEntry], np.ndarray]:
    from loglens.pipeline.parser import detect_format, parse_line
    lines = [l.rstrip("\n") for l in open(path, encoding="utf-8") if l.strip()]
    fmt = detect_format(lines[0]) if lines else "generic"
    entries = [e for e in (parse_line(l, fmt) for l in lines) if e is not None]
    label_path = os.path.splitext(path)[0] + ".labels"
    if os.path.exists(label_path):
        labels = np.array(
            [int(x) for x in open(label_path).read().split()], dtype=bool)
    else:
        labels = np.zeros(len(entries), dtype=bool)
    return entries, labels[:len(entries)]


def load_task(path: str):
    if path.endswith(".jsonl"):
        return _load_jsonl(path)
    return _load_log_with_sidecar(path)


def score(pred: np.ndarray, truth: np.ndarray) -> dict:
    tp = int(np.sum(pred & truth))
    fp = int(np.sum(pred & ~truth))
    fn = int(np.sum(~pred & truth))
    tn = int(np.sum(~pred & ~truth))
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec, "recall": rec, "f1": f1}


def evaluate(path: str, cfg: RunConfig) -> dict:
    entries, truth = load_task(path)
    t0 = time.perf_counter()
    res = run(entries, cfg)
    dt = time.perf_counter() - t0
    m = score(np.asarray(res.flagged), truth)
    m.update(task=os.path.basename(path), n=len(entries),
             positives=int(truth.sum()), seconds=round(dt, 3),
             lines_per_s=round(len(entries) / dt) if dt else 0)
    return {"metrics": m, "result": res}


def main():
    ap = argparse.ArgumentParser(description="LogLens eval harness")
    ap.add_argument("tasks", nargs="+", help="labeled .jsonl or .log files")
    ap.add_argument("--mode", default="fast", choices=["fast", "deep"])
    ap.add_argument("--sensitivity", default="normal",
                    choices=["low", "normal", "high"])
    ap.add_argument("--auto-threshold", action="store_true")
    ap.add_argument("--html", help="write HTML report for the FIRST task here")
    args = ap.parse_args()

    cfg = RunConfig(mode=args.mode, sensitivity=args.sensitivity,
                    auto_threshold=args.auto_threshold)

    print(f"{'task':<20}{'n':>8}{'pos':>6}{'P':>7}{'R':>7}{'F1':>7}"
          f"{'sec':>8}{'ln/s':>9}")
    print("-" * 72)
    f1s = []
    first = None
    for t in args.tasks:
        out = evaluate(t, cfg)
        m = out["metrics"]
        if first is None:
            first = out["result"]
        f1s.append(m["f1"])
        print(f"{m['task'][:19]:<20}{m['n']:>8,}{m['positives']:>6}"
              f"{m['precision']:>7.3f}{m['recall']:>7.3f}{m['f1']:>7.3f}"
              f"{m['seconds']:>8}{m['lines_per_s']:>9,}")
    print("-" * 72)
    print(f"mean F1: {np.mean(f1s):.3f}")

    if args.html and first is not None:
        from loglens.output.report import write_report
        write_report(first, args.html, title=f"LogLens — {args.tasks[0]}")
        print(f"HTML report -> {args.html}")


if __name__ == "__main__":
    main()
