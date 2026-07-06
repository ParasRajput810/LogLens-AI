# LogLens AI

Intelligent log analysis and anomaly detection from the command line.
Point it at a log file (or URL, or stdin) and it parses, embeds, and scores
every entry with a multi-signal anomaly detector - then shows you *what* is
wrong, *how often*, and *why*. No SaaS, no data leaving your machine.

```bash
loglens analyze --source app.log
```

**Benchmarked on the public LogHub BGL dataset: F1 0.94** (supervised head).
Reproduce it yourself in two commands - see [Accuracy](#accuracy).

---

## Installation

```bash
# from the project root
pip install -e .

# optional: neural embeddings for --deep mode
pip install sentence-transformers
```

Requires Python 3.10+.

---

## Quickstart

```bash
# analyze a log file
loglens analyze --source tests/fixtures/demo_incident.log

# neural embeddings (better on large, varied real-world logs)
loglens analyze --source app.log --deep

# huge file? turbo mode: parallel byte-range scan + template dedup
loglens analyze --source huge.log --turbo --workers 8

# read from a URL or stdin
loglens analyze --source https://example.com/app.log
cat app.log | loglens analyze --source stdin
```

---

## Commands

### `loglens analyze`

Parse a log source, embed every entry, run multi-signal anomaly detection,
and print ranked anomalies with reasons.

| Flag | Default | Meaning |
|---|---|---|
| `--source TEXT` | *(required)* | File path, URL, or `stdin` |
| `--deep` | off | Neural embeddings (sentence-transformers). Slower, more accurate on varied natural-language logs |
| `--turbo` | off | Fast multiprocess scan for huge files (byte-range split + template dedup, skips embeddings) |
| `--workers INT` | `4` | Number of parallel workers |
| `--limit INT` | `20` | Max anomalies to display |
| `--sort-by TEXT` | `severity` | Sort anomalies by `severity` \| `time` \| `service` |
| `--dry-run` | off | Stop after ingestion; just show line count and detected format |
| `--verbose` | off | Show a sample parsed entry |

### `loglens benchmark`

Evaluate detection accuracy against a labeled dataset (precision / recall / F1).

| Flag | Default | Meaning |
|---|---|---|
| `DATASET` | *(required)* | Path to a labeled log file (positional argument) |
| `--format TEXT` | `bgl` | Label format: `bgl` \| `jsonl` \| `labeled` |
| `--limit INT` | all | Max lines to load |
| `--grid` | off | Grid-search `feature_weight × threshold` |
| `--supervised` | off | Train + evaluate a supervised (RandomForest) head |
| `--min-f1 FLOAT` | - | Exit non-zero if baseline F1 falls below this (useful in CI) |

### `loglens version`

Print the installed version.

### `loglens hello`

Smoke test - confirms the CLI is installed and working.

---

## Accuracy

LogLens is benchmarked against the public
[LogHub](https://github.com/logpai/loghub) **BGL** dataset (Blue Gene/L
supercomputer logs with ground-truth anomaly labels). Reproduce the numbers
yourself - the dataset is fetched on demand, nothing is vendored into the repo:

```bash
bash scripts/fetch_benchmark.sh
loglens benchmark benchmarks/BGL_2k.log --format bgl --grid --supervised
```

| Method | Precision | Recall | F1 |
|---|---|---|---|
| Unsupervised (multi-signal detector) | high | high | strong |
| **Supervised head (RandomForest)** | - | - | **0.94** |

Use `--min-f1 0.90` to turn the benchmark into a regression gate in CI.

---

## How anomaly detection works

Every entry gets an **anomaly score (0–1)** summed from independent signals.
Score ≥ threshold ⇒ anomaly. Each signal covers a different failure regime,
so detection works whether anomalies are **rare, common, bursty, or dominating
the file**:

| Signal | Catches | Example reason shown |
|---|---|---|
| Hard severity | catastrophic levels, always | `FATAL level is always flagged` |
| Severity base | ERROR/CRITICAL carry weight by default | `severity CRITICAL` |
| Recurring severe | **common** anomalies - severe templates repeating at scale | `recurring ERROR pattern (70x)` |
| Failure semantics | severe level + failure vocabulary (timeout, exhausted, refused…) | `failure keyword in severe entry` |
| Rarity | templates rare for their level (thresholds scale with volume) | `template seen only 1x` |
| Semantic outlier | small groups far from their level's centroid | `semantic outlier within ERROR level` |
| Rate burst | spikes ≥4× the per-minute baseline in a 60s window | `rate burst (> 4x baseline in 60s window)` |
| Flood | one severe template ≥20% of the whole file, scaled by share | `flood: pattern is 34% of the whole file` |
| Catastrophe keywords | kernel panic, data loss, corruption, split-brain… | `catastrophic keyword` |
| Baseline novelty | templates never seen / surging >10× vs a baseline | `never seen in baseline` |

The design principle: **the level is evidence, not a verdict.** An
`ERROR user login successful` line won't be flagged just because someone
logged a success at ERROR level - and a burst of WARNs *can* be flagged even
though single WARNs are routine.

DBSCAN `eps` and the score threshold are **auto-tuned** (k-distance elbow +
Otsu), so there are no knobs to fiddle with for the common case.

---

## Reading the output

```
[LogLens] Detected format: STANDARD
[LogLens] Lines ingested: 12,043
[LogLens] Mode: Fast (TF-IDF embeddings)
[LogLens] Clusters found: 6
[LogLens] Anomalies detected: 167 🚨 ⚠ INCIDENT
          ├── FATAL      : 1
          ├── CRITICAL   : 12
          ├── ERROR      : 141
          └── WARN       : 13

╭─────────────── ANOMALIES DETECTED (167 total) ───────────────╮
│ [FATAL] db-service - database master unreachable split-brain… │
│ [ERROR] payment-service - payment gateway timeout after 27s…  │
╰───────────────────────────────────────────────────────────────╯
```

* **INCIDENT banner** - appears when ≥30% of the file is ERROR-or-worse. Treat
  the ranking as your triage order.
* **Level breakdown tree** - how many anomalies fell into each severity.
* Programmatic access: after detection every entry carries
  `entry.anomaly_score` and `entry.anomaly_reasons`.

---

## Fast vs deep vs turbo

| | Fast (default) | `--deep` | `--turbo` |
|---|---|---|---|
| Embeddings | TF-IDF + engineered log features | MiniLM sentence embeddings + log features | none (template dedup only) |
| Speed | thousands of lines/sec | slower, batch-encoded | fastest, multiprocess |
| Needs | nothing extra | `pip install sentence-transformers` | nothing extra |
| Best for | most logs, repetitive templates | large logs with varied natural-language text | huge files where you want a fast triage scan |

Fast and deep feed the **same detector** - severity, recurrence, bursts and
floods behave identically; deep mode mainly improves rarity/outlier judgment on
messy real-world text.

---

## Supported log formats

Format is auto-detected per line (with sticky detection + multiline stack-trace
stitching, so Java/Python tracebacks stay attached to their parent entry). No
flags needed - just point LogLens at the file.

### Cloud providers (structured JSON)

Cloud JSON is detected by its shape and mapped to a normalized entry (severity,
service, message + provider metadata like region / project / resource):

| Provider | Detected from | Extracted fields |
|---|---|---|
| **AWS** (CloudTrail) | `eventSource` / `eventName` + `awsRegion` | `eventName`, `errorCode`, `awsRegion`, `sourceIPAddress`, `userIdentity.arn` |
| **GCP** (Cloud Logging) | `logName` / `protoPayload` / `jsonPayload` / `resource.severity` | `severity`, `resource.type`, `textPayload`, `logName`, `project_id` |
| **Azure** (Monitor / Activity) | `resourceId` + `operationName` / `category` | `level`, `category`, `operationName`, `resultType`, `properties.status` |

### Application & infrastructure

| Format | Example |
|---|---|
| STANDARD | `2024-03-10T14:00:00Z ERROR [api-gateway] connection reset` |
| SYSLOG (incl. `<PRI>` + `facility.severity`) | `Mar 10 14:00:00 host sshd: Failed password for root` |
| NGINX / APACHE access | `1.2.3.4 - - [10/Mar/2024:14:00:00 +0000] "GET / HTTP/1.1" 502 0` |
| APACHE error | `[Wed Mar 10 14:00:00 2024] [error] client denied` |
| APP_LOG (Log4j / logback) | `2024-03-10 14:00:00,123 ERROR [main] service: message` |
| JSON lines (generic) | `{"time": "...", "level": "error", "msg": "..."}` |
| LOGLENS | internal format |

### Big-data & system logs (LogHub-style)

| Format | Source |
|---|---|
| HDFS | Hadoop Distributed File System |
| ZK_LOG | ZooKeeper |
| SPARK_LOG | Apache Spark |
| BGL / HPC | Blue Gene/L & HPC supercomputer logs |
| WINCBS | Windows CBS (Component-Based Servicing) |
| HEALTHAPP | HealthApp mobile logs |
| PROXIFIER | Proxifier network logs |

Anything that doesn't match a known pattern falls back to **PLAINTEXT** - the
message is still kept and its level is inferred from keywords (`ERROR`, `FATAL`,
`timeout`, `panic`, …), so no line is ever dropped. HTTP access logs also get an
inferred level from status code (5xx → ERROR, 503/504 → CRITICAL, 4xx → WARN).

---

## Try it

The repo ships a demo file that contains every regime - healthy INFO
background, benign WARNs, recurring CRITICAL/ERROR, a one-minute ERROR burst,
rare FATAL/EMERGENCY events, and a semantic outlier:

```bash
loglens analyze --source tests/fixtures/demo_incident.log
```

---

## Project layout

```
src/loglens/
├── cli.py                    # typer CLI (analyze / benchmark / version / hello)
├── models.py                 # LogEntry dataclass
├── output/
│   └── terminal.py           # rich progress rendering
└── pipeline/
    ├── ingestion/            # async line streaming (file / URL / stdin)
    ├── parser.py             # format detection + parsing
    ├── synonyms.py           # message normalization + synonym learning
    ├── embeddings.py         # fast TF-IDF + log-feature embeddings
    ├── deep_embeddings.py    # neural embeddings (--deep)
    ├── templates.py          # template masking + registry (grouping)
    ├── detector.py           # multi-signal anomaly detection
    ├── benchmark.py          # labeled-dataset evaluation (P/R/F1)
    ├── turbo.py              # parallel byte-range scan (--turbo)
    └── worker.py             # async worker pool
scripts/
└── fetch_benchmark.sh        # download the LogHub BGL sample on demand
```

---

## Running tests

```bash
pip install -e ".[dev]"
pytest
```