from __future__ import annotations

import html as _html
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from loglens.models import LogEntry

LEVEL_COLORS = {
    "EMERGENCY": "#ff2d55", "FATAL": "#ff375f", "CRITICAL": "#ff453a",
    "ERROR": "#ff6b6b", "WARN": "#ffd60a", "WARNING": "#ffd60a",
    "NOTICE": "#ffe28a", "INFO": "#8b949e", "DEBUG": "#6e7681",
}


def _esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _md_to_html(md: str) -> str:
    out, in_list = [], False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("- ") or s.startswith("* "):
            if not in_list:
                out.append("<​ul>")
                in_list = True
            out.append(f"<li>{_esc(s[2:])}</li>")
            continue
        if in_list:
            out.append("<​/ul>")
            in_list = False
        if s.startswith("### "):
            out.append(f"<h4>{_esc(s[4:])}</h4>")
        elif s.startswith("## "):
            out.append(f"<h3>{_esc(s[3:])}</h3>")
        elif s.startswith("# "):
            out.append(f"<h3>{_esc(s[2:])}</h3>")
        elif s:
            out.append(f"<p>{_esc(s)}</p>")
    if in_list:
        out.append("<​/ul>")
    return "\n".join(out)


def _bar_chart(pairs: List[tuple], colors: Optional[List[str]] = None,
               width: int = 640, bar_h: int = 22, gap: int = 8) -> str:
    if not pairs:
        return ""
    maxv = max(v for _, v in pairs) or 1
    label_w = 150
    h = len(pairs) * (bar_h + gap) + gap
    rows = []
    for i, (label, v) in enumerate(pairs):
        y = gap + i * (bar_h + gap)
        w = max(2, int((width - label_w - 90) * v / maxv))
        c = (colors[i] if colors and i < len(colors) else "#58a6ff")
        rows.append(
            f"<text x='{label_w - 8}' y='{y + bar_h - 6}' text-anchor='end' "
            f"fill='#8b949e' font-size='12'>{_esc(str(label)[:22])}</text>"
            f"<​rect x='{label_w}' y='{y}' width='{w}' height='{bar_h}' rx='4' fill='{c}'/>"
            f"<text x='{label_w + w + 8}' y='{y + bar_h - 6}' fill='#e6edf3' "
            f"font-size='12' font-weight='700'>{v:,}</text>"
        )
    return (f"<svg viewBox='0 0 {width} {h}' width='100%' "
            f"xmlns='http://www.w3.org/2000/svg'>{''.join(rows)}</svg>")


def _histogram(values: Sequence[float], bins: int = 20,
               width: int = 640, height: int = 140) -> str:
    if not values:
        return ""
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int(max(0.0, min(0.9999, float(v))) * bins))
        counts[idx] += 1
    maxc = max(counts) or 1
    bw = width / bins
    bars = []
    for i, c in enumerate(counts):
        bh = int((height - 30) * c / maxc)
        color = "#ff6b6b" if (i / bins) >= 0.7 else "#58a6ff"
        bars.append(f"<​rect x='{i * bw + 1:.1f}' y='{height - 20 - bh}' "
                    f"width='{bw - 2:.1f}' height='{bh}' rx='2' fill='{color}'/>")
    axis = (f"<text x='0' y='{height - 4}' fill='#8b949e' font-size='11'>0.0</text>"
            f"<text x='{width * 0.7:.0f}' y='{height - 4}' fill='#ff6b6b' font-size='11'>0.70 threshold</text>"
            f"<text x='{width - 24}' y='{height - 4}' fill='#8b949e' font-size='11'>1.0</text>"
            f"<​line x1='{width * 0.7:.0f}' y1='0' x2='{width * 0.7:.0f}' y2='{height - 22}' "
            f"stroke='#ff6b6b' stroke-dasharray='4 4' stroke-width='1'/>")
    return (f"<svg viewBox='0 0 {width} {height}' width='100%' "
            f"xmlns='http://www.w3.org/2000/svg'>{''.join(bars)}{axis}</svg>")


def render_html_report(source: str, total_lines: int,
                       anomalies: List[LogEntry],
                       level_counts: Dict[str, int],
                       rca_markdown: Optional[str] = None,
                       rca_meta: Optional[dict] = None,
                       scores: Optional[Sequence[float]] = None) -> str:
    n = len(anomalies)
    rate = (n / total_lines * 100) if total_lines else 0.0

    chips = "".join(
        f"<span class='chip' style='border-color:{LEVEL_COLORS.get(l.upper(), '#8b949e')};"
        f"color:{LEVEL_COLORS.get(l.upper(), '#8b949e')}'>{_esc(l)}: {c}</span>"
        for l, c in sorted(level_counts.items(), key=lambda kv: -kv[1]))

    rows = "".join(
        f"<tr><td><span class='lvl' style='background:"
        f"{LEVEL_COLORS.get(a.level.upper(), '#8b949e')}'>{_esc(a.level)}</span></td>"
        f"<td>{_esc(a.service)}</td><td class='msg'>{_esc(a.message[:200])}</td></tr>"
        for a in anomalies[:200])
    more = (f"<p class='dim'>… and {n - 200:,} more anomalies not shown.</p>"
            if n > 200 else "")

    lvl_pairs = sorted(level_counts.items(), key=lambda kv: -kv[1])
    lvl_chart = _bar_chart(
        lvl_pairs,
        colors=[LEVEL_COLORS.get(l.upper(), "#8b949e") for l, _ in lvl_pairs])
    svc_counts = Counter(a.service for a in anomalies).most_common(10)
    svc_chart = _bar_chart(svc_counts)
    score_chart = _histogram(list(scores)) if scores else ""

    charts_html = f"""
  <div class="card"><h2>📊 Severity Breakdown</h2>{lvl_chart}</div>
  <div class="card"><h2>🧩 Top Affected Services</h2>{svc_chart}</div>"""
    if score_chart:
        charts_html += f"""
  <div class="card"><h2>📈 Anomaly Score Distribution</h2>{score_chart}
  <p class="dim">Scores right of the dashed line were flagged.</p></div>"""

    rca_html = ""
    if rca_markdown:
        meta = rca_meta or {}
        meta_line = " • ".join(f"{k}: {_esc(v)}" for k, v in meta.items())
        rca_html = f"""
  <div class="card rca">
    <h2>🧠 AI Root-Cause Analysis</h2>
    <p class="dim">{meta_line}</p>
    {_md_to_html(rca_markdown)}
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LogLens AI Report — {_esc(source)}</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background:#0d1117; color:#e6edf3; margin:0; padding:24px; }}
  h1 {{ color:#58a6ff; }} h2 {{ color:#58a6ff; margin-top:0; }} h3, h4 {{ color:#79c0ff; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:12px; padding:20px 24px; margin-bottom:20px; }}
  .stats {{ display:flex; gap:24px; flex-wrap:wrap; }}
  .stat .num {{ font-size:28px; font-weight:700; }} .stat .lbl {{ color:#8b949e; font-size:12px; text-transform:uppercase; }}
  .chip {{ display:inline-block; border:1px solid; border-radius:999px; padding:2px 10px; margin:4px 6px 0 0; font-size:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid #21262d; }}
  th {{ color:#8b949e; text-transform:uppercase; font-size:11px; }}
  .lvl {{ color:#0d1117; font-weight:700; padding:1px 8px; border-radius:4px; font-size:11px; }}
  .msg {{ font-family: ui-monospace, monospace; color:#c9d1d9; }}
  .dim {{ color:#8b949e; font-size:12px; }}
  .rca p, .rca li {{ line-height:1.6; }}
</style>
</head>
<body>
  <h1>🔍 LogLens AI Report</h1>
  <p class="dim">Source: {_esc(source)} &nbsp;•&nbsp; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

  <div class="card">
    <div class="stats">
      <div class="stat"><div class="num">{total_lines:,}</div><div class="lbl">Lines analyzed</div></div>
      <div class="stat"><div class="num" style="color:#ff6b6b">{n:,}</div><div class="lbl">Anomalies</div></div>
      <div class="stat"><div class="num">{rate:.2f}%</div><div class="lbl">Anomaly rate</div></div>
    </div>
    <div>{chips}</div>
  </div>
{charts_html}
  <div class="card">
    <h2>🚨 Anomalies</h2>
    <table>
      <tr><th>Level</th><th>Service</th><th>Message</th></tr>
      {rows}
    </table>
    {more}
  </div>{rca_html}
  <p class="dim">Generated by LogLens AI — detection ran 100% locally.</p>
</body>
</html>"""