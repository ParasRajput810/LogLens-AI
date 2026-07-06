# LogLens AI

Intelligent log analysis and anomaly detection from the command line.
Point it at a log file (or URL, or stdin) and it parses, embeds, and scores
every entry with a multi-signal anomaly detector - then shows you *what* is
wrong, *how often*, and *why*.

```
loglens analyze --source app.log
```

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

# more sensitive (also flags recurring failing WARNs)
loglens analyze --source app.log --sensitivity high

# neural embeddings (better on large, varied real-world logs)
loglens analyze --source app.log --deep

# read from a URL or stdin
loglens analyze --source https://example.com/app.log
cat app.log | loglens analyze --source stdin
```

---

## Commands

### `loglens analyze`

Parse a log source, embed every entry, run multi-signal anomaly
detection, and print ranked anomaly groups with reasons.

| Flag | Default | Meaning |
|---|---|---|
| `--source TEXT` | *(required)* | File path, URL, or `stdin` |
| `--deep` | off | Neural embeddings (sentence-transformers). Slower, more accurate on varied logs |
| `--sensitivity TEXT` | `normal` | `low` \| `normal` \| `high`. Moves the score threshold (0.80 / 0.70 / 0.60). `high` also catches recurring failing WARNs |
| `--threshold FLOAT` | auto | Override the anomaly score threshold directly (0–1) |
| `--eps FLOAT` | auto-tuned | DBSCAN neighborhood radius. Only set this if you know why |
| `--min-samples INT` | `4` | DBSCAN min_samples |
| `--limit INT` | `20` | Max anomaly *groups* to display |
| `--no-burst` | off | Disable rate-burst detection (for logs without meaningful timestamps) |
| `--workers INT` | `4` | Parallel processing workers |
| `--dry-run` | off | Stop after ingestion; just show line counts and detected format |
| `--verbose` | off | Show detector internals (eps, unique templates, severe share) and a sample parsed entry |

### `loglens version`

Print the installed version.

### `loglens hello`

Smoke test - confirms the CLI is installed and working.

---

## How anomaly detection works

Every entry gets an **anomaly score (0–1)** summed from independent
signals. Score ≥ threshold ⇒ anomaly. Each signal covers a different
failure regime, so detection works whether anomalies are **rare, common,
bursty, or dominating the file**:

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

### The severity ladder

| Level | Base score | What flags it |
|---|---|---|
| EMERGENCY / PANIC / ALERT / FATAL | 1.00 | Always flagged, unconditionally |
| CRITICAL | 0.55 | Any single corroboration (recurring, keyword, rare, burst) |
| ERROR | 0.35 | Two corroborations (e.g. recurring + failure keyword) |
| WARN | 0.22 | Strong evidence at `normal` (burst, flood, rare + keyword); recurring failures at `--sensitivity high` |
| INFO / DEBUG | 0.00 | Only if genuinely rare/novel, and dampened |

The design principle: **the level is evidence, not a verdict.** An
`ERROR user login successful` line will not be flagged just because
someone logged a success at ERROR level - and a burst of WARNs can be
flagged even though single WARNs are routine.

---

## Reading the output

```
[LogLens] Clusters found: 6
[LogLens] Anomalies detected: 167 in 8 groups 🚨

╭─────────────── ANOMALIES - 167 entries in 8 groups ───────────────╮
│ [FATAL] x1 db-service - database master unreachable split-brain…  │
│     why: FATAL level is always flagged                            │
│ [ERROR] x70 payment-service - payment gateway timeout after 27s…  │
│     why: severity ERROR; recurring ERROR pattern (70x); failure…  │
╰────────────────────────────────────────────────────────────────────╯

 Recurring severe patterns (below flag threshold)
┌───────┬───────┬───────┬──────────────────────────────┬─────────────┐
│ WARN  │    80 │  9.9% │ token refresh failed uid=…   │ auth-service│
└───────┴───────┴───────┴──────────────────────────────┴─────────────┘
```

* **Anomaly groups** - one row per pattern, not per line. `x70` means
  70 log entries share that template. Groups are ranked by score, then
  count. The `why:` line lists the signals that fired.
* **Recurring severe patterns** - chronic severe templates that stayed
  *below* the threshold. Never silent: even when something isn't flagged,
  you can see it's happening.
* **INCIDENT MODE banner** - appears when ≥30% of the file is ERROR-or-
  worse. The whole file is an incident window; treat the ranking as your
  triage order.
* Programmatic access: after detection every entry carries
  `entry.anomaly_score` and `entry.anomaly_reasons`.

---

## Tuning

```bash
# quieter: only high-confidence anomalies (threshold 0.80)
loglens analyze --source app.log --sensitivity low

# louder: recurring failing WARNs included (threshold 0.60)
loglens analyze --source app.log --sensitivity high

# exact control
loglens analyze --source app.log --threshold 0.55

# show every group, not just the top 20
loglens analyze --source app.log --limit 1000

# timestamps are fake/missing? skip burst detection
loglens analyze --source app.log --no-burst
```

Rule of thumb: `normal` for ERROR-and-worse triage, `high` when WARNs
matter, `low` for noisy production logs where you only want to be paged
for the real thing.

---

## Supported log formats

Format is auto-detected from the first line:

| Format | Example |
|---|---|
| STANDARD | `2024-03-10T14:00:00Z ERROR [api-gateway] connection reset` |
| SYSLOG | `Mar 10 14:00:00 host sshd: Failed password for root` |
| NGINX / APACHE access | `1.2.3.4 - - [10/Mar/2024:14:00:00 +0000] "GET / HTTP/1.1" 502 0` |
| JSON lines | `{"time": "...", "level": "error", "msg": "..."}` |
| LOGLENS | internal format |

---

## Fast vs deep mode

| | Fast (default) | `--deep` |
|---|---|---|
| Embeddings | TF-IDF + engineered log features | MiniLM sentence embeddings + log features |
| Speed | thousands of lines/sec | slower, batch-encoded |
| Needs | nothing extra | `pip install sentence-transformers` (first run downloads the model) |
| Best for | most logs, repetitive templates | large logs with varied natural-language messages |

Both modes feed the **same detector** - severity, recurrence, bursts and
floods behave identically; deep mode mainly improves rarity/outlier
judgment on messy real-world text.

---

## Try it

The repo ships a demo file that contains every regime - healthy INFO
background, benign WARNs, recurring CRITICAL/ERROR, a one-minute ERROR
burst, rare FATAL/EMERGENCY events, and a semantic outlier:

```bash
loglens analyze --source tests/fixtures/demo_incident.log
loglens analyze --source tests/fixtures/demo_incident.log --sensitivity high
```

At `normal` you should see 167 anomalies in 8 groups spanning EMERGENCY,
FATAL, CRITICAL and ERROR; at `high`, the recurring `token refresh failed`
WARN joins as a 9th group - while the benign `disk usage 55%` WARN stays
quiet at every sensitivity.

---

## Project layout

```
src/loglens/
├── cli.py                    # typer CLI (analyze / version / hello)
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
    └── worker.py             # async worker pool
```

## Running tests

```bash
pip install pytest pytest-asyncio
pytest
```