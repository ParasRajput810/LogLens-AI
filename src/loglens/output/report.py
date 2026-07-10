from __future__ import annotations


import html
from typing import Optional

import numpy as np

from loglens.pipeline.detector import DetectionResult, get_severity


def _svg_bar_chart(pairs, width=460, bar_h=26, gap=10):
    if not pairs:
        return "<p class='muted'>No data.</p>"
    mx = max(v for _, v in pairs) or 1
    rows = []
    y = 0
    for label, val in pairs:
        w = int((val / mx) * (width - 150))
        rows.append(
            f'<g transform="translate(0,{y})">'
            f'<text x="0" y="{bar_h*0.7:.0f}" class="lbl">{html.escape(str(label))}</text>'
            f'<rect x="110" y="2" width="{max(w,2)}" height="{bar_h-4}" rx="3" class="bar"/>'
            f'<text x="{115+max(w,2)}" y="{bar_h*0.7:.0f}" class="val">{val:,}</text>'
            f'</g>')
        y += bar_h + gap
    h = y
    return (f'<svg viewBox="0 0 {width} {h}" width="100%" '
            f'style="max-width:{width}px">{"".join(rows)}</svg>')


def _score_histogram(scores, threshold, width=460, height=140, bins=20):
    s = np.asarray(scores, dtype=float)
    s = s[(s > 0) & (s <= 1)]
    if len(s) == 0:
        return "<p class='muted'>No scored entries.</p>"
    hist, edges = np.histogram(s, bins=bins, range=(0, 1))
    mx = hist.max() or 1
    bw = width / bins
    bars = []
    for i, c in enumerate(hist):
        bh = (c / mx) * (height - 20)
        x = i * bw
        color = "#e04b4b" if edges[i] >= threshold else "#4b9ce0"
        bars.append(f'<rect x="{x:.1f}" y="{height-20-bh:.1f}" '
                    f'width="{bw-1:.1f}" height="{bh:.1f}" fill="{color}"/>')
    tx = threshold * width
    bars.append(f'<line x1="{tx:.1f}" y1="0" x2="{tx:.1f}" y2="{height-20}" '
                f'stroke="#111" stroke-dasharray="4 3"/>')
    bars.append(f'<text x="{tx+3:.1f}" y="12" class="val">thr {threshold:.2f}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'style="max-width:{width}px">{"".join(bars)}</svg>')


def render_html(result: DetectionResult, title: str = "LogLens Report") -> str:
    s = result.summary()
    meta = result.meta

    sev_counts = {}
    for e in result.entries:
        lv = e.level.upper()
        sev_counts[lv] = sev_counts.get(lv, 0) + 1
    sev_pairs = sorted(sev_counts.items(), key=lambda kv: get_severity(kv[0]))

    group_rows = []
    for g in result.groups[:50]:
        group_rows.append(
            f"<tr><td><span class='sev sev-{html.escape(g.level.lower())}'>"
            f"{html.escape(g.level)}</span></td>"
            f"<td class='num'>{g.score:.2f}</td>"
            f"<td class='num'>{g.count:,}</td>"
            f"<td>{html.escape(', '.join(g.services))}</td>"
            f"<td class='tmpl'>{html.escape(g.template[:120])}</td>"
            f"<td class='reasons'>{html.escape('; '.join(g.reasons[:4]))}</td></tr>")
    if not group_rows:
        group_rows = ["<tr><td colspan='6' class='muted'>No anomaly groups flagged.</td></tr>"]

    incident = (f"<div class='banner'>{html.escape(result.incident_note)}</div>"
                if result.incident_mode and result.incident_note else "")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#0f1115;--card:#171a21;--fg:#e6e8ec;--muted:#8b93a1;--line:#252a33;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:28px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:26px 0 10px}}
.muted{{color:var(--muted)}}
.cards{{display:flex;gap:14px;flex-wrap:wrap;margin-top:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 20px;min-width:130px}}
.card .n{{font-size:26px;font-weight:700}}
.card .k{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
.banner{{background:#3a2020;border:1px solid #6b2b2b;color:#ffb3b3;
padding:10px 14px;border-radius:8px;margin-top:14px}}
.grid{{display:flex;gap:24px;flex-wrap:wrap;margin-top:8px}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;flex:1;min-width:300px}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.tmpl{{font-family:ui-monospace,Menlo,monospace;color:#bcd}}
.reasons{{color:var(--muted);font-size:12px}}
.sev{{padding:2px 7px;border-radius:6px;font-size:11px;font-weight:700}}
.sev-critical,.sev-crit,.sev-fatal,.sev-alert,.sev-emergency,.sev-emerg,.sev-panic{{background:#5a1e1e;color:#ffbcbc}}
.sev-error,.sev-err{{background:#4a2a1a;color:#ffd0a8}}
.sev-warn,.sev-warning{{background:#463c17;color:#ffe9a3}}
.sev-notice,.sev-info,.sev-debug,.sev-trace{{background:#1e2c3a;color:#a8d0ff}}
.bar{{fill:#4b9ce0}} .lbl{{fill:var(--fg);font-size:12px}}
.val{{fill:var(--muted);font-size:11px}}
text{{font-family:inherit}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="muted">{s['entries']:,} entries · {meta.get('unique_templates',0):,} templates ·
threshold {meta.get('threshold_used',0):.2f}</div>
{incident}
<div class="cards">
<div class="card"><div class="n">{s['anomalies']:,}</div><div class="k">Anomalies</div></div>
<div class="card"><div class="n">{s['anomaly_groups']:,}</div><div class="k">Groups</div></div>
<div class="card"><div class="n">{s['clusters']:,}</div><div class="k">Clusters</div></div>
<div class="card"><div class="n">{meta.get('chronic_templates',0):,}</div><div class="k">Chronic</div></div>
<div class="card"><div class="n">{meta.get('global_rare_templates',0):,}</div><div class="k">Globally rare</div></div>
</div>
<div class="grid">
<div class="panel"><h2>Severity mix</h2>{_svg_bar_chart(sev_pairs)}</div>
<div class="panel"><h2>Score distribution</h2>
{_score_histogram(result.scores, float(meta.get('threshold_used',0.7)))}</div>
</div>
<h2>Top anomaly groups</h2>
<table><thead><tr><th>Level</th><th class="num">Score</th><th class="num">Count</th>
<th>Services</th><th>Template</th><th>Why</th></tr></thead>
<tbody>{''.join(group_rows)}</tbody></table>
<p class="muted" style="margin-top:24px">Generated by LogLens.</p>
</body></html>"""


def write_report(result: DetectionResult, path: str,
                 title: str = "LogLens Report") -> str:
    out = render_html(result, title=title)
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path
