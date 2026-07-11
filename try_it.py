import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from loglens import LiveDetector, LogLensHandler, analyze

LINES = (
    [f"2024-01-01T00:00:{i % 60:02d}Z INFO api request completed {i % 7}ms"
     for i in range(60)]
    + ["2024-01-01T00:01:00Z FATAL db disk failure raid degraded"]
    + [f"2024-01-01T00:01:{i:02d}Z ERROR db connection refused host=db-1"
       for i in range(1, 13)]
)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    mark = "\033[92mPASS\033[0m" if cond else "\033[91mFAIL\033[0m"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))


def main():
    print("\n1) analyze(file)")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "app.log"
        p.write_text("\n".join(LINES))
        r = analyze(str(p))
    check("file analyzed", r.total == len(LINES), f"{r.total} entries")
    check("FATAL + ERROR storm caught",
          {"FATAL", "ERROR"} <= {a.level for a in r.anomalies},
          f"{len(r.anomalies)} anomalies: {r.by_level()}")

    print("\n2) analyze(lines=...)")
    r = analyze(lines=LINES)
    check("in-memory lines", len(r.anomalies) >= 13, str(r.summary()))
    check("anomalies sorted by score",
          all(r.anomalies[i].score >= r.anomalies[i + 1].score
              for i in range(len(r.anomalies) - 1)))
    check("every anomaly has reasons", all(a.reasons for a in r.anomalies))

    print("\n3) analyze(cmd=...)   (a command's output as source)")
    r = analyze(cmd="printf 'INFO ok\\nERROR payment gateway timeout order=1\\n'")
    check("bounded command analyzed",
          r.total == 2 and any(a.level == "ERROR" for a in r.anomalies))

    print("\n4) LiveDetector (streaming, exactly-once)")
    det = LiveDetector(window=200, rescore_every=20, min_window=5)
    hits = []
    for ln in LINES:
        hits += det.feed(ln)
    hits += det.flush()
    lv = [h.level for h in hits]
    check("FATAL surfaced", "FATAL" in lv or "CRITICAL" in lv)
    check("whole ERROR storm reported once each", lv.count("ERROR") == 12,
          f"{lv.count('ERROR')}/12")
    check("no benign INFO spam", "INFO" not in lv)
    check("exactly-once (no duplicates)",
          len([h.index for h in hits]) == len({h.index for h in hits}))

    print("\n5) LogLensHandler (drop-in logging integration)")
    caught = []
    h = LogLensHandler(on_anomaly=caught.append, min_window=5,
                       rescore_every=10)
    lg = logging.getLogger("demo.svc")
    lg.addHandler(h)
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    for i in range(30):
        lg.info("heartbeat ok %d", i % 3)
    lg.critical("kernel panic null pointer dereference")
    h.flush()
    lg.removeHandler(h)
    check("callback fired on CRITICAL",
          len(caught) >= 1 and caught[0].level == "CRITICAL",
          f"{len(caught)} callback(s), summary={h.summary()}")

    print("\n6) loglens watch (fake live stream, stopped after the storm)")
    print("   (first output can take 10-30s on WSL /mnt/c — imports are slow there)")
    fake_stream = (
        "i=0; while true; do "
        "echo \"2024-01-01T00:00:00Z INFO api request ok $((i%7))ms\"; "
        "i=$((i+1)); "
        "if [ $i -eq 40 ]; then echo '2024-01-01T00:00:30Z FATAL db split-brain detected'; fi; "
        "if [ $i -gt 50 ] && [ $i -lt 62 ]; then "
        "echo '2024-01-01T00:00:40Z ERROR db connection refused host=db-1'; fi; "
        "sleep 0.05; done")
    import signal
    import threading
    import time

    proc = subprocess.Popen(
        [sys.executable, "-m", "loglens.cli", "watch", fake_stream, "--quiet"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        errors="replace")

    def watchdog():        # absolute last resort so the demo can't hang
        time.sleep(120)
        if proc.poll() is None:
            proc.kill()

    threading.Thread(target=watchdog, daemon=True).start()

    lines, storm = [], 0
    deadline = time.time() + 90
    for line in proc.stdout:            # wait for REAL activity, not a timer
        lines.append(line)
        if "connection refused" in line:
            storm += 1
        if storm >= 5 or time.time() > deadline:
            break
    proc.send_signal(signal.SIGINT)     # = pressing Ctrl-C
    try:
        rest, _ = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        rest, _ = proc.communicate()
    out = "".join(lines) + (rest or "")
    check("watch streamed anomalies live",
          "FATAL" in out or "CRITICAL" in out)
    check("watch caught the error storm", "connection refused" in out)
    check("Ctrl-C produced a summary", "WATCH SUMMARY" in out)
    print("\n--- watch output tail " + "-" * 30)
    print("\n".join(out.splitlines()[-8:]))
    print("-" * 52)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{'='*52}\n  {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed"
          + (f"  — FAILED: {failed}" if failed else "  🎉") + f"\n{'='*52}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()