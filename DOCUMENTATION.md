# 📖 LogLens AI -Command Reference

Complete guide to every LogLens command, flag, and workflow.

> **Note on syntax:** `analyze` and `ask` take the log source via the `--source` option (a file path, URL, or `-` for stdin). `benchmark` and `bench` take the file as a positional argument.

---

## Table of contents

1. [Installation](#installation)
2. [Global usage](#global-usage)
3. [`version`](#version)
4. [`hello`](#hello)
5. [`analyze`](#analyze) -the main command
6. [`ask`](#ask) -natural-language Q&A
7. [`benchmark`](#benchmark) -labeled accuracy evaluation
8. [`bench`](#bench) -speed / memory profiling
9. [AI (LLM) configuration](#ai-llm-configuration)
10. [Common workflows](#common-workflows)
11. [Exit codes](#exit-codes)

---

## Installation

```bash
pip install loglens

# for deep (neural) mode
pip install sentence-transformers
```

Verify:

```bash
loglens version
```

---

## Global usage

```bash
loglens [COMMAND] [OPTIONS]
loglens --help
loglens [COMMAND] --help
```

Available commands: `version`, `hello`, `analyze`, `ask`, `benchmark`, `bench`.

---

## `version`

Print the installed LogLens version.

```bash
loglens version
```

---

## `hello`

Health-check command that confirms LogLens is installed and runnable.

```bash
loglens hello
```

---

## `analyze`

The primary command. Ingests a log source, detects anomalies, groups them into families, and optionally runs AI root-cause analysis and generates an HTML report.

```bash
loglens analyze --source <PATH|URL|-> [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--source` | string | *(required)* | Log source: file path, URL, or `-` for stdin. |
| `--dry-run` | flag | off | Stop after ingestion; show stats only (no detection). |
| `--verbose` | flag | off | Show a sample parsed entry (field breakdown). |
| `--workers` | int | 4 | Number of parallel workers. |
| `--deep` | flag | off | Use neural (transformer) embeddings -most accurate, slower. Requires `sentence-transformers`. |
| `--turbo` | flag | off | Fast multiprocess scan for huge files (byte-range + template dedup, skips embeddings). |
| `--limit` | int | 20 | Max anomaly **families** to display. |
| `--sort-by` | string | `severity` | Sort anomalies by `severity`, `time`, or `service`. |
| `--explain` | int | 0 | Show top-N scored entries (flagged or not) with score + reasons -for debugging near-misses. |
| `--rca` | flag | off | Run AI root-cause analysis on detected anomalies (requires an LLM key). |
| `--provider` | string | env | LLM provider: `openai`, `azure`, or `groq`. |
| `--llm-model` | string | env | LLM model name / Azure deployment name. |
| `--api-key` | string | env | LLM API key (prefer the environment variable). |
| `--rca-out` | string | -| Save the RCA narrative to a markdown file (e.g. `rca.md`). |
| `--html` | string | -| Save a standalone offline HTML report (e.g. `report.html`). Includes RCA if `--rca` is set. |

### Modes

- **fast** (default): from-scratch TF-IDF statistical detector.
- **turbo** (`--turbo`): same accuracy, optimized throughput. Best for large files.
- **deep** (`--deep`): transformer semantic embeddings, best precision.

> `--turbo` and `--deep` are mutually meaningful -pick one. If neither is set, fast mode runs.

### Examples

```bash
# Basic -fast mode, format auto-detected
loglens analyze --source app.log

# Huge file, maximum speed
loglens analyze --source /var/log/prod.log --turbo --workers 8

# Best precision (neural)
loglens analyze --source app.log --deep

# Show only the top 5 families, sorted by service
loglens analyze --source app.log --limit 5 --sort-by service

# Debug why something almost got flagged
loglens analyze --source app.log --explain 15

# Read from stdin
cat app.log | loglens analyze --source -

# Just count/ingest, no detection
loglens analyze --source app.log --dry-run

# Full incident workflow: scan + AI root-cause + HTML dashboard
loglens analyze --source app.log --turbo --rca --html incident_report.html

# Save both the RCA markdown and the HTML report
loglens analyze --source app.log --rca --rca-out rca.md --html report.html
```

### Output

- **Anomaly families** panel: each unique incident with an `×N` occurrence count and a max score.
- **Category breakdown tree**: counts per severity level.
- **INCIDENT flag**: shown when ≥30% of entries are severe.
- **HTML report** (`--html`): dark-themed dashboard with severity breakdown, per-service breakdown, and score distribution -fully offline (no internet required).

---

## `ask`

Ask a free-form question about a log file. LogLens detects anomalies locally, then sends only grouped anomaly summaries to the LLM to answer your question.

```bash
loglens ask "<QUESTION>" --source <PATH> [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `QUESTION` | string | *(required, positional)* | The question, e.g. `"why did db-service degrade?"` |
| `--source` | string | *(required)* | Log file path. |
| `--deep` | flag | off | Use neural embeddings for detection. |
| `--provider` | string | env | LLM provider: `openai`, `azure`, or `groq`. |
| `--llm-model` | string | env | LLM model / Azure deployment name. |
| `--api-key` | string | env | LLM API key. |

### Examples

```bash
loglens ask "why did the payment service start timing out?" --source app.log

loglens ask "what is the root cause of the outage?" --source prod.log --deep

loglens ask "which service failed first?" --source app.log --provider groq
```

> Requires an LLM key (see [AI configuration](#ai-llm-configuration)). Detection stays 100% local; only anomaly summaries are sent.

---

## `benchmark`

Evaluate detection **accuracy** against a labeled dataset (precision / recall / F1). Use this to validate the detector against ground-truth data like Loghub.

```bash
loglens benchmark <DATASET> [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `DATASET` | string | *(required, positional)* | Path to labeled log file. |
| `--format` | string | `bgl` | Label format: `bgl`, `jsonl`, or `labeled`. |
| `--limit` | int | all | Max lines to load. |
| `--grid` | flag | off | Grid-search `feature_weight × threshold` for the best F1. |
| `--supervised` | flag | off | Train + evaluate a logistic-regression head. |
| `--min-f1` | float | -| Fail (exit 1) if baseline F1 falls below this -useful in CI. |

### Examples

```bash
# Basic accuracy on a BGL-labeled file
loglens benchmark data/bgl/BGL.log --limit 500000

# Grid-search the best hyperparameters
loglens benchmark data/bgl/BGL.log --grid

# Compare against a supervised head
loglens benchmark data/bgl/BGL.log --supervised

# CI gate: fail the build if F1 drops below 0.90
loglens benchmark data/bgl/BGL.log --min-f1 0.90
```

### Output

A table with Precision / Recall / F1 for the rule+embeddings baseline (and the supervised head if requested), plus grid-search best params when `--grid` is used.

---

## `bench`

Profile **speed and memory** across modes -the "insight in seconds on one box" story.

```bash
loglens bench <SOURCE> [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `SOURCE` | string | *(required, positional)* | Log file to benchmark. |
| `--modes` | string | `fast,turbo` | Comma-separated modes: `fast`, `deep`, `turbo`. |
| `--workers` | int | 4 | Number of parallel workers. |
| `--out` | string | -| Write markdown results to this file. |

### Examples

```bash
# Compare fast vs turbo
loglens bench app.log --modes fast,turbo

# All three modes, save a markdown table for the README
loglens bench app.log --modes fast,deep,turbo --out BENCHMARK.md

# High core count
loglens bench huge.log --modes turbo --workers 16
```

### Output

A table with: Mode, Lines, Time (s), Lines/s, Anomalies, Peak RAM (MB). With `--out`, the same table is written as markdown.

---

## AI (LLM) configuration

The `--rca` flag and the `ask` command require an LLM. LogLens supports **OpenAI**, **Azure OpenAI**, and **Groq**. Configure via environment variables (recommended) or flags.

### Environment variables

```bash
export LOGLENS_LLM_PROVIDER=openai      # openai | azure | groq
export LOGLENS_LLM_API_KEY=sk-...
export LOGLENS_LLM_MODEL=gpt-4o-mini    # or Azure deployment name
```

### Or via flags

```bash
loglens analyze --source app.log --rca \
  --provider openai --llm-model gpt-4o-mini --api-key sk-...
```

### Privacy

Only **grouped anomaly summaries** (representative line + `×N` count + score) are sent to the LLM -never your full log file. Detection itself runs entirely locally.

---

## Common workflows

**1. Triage a production incident fast**

```bash
loglens analyze --source /var/log/prod.log --turbo --rca --html incident.html
```
Scan the whole file in seconds, get grouped families, an AI root-cause narrative, and a shareable offline dashboard.

**2. Investigate a specific service**

```bash
loglens ask "why is db-service slow?" --source prod.log --deep
```

**3. Regression-gate in CI**

```bash
loglens benchmark data/labeled.log --format jsonl --min-f1 0.90
```

**4. Publish performance numbers**

```bash
loglens bench sample.log --modes fast,turbo,deep --out BENCHMARK.md
```

**5. Debug a near-miss (why wasn't X flagged?)**

```bash
loglens analyze --source app.log --explain 20
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | Failure -no valid entries, missing deep-mode dependency, LLM/RCA error, or benchmark F1 below `--min-f1`. |

---

*For architecture and reproducible accuracy details, see [README.md](README.md) and [BENCHMARK.md](BENCHMARK.md).*