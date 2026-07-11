from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from loglens.models import LogEntry
from loglens.llm.providers import LLMClient, LLMConfig, TokenUsage

MAX_ANOMALY_LINES = 40       
MAX_CONTEXT_LINES = 20      
MAX_LINE_CHARS = 300

SYSTEM_PROMPT = (
    "You are a senior Site Reliability Engineer performing root-cause analysis "
    "on anomalies detected in production logs. Be precise and honest: if evidence "
    "is insufficient, say so. Never invent log lines or services not shown.\n\n"
    "Respond in exactly this markdown structure:\n"
    "## Incident Summary\n(2-3 sentences, plain English)\n"
    "## Probable Root Cause\n(most likely cause + confidence: high/medium/low)\n"
    "## Evidence\n(bullet list citing the specific log lines/templates)\n"
    "## Impact\n(what is affected)\n"
    "## Recommended Actions\n(numbered, most urgent first)\n"
)

ASK_SYSTEM_PROMPT = (
    "You are a senior Site Reliability Engineer. You are given a digest of "
    "anomalies detected in production logs. Answer the user's question about "
    "these logs precisely and honestly. If the digest does not contain enough "
    "evidence to answer, say so clearly. Never invent log lines or services "
    "not shown. Answer in concise markdown."
)


@dataclass
class RCAResult:
    report: str          
    provider: str
    model: str
    anomalies_sent: int  # how many anomaly lines were included
    usage: TokenUsage = field(default_factory=TokenUsage)


def _clip(s: str) -> str:
    s = s.strip()
    return s if len(s) <= MAX_LINE_CHARS else s[: MAX_LINE_CHARS] + "…"


def build_rca_context(
    anomalies: Sequence[LogEntry],
    scores: Sequence[float] = (),
    reasons: Sequence[str] = (),
    context_lines: Sequence[str] = (),
    source_name: str = "",
) -> str:
    """Build a compact, privacy-conscious context block for the LLM."""
    parts: List[str] = []
    if source_name:
        parts.append(f"Log source: {source_name}")
    parts.append(f"Total anomalies detected locally: {len(anomalies)}")
    parts.append("\n--- ANOMALOUS LINES (top, by score) ---")
    for i, e in enumerate(list(anomalies)[:MAX_ANOMALY_LINES]):
        sc = f" score={scores[i]:.2f}" if i < len(scores) else ""
        rs = f" reason={reasons[i]}" if i < len(reasons) and reasons[i] else ""
        parts.append(f"[{e.level}] {e.service}: {_clip(e.message or e.raw)}{sc}{rs}")
    if context_lines:
        parts.append("\n--- SURROUNDING NORMAL CONTEXT (sample) ---")
        for ln in list(context_lines)[:MAX_CONTEXT_LINES]:
            parts.append(_clip(ln))
    return "\n".join(parts)


def run_rca(
    anomalies: Sequence[LogEntry],
    config: LLMConfig,
    scores: Sequence[float] = (),
    reasons: Sequence[str] = (),
    context_lines: Sequence[str] = (),
    source_name: str = "",
) -> RCAResult:
    if not anomalies:
        return RCAResult(
            report="No anomalies were detected — nothing to analyze. ✅",
            provider=config.provider, model=config.model, anomalies_sent=0,
        )
    context = build_rca_context(anomalies, scores, reasons, context_lines, source_name)
    client = LLMClient(config)
    report = client.chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ])
    return RCAResult(
        report=report,
        provider=config.provider,
        model=config.model,
        anomalies_sent=min(len(anomalies), MAX_ANOMALY_LINES),
        usage=client.last_usage,
    )


def run_ask(
    question: str,
    anomalies: Sequence[LogEntry],
    config: LLMConfig,
    scores: Sequence[float] = (),
    reasons: Sequence[str] = (),
    source_name: str = "",
) -> RCAResult:
    """Ask a free-form question about the detected anomalies."""
    if not anomalies:
        return RCAResult(
            report="No anomalies were detected — there is nothing to ask about. ✅",
            provider=config.provider, model=config.model, anomalies_sent=0,
        )
    context = build_rca_context(anomalies, scores, reasons, source_name=source_name)
    client = LLMClient(config)
    answer = client.chat([
        {"role": "system", "content": ASK_SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}\n\n--- QUESTION ---\n{question}"},
    ])
    return RCAResult(
        report=answer,
        provider=config.provider,
        model=config.model,
        anomalies_sent=min(len(anomalies), MAX_ANOMALY_LINES),
        usage=client.last_usage,
    )


def save_report(result: RCAResult, path: str, source_name: str = "") -> None:
    """Save an RCA report as a markdown file."""
    import datetime
    header = (
        f"# LogLens AI — Root-Cause Analysis\n\n"
        f"- **Source:** {source_name or 'n/a'}\n"
        f"- **Generated:** {datetime.datetime.now().isoformat(timespec='seconds')}\n"
        f"- **Provider:** {result.provider} ({result.model})\n"
        f"- **Anomaly summaries analyzed:** {result.anomalies_sent}\n"
        f"- **Tokens used:** {result.usage.total_tokens}\n\n---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + result.report + "\n")