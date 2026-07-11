from __future__ import annotations

import datetime
import html
from typing import Dict, List, Optional, Sequence

LEVEL_COLORS = {
    "EMERGENCY": "#ff2d55", "FATAL": "#ff2d55", "CRITICAL": "#ff453a",
    "ERROR": "#ff6b6b", "WARN": "#ffd60a", "WARNING": "#ffd60a",
    "NOTICE": "#ffcc00", "INFO": "#8e8e93", "DEBUG": "#636366",
}


def _md_to_html(md: str) -> str:
    out: List[str] = []
    in_list = False
    for line in md.splitlines():
        s = line.strip()
        esc = html.escape(s)
        # bold
        while "**" in esc:
            esc = esc.replace("**", "<​strong>", 1).replace("**", "<​/strong>", 1)
        if s.startswith("## "):
            if in_list:
                out.append("<​/ul>"); in_list = False
            out.append(f"<h3>{esc[3:]}</h3>")
        elif s.startswith("# "):
            if in_list:
                out.append("<​/ul>"); in_list = False
            out.append(f"<h2>{esc[2:]}</h2>")
        elif s.startswith(("- ", "* ")):
            if not in_list:
                out.append("<​ul>"); in_list = True
            out.append(f"<li>{esc[2:]}</li>")
        elif s and s[0].isdigit() and ". " in s[:4]:
            if not in_list:
                out.append("<​ul>"); in_list = True
            out.append(f"<li>{esc}</li>")
        elif s == "":
            if in_list:
                out.append("<​/ul>"); in_list = False
        else:
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("<​/ul>")
    return "\n".join(out)


def render_html_report(
    source: str,
    total_lines: int,
    anomalies: Sequence,          
    level_counts: Dict[str, int],
    rca_markdown: Optional[str] = None,
    rca_meta: Optional[Dict[str, str]] = None,
    max_rows: int = 200,
) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = len(anomalies)
    rate = (n / total_lines * 100) if total_lines else 0.0

    # severity chips
    chips = "".join(
        f'<span class="chip" style="border-color:{LEVEL_COLORS.get(lvl, "#888")};'
        f'color:{LEVEL_COLORS.get(lvl, "#888")}">{lvl}: {cnt:,}</span>'
        for lvl, cnt in level_counts.items()
    )

    # anomaly table rows
    rows = []
    for a in list(anomalies)[:max_rows]:
        lvl = a.level.upper()
        color = LEVEL_COLORS.get(lvl, "#888")
        rows.append(
            f"<tr><td><span class='lvl' style='background:{color}'>{html.escape(lvl)}</span></td>"
            f"<td>{html.escape(a.service)}</td>"
            f"<td class='msg'>{html.escape((a.message or a.raw)[:200])}</td></tr>"
        )
    table_rows = "\n".join(rows)
    truncated = f"<p class='dim'>Showing first {max_rows} of {n:,} anomalies.</p>" if n > max_rows else ""

    rca_section = ""
    if rca_markdown:
        meta = rca_meta or {}
        rca_section = f"""
    <div class="card">
      <h2>🧠 AI Root-Cause Analysis</h2>
      <p class="dim">Provider: {html.escape(meta.get('provider', ''))} ({html.escape(meta.get('model', ''))})
         &nbsp;•&nbsp; Tokens: {html.escape(str(meta.get('tokens', '')))}</p>
      <div class="rca">{_md_to_html(rca_markdown)}</div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LogLens AI Report — {html.escape(source)}</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background:#0d1117; color:#e6edf3; margin:0; padding:24px; }}
  h1 {{ color:#58a6ff; }} h2 {{ color:#58a6ff; margin-top:0; }} h3 {{ color:#79c0ff; }}
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
  .rca p, .rca li {{ line-height:1.55; }}
</style>
</head>
<body>
  <h1>🔍 LogLens AI Report</h1>
  <p class="dim">Source: {html.escape(source)} &nbsp;•&nbsp; Generated: {now}</p>

  <div class="card">
    <div class="stats">
      <div class="stat"><div class="num">{total_lines:,}</div><div class="lbl">Lines analyzed</div></div>
      <div class="stat"><div class="num" style="color:#ff6b6b">{n:,}</div><div class="lbl">Anomalies</div></div>
      <div class="stat"><div class="num">{rate:.2f}%</div><div class="lbl">Anomaly rate</div></div>
    </div>
    <div>{chips}</div>
  </div>
{rca_section}
  <div class="card">
    <h2>🚨 Anomalies</h2>
    <table>
      <tr><th>Level</th><th>Service</th><th>Message</th></tr>
      {table_rows}
    </table>
    {truncated}
  </div>
  <p class="dim">Generated by LogLens AI — detection ran 100% locally.</p>
</body>
</html>"""