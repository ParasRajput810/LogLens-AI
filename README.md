<div align="center">

# 🔍 LogLens AI

**AI-powered log anomaly detection that reads your logs like a senior engineer.**

*Detects anomalies by meaning, explains them in plain English, groups them into incidents, watches your services live, alerts you Sentry-style - and runs 100% local: zero setup, zero cloud, $0/GB.*

`pip install loglens` → first insight in seconds.

</div>

---

## Why LogLens AI stands out

Most log platforms give you a score and a bill. LogLens AI gives you **published, reproducible accuracy** - something no major platform does - plus **explainable, grouped incidents**, **live watching**, **self-alerting for your own apps**, and an **optional AI root-cause layer**.

|  | **LogLens AI** | Splunk | Datadog | Elastic ML | DeepLog (research) |
|---|---|---|---|---|---|
| Setup time | **seconds** | days–weeks | hours–days | hours | N/A (paper) |
| Cost | **$0/GB** | ~$150/GB/yr | ~$0.10–1.27/GB | license | free |
| Runs offline / air-gapped | ✅ | partial | ❌ | partial | ✅ |
| Published, reproducible accuracy | ✅ **F1 0.957** | ❌ | ❌ | ❌ | ✅ (HDFS only) |
| Explains *why* a line is anomalous | ✅ | scores only | scores only | scores only | ❌ |
| Groups repeats into incident families | ✅ | partial | partial | ❌ | ❌ |
| Live watch (docker / k8s / journald) | ✅ | ✅ | ✅ | partial | ❌ |
| Self-alerting for your own app (1 line) | ✅ | ❌ | agent | ❌ | ❌ |
| AI root-cause narratives (BYO key) | ✅ | paid add-on | paid | ❌ | ❌ |
| Self-contained offline HTML report | ✅ | ❌ | ❌ | ❌ | ❌ |

> **The one-liner:** *The only log anomaly detector with published, reproducible F1 - free, local, explained, grouped into incidents, and able to watch and alert on your services in real time.*

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
- **Deep (AI) mode measurably beats the baseline** - semantic embeddings cut false positives by ~18%. Provable AI value, not marketing.
- **Turbo matches fast-mode accuracy exactly** at higher throughput - speed with no accuracy tradeoff.

### Speed benchmark - `loglens bench`

Measured with the built-in `bench` command (`demo_incident.log`, 810 entries):

| Mode | Lines | Time (s) | Lines/s | Anomaly families | Peak RAM |
|------|-------|----------|---------|------------------|----------|
| **⚡ turbo** | 810 | 0.054 | **14,999** | **8** | 169 MB |
| **🟢 fast** | 810 | 0.601 | 1,348 | (170 raw events) | 169 MB |

Turbo collapses 810 lines into **8 incident families** - the "insight in seconds on one box" story.

### Cross-dataset generality - no retuning

Threshold tuned on BGL, applied **unchanged** to the Sandia Thunderbird cluster (500,000 all-normal lines):

| Mode | False-alarm rate | Specificity | Speed |
|------|------------------|-------------|-------|
| fast | 0.68% | **99.32%** | ~8,600 l/s |
| deep | 0.67% | **99.33%** | ~1,800 l/s |

### Needle-in-a-haystack - injected incident recall

5 unique critical incidents (kernel panic, OOM, disk failure, security breach, data corruption) injected into routine logs across 6 formats:

| Format | Caught | Format | Caught |
|---|---|---|---|
| Apache | 5/5 | HealthApp | 5/5 |
| Spark | 5/5 | OpenStack | 5/5 |
| HDFS | 5/5 | Thunderbird | 5/5 |

**30/30 injected incidents detected - 100% recall across every format, zero configuration.**

---

## ✨ Features

### Detection core
- 🧠 **Three detection engines, one unified scoring model**
  - `fast` - from-scratch statistical detector (TF-IDF template embeddings, weighted density clustering, severity/rarity/chronic scoring). No ML libraries in the core.
  - `turbo` - the same accuracy, optimized for throughput via parallel byte-range scanning and template dedup.
  - `deep` - transformer-based semantic embeddings that understand log *meaning*. Runs on unique templates only, so it stays fast.
- 🧩 **Anomaly families (template grouping)** - repeated anomalies are collapsed into a single incident with an `×N` count, across *all* modes. No more scrolling through 200 identical errors.
- ⚖️ **Recalibrated scoring** - graded severity priors, **chronic-pattern damping** (routine errors are suppressed), and a **global-rarity bonus** (rare severe events are boosted). Cuts false positives dramatically while keeping 1.0 recall on real incidents.
- 💬 **Explainable anomalies** - every flag comes with a plain-language reason (rare + severe + burst context), not just a score.
- 📄 **10+ log formats auto-detected** - Apache, Linux, Mac, HDFS, Spark, Zookeeper, OpenStack, Thunderbird, BGL, HealthApp and generic formats. No config, ever.
- 🔌 **Flexible ingestion** - files, stdin, HTTP.

### Live & always-on
- 👀 **`loglens watch` - live tail anomaly alerts** - point it at `docker logs -f`, `kubectl logs -f`, or `journalctl -f` and it prints **only the problems**, the instant they happen. CRITICAL/FATAL lines surface immediately; Ctrl-C prints a summary card (and, optionally, an AI root-cause story + HTML dashboard).
- 🚨 **Always-on monitoring & alerts (`loglens.init`)** - add **one line** to your app and get Sentry-style alerts in **Slack / Teams / Email** the moment something serious happens, including uncaught crashes. De-duplicated, rate-limited, sent from a background thread so it never risks your app. Works with **zero AI setup** (built-in cause hints) and gets richer with a BYO LLM key.

### AI layer (bring your own key)
- 🤖 **AI root-cause analysis (`--rca`)** - optional, BYO key (OpenAI / Azure / Groq). Sends only **grouped anomaly summaries** to the LLM - never your full log file - so it's cheap, private, and coherent.
- ❓ **Natural-language Q&A (`loglens ask`)** - ask "why did db-service degrade?" and get an answer grounded in the detected anomalies.

### Python SDK
- 🐍 **Full SDK** - everything the CLI does, callable from your code:
  - `analyze()` / `analyze_async()` - "here are logs, give me the problems."
  - `LogLensHandler` - drop into Python's `logging` so your app raises its own alarm.
  - `LiveDetector` - feed a custom stream line-by-line, get anomalies out (powers `watch`).
  - `.rca()`, `.ask(...)`, `.save_html(...)`, `.save_rca(...)` on any result or live session.

### Reporting & benchmarking
- 📈 **Self-contained HTML report (`--html`)** - a dark-themed dashboard with severity breakdown, per-service breakdown, and score distribution. Fully offline (no CDN), embeds the RCA narrative when `--rca` is used.
- ⏱️ **Speed benchmark (`loglens bench`)** - lines/sec, time-to-insight, and peak RAM across modes, exportable to markdown.
- 🧪 **Reproducible accuracy benchmark (`loglens benchmark`)** - precision / recall / F1 against labeled datasets, grid-search, supervised head, and a `--min-f1` CI gate. Don't trust us; run it yourself.
- 🔒 **100% local & private** - detection never leaves your machine; air-gap friendly.

---

## 🚀 Quick start

```bash
pip install loglens

# analyze any log file - format auto-detected
loglens analyze --source app.log

# maximum throughput on huge files
loglens analyze --source app.log --turbo

# AI semantic mode (best precision)
loglens analyze --source app.log --deep

# full incident workflow: turbo scan + AI root-cause + offline HTML report
loglens analyze --source app.log --turbo --rca --html report.html

# watch a running service live and get only the problems
loglens watch "docker logs -f my-api"

# ask a question about a log file
loglens ask "why did the payment service start timing out?" --source app.log

# benchmark speed across modes
loglens bench app.log --modes fast,turbo,deep --out BENCHMARK.md
```

**Add self-alerting to your own app in one line:**

```python
import loglens
loglens.init(app_name="checkout-api")   # → Slack / Teams / Email on serious events
```

📖 **Full command & SDK reference:** see [DOCUMENTATION.md](DOCUMENTATION.md).

---

## 🧭 How it works

1. **Parse** - streaming parser auto-detects the log format.
2. **Template** - messages are mined into templates; volume statistics per template.
3. **Embed** - templates are embedded (TF-IDF in fast/turbo, transformer in deep) - one vector per unique template for speed.
4. **Detect** - an ensemble score blends severity prior, template rarity, embedding distance, chronic damping and global-rarity bonus into a calibrated continuous score.
5. **Group** - repeated anomalies are collapsed into incident families (`×N`).
6. **Explain** - every anomaly is reported with its human-readable reason; optionally an LLM writes the root-cause narrative.
7. **Deliver** - print to terminal, stream live via `watch`, alert to Slack/Teams/Email via `init`, or export an offline HTML report.

---

## 🗺️ Roadmap

- 🔧 Chronic-noise damping improvements for Linux/Mac daemon logs.
- 📦 Prebuilt Docker image and GitHub Action.
- 📊 Additional alert channels (PagerDuty, Opsgenie, generic webhooks).
- 🌐 Optional lightweight web UI for the HTML dashboards.

---

## 📜 Honesty notes

- Accuracy measured on Loghub line-level labels (token `-` = normal).
- Deep mode embeds unique templates only - a real optimization, disclosed.
- `--rca`, `ask`, and alert cause-hints send only grouped anomaly summaries to the LLM, never the full log.
- Alerting works fully offline with built-in cause hints; an LLM key only enriches the narrative.
- All tests reproducible with the included harness. See [BENCHMARK.md](BENCHMARK.md).

## License

MIT - see [LICENSE](LICENSE).