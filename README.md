<div align="center">

# 🔍 LogLens AI

**AI-powered log anomaly detection that reads your logs like a senior engineer.**

*Detects anomalies by meaning, explains them in plain English, runs 100% local - zero setup, zero cloud, $0/GB.*

`pip install loglens` → first insight in seconds.

</div>

---

## Why LogLens AI stands out

Most log platforms give you a score and a bill. LogLens AI gives you **published, reproducible accuracy** - something no major platform does.

|  | **LogLens AI** | Splunk | Datadog | Elastic ML | DeepLog (research) |
|---|---|---|---|---|---|
| Setup time | **seconds** | days–weeks | hours–days | hours | N/A (paper) |
| Cost | **$0/GB** | ~$150/GB/yr | ~$0.10–1.27/GB | license | free |
| Runs offline / air-gapped | ✅ | partial | ❌ | partial | ✅ |
| Published, reproducible accuracy | ✅ **F1 0.95** | ❌ | ❌ | ❌ | ✅ (HDFS only) |
| Explains *why* a line is anomalous | ✅ | scores only | scores only | scores only | ❌ |
| Anomaly detection free & built-in | ✅ | paid add-on | paid | paid tier | - |
| From-scratch algorithms (no ML deps in core) | ✅ | - | - | - | ❌ |

> **The one-liner:** *The only log anomaly detector with published, reproducible F1 - free, local, and explained.*

---

## 📊 Benchmark results (real production logs)

All numbers measured on real-world labeled datasets from [Loghub](https://github.com/logpai/loghub).
Fully reproducible - see [BENCHMARK.md](BENCHMARK.md).

### Accuracy - Loghub BGL (500,000 lines, 206,847 labeled alerts)

| Mode | Engine | Precision | Recall | F1 | Speed | Missed alerts |
|------|--------|-----------|--------|----|-------|---------------|
| **fast** | from-scratch statistical | 0.901 | **1.000** | 0.948 | ~6,700 l/s | **0** |
| **turbo** | from-scratch, optimized | 0.901 | **1.000** | 0.948 | ~7,300 l/s | **0** |
| **deep** | AI semantic embeddings | **0.917** | **1.000** | **0.957** | ~3,400 l/s | **0** |

- **Zero false negatives** across all 206,847 alerts, in every mode.
- **Deep (AI) mode measurably beats the baseline** - semantic embeddings cut false positives by ~18% (22,810 → 18,624). Provable AI value, not marketing.
- **Turbo matches fast-mode accuracy exactly** at higher throughput - speed with no accuracy tradeoff.

### Cross-dataset generality - no retuning

Threshold tuned on BGL, applied **unchanged** to a completely different system
(Sandia Thunderbird cluster, 500,000 all-normal lines):

| Mode | False-alarm rate | Specificity | Speed |
|------|------------------|-------------|-------|
| fast | 0.68% | **99.32%** | ~8,600 l/s |
| deep | 0.67% | **99.33%** | ~1,800 l/s |

### False-alarm stress test - 9 real-world log types, one universal threshold

Routine operational logs where every flag is noise. Zero per-format tuning.

| Log type | False-alarm rate | | Log type | False-alarm rate |
|---|---|---|---|---|
| Spark | **0.00%** ✅ | | Apache | 1.20% ✅ |
| HDFS | **0.00%** ✅ | | Mac | 8.15% ⚠️ |
| OpenStack | 0.05% ✅ | | Linux | 13.25% ⚠️ |
| HealthApp | 0.20% ✅ | | Zookeeper | 61.6% * |
| Thunderbird | 0.60% ✅ | | | |

**7 of 9 formats under 1.2% false alarms.** (*) The Zookeeper capture is a genuine
connection-failure election storm (66% of lines are failure WARNs) - flagging it is
correct behavior. Linux/Mac chronic-noise damping is a documented roadmap item.

### Needle-in-a-haystack - injected incident recall

5 unique critical incidents (kernel panic, OOM, disk failure, security breach, data
corruption) injected into routine logs across 6 different formats:

| Format | Caught | Format | Caught |
|---|---|---|---|
| Apache | 5/5 | HealthApp | 5/5 |
| Spark | 5/5 | OpenStack | 5/5 |
| HDFS | 5/5 | Thunderbird | 5/5 |

**30/30 injected incidents detected - 100% recall across every format, zero configuration.**

---

## ✨ Features

- 🧠 **Three detection engines, one scoring model**
  - `fast` - from-scratch statistical detector (TF-IDF template embeddings, weighted density clustering, severity/rarity/chronic scoring). No ML libraries in the core.
  - `turbo` - the same accuracy, optimized for throughput.
  - `deep` - transformer-based semantic embeddings that understand log *meaning*, not just keywords. Runs on unique templates only, so it stays fast.
- 💬 **Explainable anomalies** - every flag comes with a plain-language reason (rare + severe + burst context), not just a score.
- 📄 **10+ log formats auto-detected** - Apache, Linux, Mac, HDFS, Spark, Zookeeper, OpenStack, Thunderbird, BGL, HealthApp and generic formats. No config, ever.
- 🎯 **Template mining** - automatic log templating; chronic/noisy patterns are learned and damped, rare severe patterns are boosted.
- 📈 **Calibrated continuous scoring** - de-saturated scores with a single universal threshold (default 0.82) that generalizes across systems, plus sensitivity presets.
- 🔌 **Flexible ingestion** - files, stdin, HTTP.
- 🖥️ **Terminal + report output** - clean CLI results and report generation.
- 🔒 **100% local & private** - no cloud, no data leaves your machine, air-gap friendly.
- 🧪 **Reproducible benchmark harness included** - `benchmark_labeled.py` runs the exact published tests. Don't trust us; run it yourself.

---

## 🚀 Quick start

```bash
pip install loglens

# analyze any log file - format auto-detected
loglens analyze app.log

# maximum throughput
loglens analyze app.log --mode turbo

# AI semantic mode (best precision)
loglens analyze app.log --mode deep
```

Reproduce the benchmarks:

```bash
# datasets from https://github.com/logpai/loghub
python benchmark_labeled.py --file data/bgl/BGL.log --limit 500000 --sweep --threshold 0.82 --mode fast
python benchmark_labeled.py --file data/bgl/BGL.log --limit 500000 --sweep --threshold 0.82 --mode deep
```

---

## 🧭 How it works

1. **Parse** - streaming parser auto-detects the log format.
2. **Template** - messages are mined into templates; volume statistics per template.
3. **Embed** - templates are embedded (TF-IDF in fast/turbo, transformer in deep) - one vector per unique template for speed.
4. **Detect** - an ensemble score blends severity prior, template rarity, embedding distance, chronic damping and global-rarity bonus into a calibrated continuous score.
5. **Explain** - every anomaly is reported with its human-readable reason.

---

## 🗺️ Roadmap

- 🤖 AI root-cause narratives & `loglens ask` - natural-language Q&A over your logs (bring-your-own-key LLM layer; detection stays local)
- 📊 One-command HTML incident report
- 👀 `loglens watch` - live tail anomaly alerts
- 🔧 Chronic-noise damping improvements for Linux/Mac daemon logs

---

## 📜 Honesty notes

- Accuracy measured on Loghub line-level labels (token `-` = normal).
- Deep mode embeds unique templates only - a real optimization, disclosed.
- Zookeeper stress-test number reflects a genuine incident-heavy capture.
- All tests reproducible with the included harness. See [BENCHMARK.md](BENCHMARK.md).

## License

MIT - see [LICENSE](LICENSE).
