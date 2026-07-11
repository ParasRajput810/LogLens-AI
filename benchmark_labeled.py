

import argparse, time
from pathlib import Path

from loglens.pipeline.parser import StreamParser
from loglens.pipeline.run import run, RunConfig

try:
    from eval_harness import threshold_sweep
except Exception:
    threshold_sweep = None


def labels_for(lines):
    y = []
    for ln in lines:
        tok = ln.split(" ", 1)[0] if ln.strip() else "-"
        y.append(0 if tok == "-" else 1)
    return y


def bench_one(path, mode, limit, sensitivity, threshold, sweep, recall_floor):
    raw = Path(path).read_text(errors="ignore").splitlines()
    if limit:
        raw = raw[:limit]
    y_true = labels_for(raw)
    n_alert = sum(y_true)
    all_normal = (n_alert == 0)

    print("\n" + "#" * 56)
    print(f"# {path}")
    print(f"# {len(raw):,} lines | {n_alert:,} alerts "
          f"({100*n_alert/max(len(raw),1):.2f}%)"
          + ("  [ALL-NORMAL -> FP-rate mode]" if all_normal else ""))
    print("#" * 56)

    entries = list(StreamParser().parse_all(raw))
    t0 = time.time()
    result = run(entries, RunConfig(mode=mode, template_level=True,
                                    sensitivity=sensitivity,
                                    threshold=threshold))
    dt = time.time() - t0
    print(f"Detection in {dt:.1f}s ({len(entries)/max(dt,1e-9):,.0f} l/s)")

    n = min(len(result.flagged), len(y_true))
    y_true = y_true[:n]
    scores = result.scores[:n]

    if sweep and threshold_sweep is not None and not all_normal:
        print("\n--- threshold sweep " + "-" * 24)
        out = threshold_sweep(scores, y_true, recall_floor=recall_floor)
        th = out["best_recall_floor"][0]
        print(f"(best @ recall>={recall_floor}: threshold {th:.4f})")
        print("-" * 44)

    y_pred = [1 if bool(result.flagged[i]) else 0 for i in range(n)]
    tp = sum(1 for i in range(n) if y_true[i] == 1 and y_pred[i] == 1)
    fp = sum(1 for i in range(n) if y_true[i] == 0 and y_pred[i] == 1)
    fn = sum(1 for i in range(n) if y_true[i] == 1 and y_pred[i] == 0)
    tn = n - tp - fp - fn

    used_th = threshold if threshold is not None else f"{sensitivity} preset"
    print("=" * 44)
    if all_normal:
        rate = 100 * fp / max(n, 1)
        print(f"  FP-rate mode [th={used_th}]")
        print(f"  Lines: {n:,} | False flags: {fp:,} ({rate:.2f}%)")
    else:
        p = tp / max(tp + fp, 1)
        r = tp / max(tp + fn, 1)
        f1 = 2 * p * r / max(p + r, 1e-9)
        print(f"  [{mode}/th={used_th}]")
        print(f"  Flagged: {tp+fp:,}")
        print(f"  Precision {p:.3f} | Recall {r:.3f} | F1 {f1:.3f}")
        print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print("=" * 44)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", required=True,
                    help="log file (repeatable)")
    ap.add_argument("--mode", default="fast", choices=["fast", "deep", "turbo"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sensitivity", default="normal",
                    choices=["low", "normal", "high"])
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--recall-floor", type=float, default=0.95)
    args = ap.parse_args()
    for f in args.file:
        bench_one(f, args.mode, args.limit, args.sensitivity,
                  args.threshold, args.sweep, args.recall_floor)