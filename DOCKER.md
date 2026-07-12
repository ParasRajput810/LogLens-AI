# LogLens AI 🔍

**AI-powered log anomaly detection that reads your logs like a senior engineer.**
Detects anomalies by *meaning*, explains them in plain English, groups them into
incidents, watches services live, and alerts you Sentry-style - 100% local, $0/GB.

- 🌐 Website: https://loglensai.com
- 📦 PyPI: https://pypi.org/project/loglensai/
- 📖 Docs: https://loglensai.com/docs

---

## Tags

| Tag | What's inside | Size |
|-----|---------------|------|
| `latest`, `0.3`, `0.3.1` | fast + turbo detection, watch, alerts, SDK, ask/RCA, HTML reports | ~slim |
| `deep` | everything above **plus** neural (transformer) mode | large (torch) |

Images are multi-arch: `linux/amd64` and `linux/arm64`.

---

## Quick start

Analyze a log file (mount the folder that contains it at `/data`):

```bash
docker run --rm -v "$PWD:/data" loglensai/loglens analyze --source app.log
```

Turbo scan + AI root-cause + offline HTML report:

```bash
docker run --rm -v "$PWD:/data" \
  -e LOGLENS_LLM_PROVIDER=openai -e LOGLENS_LLM_API_KEY=sk-... \
  loglensai/loglens analyze --source app.log --turbo --rca --html report.html
```

Ask a question about a log file:

```bash
docker run --rm -v "$PWD:/data" \
  -e LOGLENS_LLM_PROVIDER=openai -e LOGLENS_LLM_API_KEY=sk-... \
  loglensai/loglens ask "why did the payment service start timing out?" --source app.log
```

Anything after the image name is passed straight to the `loglens` CLI, so
`--help` lists everything:

```bash
docker run --rm loglensai/loglens --help
```

---

## Live watch (docker / kubernetes / journald)

Watch another container's logs and get **only the problems**, live. This needs
the host Docker socket:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  loglensai/loglens watch "docker logs -f my-api" --rca
```

Press Ctrl-C for a summary card (and an AI root-cause story if `--rca` is set).

---

## Always-on alerts (Slack / Teams / Email)

Pass your channel settings as environment variables and LogLens will alert the
moment something serious happens:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -e LOGLENS_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ \
  loglensai/loglens watch "docker logs -f my-api" --rca
```

Supported channel variables:

```
LOGLENS_SLACK_WEBHOOK
LOGLENS_TEAMS_WEBHOOK
LOGLENS_EMAIL_SMTP_HOST / _SMTP_PORT / _USER / _PASSWORD / _TO
```

LLM (optional, enriches root-cause):

```
LOGLENS_LLM_PROVIDER   openai | azure | groq
LOGLENS_LLM_MODEL
LOGLENS_LLM_API_KEY
```

---

## Neural (deep) mode

The `deep` tag adds transformer embeddings for the best precision:

```bash
docker run --rm -v "$PWD:/data" loglensai/loglens:deep analyze --source app.log --deep
```

---

## Notes

- Runs as a non-root user; `/data` is the working directory and volume.
- Detection is 100% local - your logs never leave the container unless you opt
  into an LLM key, and even then only *grouped anomaly summaries* are sent.
- MIT licensed. Source: https://github.com/ParasRajput810/LogLens-AI