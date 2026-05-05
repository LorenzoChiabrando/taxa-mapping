"""
taxa_mapping/pdf_report.py
==========================
Generates a per-run PDF debug report from the files written by run.py.

Public API
----------
    generate_pdf_report(run_dir: Path) -> Path

Reads:
    <run_dir>/debug/00_input.csv              (original + cleaned names, pre-dedup)
    <run_dir>/debug/01_jaccard_raw.csv
    <run_dir>/debug/02_filtering_stats.json
    <run_dir>/debug/03_rescue_process.csv     (optional absent when all auto-accepted)
    <run_dir>/results/mapping_report.json

Writes:
    <run_dir>/debug_report.pdf

Requires:
    pip install weasyprint
"""
from __future__ import annotations

import base64
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── thresholds ─────────────────────────────────────────────────────────────────

_INLINE_MAX   = 10    # ≤ this → pipe-separated inline
_GRID_MAX     = 100   # ≤ this → 3-column grid  (>_INLINE_MAX)
                      # > _GRID_MAX → count note only

# ── colour palette ─────────────────────────────────────────────────────────────

_STATUS_COLOR: dict[str, str] = {
    "unambiguous":       "#2e7d32",
    "high_similarity":   "#558b2f",
    "near_tier":         "#f57f17",
    "low_similarity":    "#c62828",
    "no_correspondence": "#424242",
}

_BAND_COLOR: dict[str, str] = {
    "auto-accept":  "#2e7d32",
    "grey-zone":    "#ef6c00",
    "flag":         "#8d6e63",
    "not-accept":   "#c62828",
    "na":           "#757575",
    "yellow_green": "#558b2f",
    "yellow":       "#f57f17",
    "red":          "#c62828",
    "black":        "#424242",
    "green":        "#2e7d32",
}

# ── CSS ────────────────────────────────────────────────────────────────────────

_CSS = """
@page { margin: 1.8cm 2cm; }
body {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 9.5pt;
    color: #222;
    line-height: 1.4;
}
h1  { font-size: 14pt; margin-bottom: 4px; }
h2  { font-size: 11pt; border-bottom: 2px solid #ddd;
      padding-bottom: 3px; margin-top: 20px; }
table {
    border-collapse: collapse;
    width: 100%;
    font-size: 8.5pt;
    margin: 5px 0 8px 0;
}
th, td {
    border: 1px solid #ccc;
    padding: 3px 7px;
    text-align: left;
    vertical-align: top;
}
th  { background: #f4f4f4; font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
code {
    font-family: 'Courier New', monospace;
    font-size: 7.8pt;
    background: #f0f0f0;
    padding: 0 3px;
    border-radius: 2px;
}
.meta  { font-size: 8.5pt; color: #555; margin: 2px 0; }
.footnote { font-size: 7.5pt; color: #777; margin-top: 4px; }

/* ── dedup table ── */
.dedup-dropped { background: #fff3e0; }
.dedup-ok      { }

/* ── taxon card ── */
.taxon-card {
    border: 1px solid #ddd;
    border-radius: 4px;
    margin-bottom: 14px;
    page-break-inside: avoid;
}
.taxon-header {
    padding: 6px 10px;
    border-radius: 4px 4px 0 0;
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
}
.taxon-num  { font-size: 8pt; color: #888; min-width: 20px; }
.taxon-name { font-weight: bold; font-size: 10pt; flex: 1; }
.badge {
    font-size: 7.5pt;
    font-weight: bold;
    padding: 1px 7px;
    border-radius: 10px;
    color: white;
    white-space: nowrap;
}
.conf      { font-size: 8pt; color: #555; }
.mapped-id { font-size: 8pt; font-family: monospace; color: #333; }
.taxon-body   { padding: 8px 10px; }
.cleaning-note { font-size: 8pt; color: #666; margin-bottom: 6px; }

/* ── phases ── */
.phase-block { margin-bottom: 10px; }
.phase-title {
    font-weight: 600;
    font-size: 8.5pt;
    color: #444;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.na-note    { font-size: 8pt; color: #888; font-style: italic; }
.rationale  { font-size: 8pt; margin: 2px 0; }
.rationale b { color: #555; }

/* ── candidate display ── */
.cand-section  { margin-top: 5px; }
.cand-label    { font-weight: 600; font-size: 8pt; color: #555; display: block;
                 margin-bottom: 3px; }
.cand-overflow { font-style: italic; color: #999; font-size: 7.5pt; }

/* candidate table — Jaccard and NCBI (shared style) */
.ncbi-table { margin: 2px 0 0 0; table-layout: fixed; }
.ncbi-table th { font-size: 7.5pt; }
.ncbi-table td { font-size: 7.5pt; word-break: break-all; overflow-wrap: break-word; }
.ncbi-table col.col-model  { width: 52%; }
.ncbi-table col.col-score  { width: 10%; }
.ncbi-table col.col-reason { width: 38%; }
.ncbi-table tr.preferred td {
    background: #e8f5e9;
    font-weight: 600;
}

/* ── pipeline path footer ── */
.path-line {
    font-size: 8pt;
    background: #f9f9f9;
    border-top: 1px solid #eee;
    padding: 4px 10px;
    border-radius: 0 0 4px 4px;
    color: #444;
}
.arrow { color: #bbb; margin: 0 4px; }
hr.section { border: none; border-top: 2px solid #eee; margin: 16px 0; }
"""


# ── tiny HTML helpers ──────────────────────────────────────────────────────────

def _badge(label: str, color: str, fs: str = "7.5pt") -> str:
    return (f'<span class="badge" style="background:{color};font-size:{fs}">'
            f'{label}</span>')


def _band_badge(band: str) -> str:
    return _badge(band, _BAND_COLOR.get(band, "#888"), "7pt")


def _has_gs_badge(value: bool) -> str:
    if value:
        return ('<span style="color:#2e7d32;font-weight:bold;font-size:8.5pt">✓</span>'
                ' <span style="font-size:7.5pt;color:#2e7d32">G+S</span>')
    return ('<span style="color:#c62828;font-weight:bold;font-size:8.5pt">✗</span>'
            ' <span style="font-size:7.5pt;color:#999">G+S</span>')


# ── candidate renderers ────────────────────────────────────────────────────────

def _render_jaccard_candidates(rec: dict) -> str:
    """Single-column table; preferred candidate (mat) highlighted. Count-only when > _GRID_MAX."""
    n         = rec["n_candidates"]
    score     = rec["j_score"]
    cands     = rec["candidates"]  # populated only when n ≤ _GRID_MAX
    preferred = rec.get("preferred", "")

    if n == 0:
        return '<span class="na-note">—</span>'

    if n > _GRID_MAX:
        return (f'<span class="cand-overflow">'
                f'No specific match &mdash; {n} candidates tied at j_score={score:.3f}'
                f'</span>')

    if not cands:
        return f'<span class="cand-overflow">{n} candidates</span>'

    rows = [f"<tr><th>Model &nbsp;<span style='font-weight:normal;color:#888'>"
            f"(all at j_score={score:.3f})</span></th></tr>"]
    for c in cands:
        is_pref = (c == preferred)
        tr_cls  = ' class="preferred"' if is_pref else ""
        marker  = " &#9654;" if is_pref else ""  # ▶
        rows.append(f"<tr{tr_cls}><td><code>{c}</code>{marker}</td></tr>")
    return f'<table class="ncbi-table">{"".join(rows)}</table>'


def _render_ncbi_candidates(rec: dict) -> str:
    """Mini-table (Model | Score | Reason); preferred candidate (suggested_gem) highlighted."""
    n         = rec["n_candidates"]
    cands     = rec["candidates"]  # populated only when n ≤ _GRID_MAX
    preferred = rec.get("preferred", "")

    if n == 0:
        return '<span class="na-note">—</span>'

    if n > _GRID_MAX:
        return (f'<span class="cand-overflow">'
                f'{n} candidates — list omitted (&gt;{_GRID_MAX})'
                f'</span>')

    if not cands:
        return f'<span class="cand-overflow">{n} candidates</span>'

    rows = [
        '<colgroup>'
        '<col class="col-model"><col class="col-score"><col class="col-reason">'
        '</colgroup>'
        "<tr><th>Model</th><th>Score</th><th>Reason</th></tr>"
    ]
    for c in cands:
        is_pref = (c["model"] == preferred)
        tr_cls  = ' class="preferred"' if is_pref else ""
        marker  = " &#9654;" if is_pref else ""  # ▶
        rows.append(
            f"<tr{tr_cls}>"
            f"<td><code>{c['model']}</code>{marker}</td>"
            f"<td class='num'>{c['score']}</td>"
            f"<td>{c['reason'] or '—'}</td>"
            f"</tr>"
        )
    return f'<table class="ncbi-table">{"".join(rows)}</table>'


# ── data loading ───────────────────────────────────────────────────────────────

def _s(val) -> str:
    v = str(val) if val is not None else ""
    return "" if v == "nan" else v

def _f(val, d: float = 0.0) -> float:
    try:    return float(val)
    except: return d  # noqa: E722

def _i(val, d: int = 0) -> int:
    try:    return int(val)
    except: return d  # noqa: E722


def _parse_jaccard_candidates(raw, n: int) -> list[str]:
    if n > _GRID_MAX:
        return []
    s = _s(raw)
    return [c.strip() for c in s.split(";") if c.strip()] if s else []


def _parse_ncbi_candidates(raw) -> list[dict]:
    s = _s(raw)
    if not s or s == "no candidates":
        return []
    out = []
    for item in s.split(";"):
        item = item.strip()
        if not item:
            continue
        parts = item.split("@@")
        if len(parts) == 3:
            out.append({"model": parts[0], "score": parts[1], "reason": parts[2]})
        elif len(parts) == 2:
            out.append({"model": parts[0], "score": parts[1], "reason": ""})
        else:
            out.append({"model": item, "score": "?", "reason": ""})
    return out


def _load(run_dir: Path) -> tuple[list[dict], dict, dict, list[dict]]:
    """
    Returns (records, filtering_stats, report_json, dedup_info).

    dedup_info: list of dicts {taxa_name, taxon, dropped: bool, merged_into: str|None}
    """
    input_path  = run_dir / "debug" / "00_input.csv"
    jaccard_path = run_dir / "debug" / "01_jaccard_raw.csv"
    stats_path   = run_dir / "debug" / "02_filtering_stats.json"
    rescue_path  = run_dir / "debug" / "03_rescue_process.csv"
    report_path  = run_dir / "results" / "mapping_report.json"

    for p in (jaccard_path, stats_path, report_path):
        if not p.exists():
            raise FileNotFoundError(f"Required debug file not found: {p}")

    df_j = pd.read_csv(jaccard_path)
    with open(stats_path) as f:
        stats = json.load(f)
    with open(report_path) as f:
        report = json.load(f)

    # ── deduplication info ─────────────────────────────────────────────────────
    dedup_info: list[dict] = []
    if input_path.exists():
        df_in   = pd.read_csv(input_path)
        kept    = set(_s(v) for v in df_j["taxa_name"].tolist())
        # For each dropped name, find the surviving representative:
        # it's the one in the jaccard output that shares the same anchor.
        anchor_map: dict[str, str] = {}  # anchor → surviving taxa_name
        for _, row in df_j.iterrows():
            anchor_map[_s(row.get("anchor"))] = _s(row.get("taxa_name"))

        for _, row in df_in.iterrows():
            name   = _s(row.get("taxa_name"))
            taxon  = _s(row.get("taxon"))
            dropped = name not in kept
            merged_into: Optional[str] = None
            if dropped:
                # best guess: same anchor in the surviving set
                from taxa_mapping.core.tokenization import extract_anchor  # lazy import
                anchor = extract_anchor(taxon)
                merged_into = anchor_map.get(anchor)
            dedup_info.append({
                "taxa_name":   name,
                "taxon":       taxon,
                "dropped":     dropped,
                "merged_into": merged_into,
            })

    # ── rescue index ──────────────────────────────────────────────────────────
    rescue_idx: dict[str, dict] = {}
    if rescue_path.exists():
        for _, row in pd.read_csv(rescue_path).iterrows():
            rescue_idx[_s(row.get("taxon"))] = row.to_dict()

    report_idx = {item["query_name"]: item for item in report.get("results", [])}

    # ── per-taxon records ─────────────────────────────────────────────────────
    records: list[dict] = []
    for _, jrow in df_j.iterrows():
        original = _s(jrow.get("taxa_name"))
        taxon    = _s(jrow.get("taxon"))
        n_cand   = _i(jrow.get("n_candidates"))
        j_score  = _f(jrow.get("j_score"))

        j_rec = {
            "anchor":       _s(jrow.get("anchor")),
            "j_score":      j_score,
            "has_gs":       bool(jrow.get("has_gs")),
            "bands":        _s(jrow.get("bands")),
            "n_candidates": n_cand,
            "candidates":   _parse_jaccard_candidates(jrow.get("mat_candidates_str"), n_cand),
            "preferred":    _s(jrow.get("mat")),
        }

        r_raw = rescue_idx.get(taxon)
        r_rec: Optional[dict] = None
        if r_raw is not None:
            ncbi_cands = _parse_ncbi_candidates(r_raw.get("ranked_candidates"))
            gem = _s(r_raw.get("suggested_gem"))
            r_rec = {
                "canonical":         _s(r_raw.get("canonical")),
                "rank":              _s(r_raw.get("rank")),
                "top_score":         _i(r_raw.get("top_score")),
                "n_top_ties":        _i(r_raw.get("n_top_ties")),
                "confidence":        _s(r_raw.get("confidence")),
                "match_level":       _s(r_raw.get("match_level")),
                "final_band":        _s(r_raw.get("final_band")),
                "rationale_scoring": _s(r_raw.get("rationale_scoring")),
                "rationale_final":   _s(r_raw.get("rationale_final")),
                "n_candidates":      len(ncbi_cands),
                "candidates":        ncbi_cands if len(ncbi_cands) <= _GRID_MAX else [],
                "preferred":         gem if gem not in ("no_suggestion", "") else "",
            }

        f_raw  = report_idx.get(original, {})
        mapped = _s(f_raw.get("mapped_id"))
        if mapped in ("no_suggestion", ""):
            mapped = ""

        records.append({
            "original": original,
            "taxon":    taxon,
            "jaccard":  j_rec,
            "rescue":   r_rec,
            "final": {
                "status":           _s(f_raw.get("status")),
                "confidence_score": _f(f_raw.get("confidence_score")),
                "mapped_id":        mapped,
            },
        })

    return records, stats, report, dedup_info


# ── visualizations ─────────────────────────────────────────────────────────────

_PANEL_TITLES: dict[str, str] = {
    "panel_A_landscape": "Panel A — Mapping Quality Landscape",
    "panel_B_heatmap":   "Panel B — Score × Tie-Bin Frequency by Tier",
    "panel_C_sankey":    "Panel C — Mapping Flow (Input type → Jaccard tier → Final band)",
}


def _embed_plots_section(run_dir: Path) -> str:
    """Return an HTML <h2>Visualizations</h2> block with base64-embedded PNGs, or ''."""
    plots_dir = run_dir / "plots"
    if not plots_dir.exists():
        return ""
    pngs = sorted(plots_dir.glob("*.png"))
    if not pngs:
        return ""
    parts = ["<h2>Visualizations</h2>"]
    for png in pngs:
        title = _PANEL_TITLES.get(png.stem, png.name)
        data  = base64.b64encode(png.read_bytes()).decode("ascii")
        parts.append(
            f'<div style="margin-bottom:18px;page-break-inside:avoid;">'
            f'<p style="font-weight:600;font-size:9pt;margin-bottom:5px;">{title}</p>'
            f'<img src="data:image/png;base64,{data}" '
            f'style="max-width:100%;height:auto;border:1px solid #e0e0e0;" />'
            f'</div>'
        )
    return "\n".join(parts)


# ── HTML builder ───────────────────────────────────────────────────────────────

def _build_html(
    records: list[dict],
    stats: dict,
    report: dict,
    dedup_info: list[dict],
    run_dir: Path,
) -> str:
    job_id    = report.get("jobId", "?")
    timestamp = report.get("timestamp", "?")
    total     = report.get("total_bacteria", len(records))
    counts    = Counter(r["final"]["status"] for r in records)
    n_input   = len(dedup_info) if dedup_info else total
    n_dropped = sum(1 for d in dedup_info if d["dropped"])

    w: list[str] = []
    out = w.append

    out(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Mapping Debug Report — {job_id}</title>
<style>{_CSS}</style>
</head>
<body>""")

    # ── document header
    out(f"<h1>Mapping Debug Report &mdash; Run <code>{job_id}</code></h1>")
    out(f'<p class="meta"><b>Timestamp:</b> {timestamp}</p>')
    out(f'<p class="meta"><b>Run directory:</b> <code>{run_dir}</code></p>')
    out(f'<p class="meta"><b>Input taxa:</b> {n_input}'
        f'{"" if not n_dropped else f" &nbsp;({n_dropped} removed by deduplication, {total} processed)"}'
        f'</p>')

    # ── dedup section (only when something was dropped)
    if dedup_info and n_dropped > 0:
        out("<h2>Input Deduplication</h2>")
        out("<p class='meta'>Taxa removed before processing because they share the same "
            "anchor (genus&nbsp;+&nbsp;species) with another entry in the input. "
            "The surviving representative is listed under <i>Merged into</i>.</p>")
        out("<table>")
        out("<tr><th>#</th><th>Original name</th><th>After cleaning</th>"
            "<th>Status</th><th>Merged into</th></tr>")
        for idx, d in enumerate(dedup_info, 1):
            if d["dropped"]:
                mi = f"<code>{d['merged_into']}</code>" if d["merged_into"] else "unknown"
                out(f'<tr class="dedup-dropped">'
                    f"<td>{idx}</td>"
                    f"<td>{d['taxa_name']}</td>"
                    f"<td><code>{d['taxon']}</code></td>"
                    f"<td>&#x26A0; removed</td>"
                    f"<td>{mi}</td>"
                    f"</tr>")
            else:
                out(f'<tr class="dedup-ok">'
                    f"<td>{idx}</td>"
                    f"<td>{d['taxa_name']}</td>"
                    f"<td><code>{d['taxon']}</code></td>"
                    f"<td>&#x2714; processed</td>"
                    f"<td>—</td>"
                    f"</tr>")
        out("</table>")

    # ── Jaccard filtering stats
    out("<h2>Jaccard Filtering Statistics</h2>")
    out("<table><tr><th>Field</th><th>Value</th></tr>")
    out(f"<tr><td>Taxa after deduplication</td><td>{stats.get('total_taxa', total)}</td></tr>")
    out(f"<tr><td>Auto-accepted (j_score &ge; 0.90 &amp; unique G+S match)</td>"
        f"<td>{stats.get('auto_accepted', 0)}</td></tr>")
    out(f"<tr><td>Sent to NCBI Rescue</td>"
        f"<td>{stats.get('need_rescue', 0)} ({stats.get('need_rescue_pct', 0)}%)</td></tr>")
    for band, count in stats.get("breakdown", {}).items():
        out(f"<tr><td>&nbsp;&nbsp;&rarr; {_band_badge(band)}</td><td>{count}</td></tr>")
    out("</table>")
    out('<p class="footnote">'
        '<b>has_gs</b> (Genus+Species matched): True when the query anchor contains '
        'exactly two tokens (genus + species epithet) <em>and</em> both tokens appear '
        'in the query token set <em>and</em> in the best-matching model\'s token set. '
        'Required for <code>auto-accept</code>; influences band assignment and NCBI scoring.'
        '</p>')

    # ── final results summary
    out("<h2>Final Results Summary</h2>")
    out("<table><tr><th>Status</th><th>Count</th><th>%</th></tr>")
    for status, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct   = count / total * 100 if total else 0
        color = _STATUS_COLOR.get(status, "#888")
        out(f"<tr><td>{_badge(status, color)}</td>"
            f"<td>{count}</td><td>{pct:.1f}%</td></tr>")
    out("</table>")

    # ── visualizations (embedded if --plots was used)
    viz_html = _embed_plots_section(run_dir)
    if viz_html:
        out(viz_html)

    out('<hr class="section">')
    out("<h2>Per-Taxon Mapping Detail</h2>")

    # ── per-taxon cards
    for i, rec in enumerate(records, 1):
        j = rec["jaccard"]
        r = rec["rescue"]
        f = rec["final"]

        status = f["status"] or "?"
        mapped = f["mapped_id"] or "—"
        conf   = f["confidence_score"]
        color  = _STATUS_COLOR.get(status, "#888")
        bg     = color + "15"

        out(f'<div class="taxon-card">')

        # ── card header
        out(f'<div class="taxon-header" '
            f'style="background:{bg}; border-left: 4px solid {color}">')
        out(f'<span class="taxon-num">{i}.</span>')
        out(f'<span class="taxon-name">{rec["original"]}</span>')
        out(_badge(status, color))
        out(f'<span class="conf">confidence: {conf:.2f}</span>')
        if mapped != "—":
            out(f'<span class="mapped-id">&rarr; {mapped}</span>')
        out("</div>")  # taxon-header

        out('<div class="taxon-body">')

        if rec["original"] != rec["taxon"]:
            out(f'<p class="cleaning-note">'
                f'After cleaning: <code>{rec["taxon"]}</code></p>')

        # ── Phase 1 — Jaccard
        out('<div class="phase-block">')
        out('<div class="phase-title">Phase 1 &mdash; Jaccard Matching</div>')
        out("<table>")
        out("<tr>"
            "<th>anchor</th>"
            "<th>j_score</th>"
            "<th>has_gs <span style='font-weight:normal;font-size:7pt'>"
            "(genus+species in match)</span></th>"
            "<th>band</th>"
            "<th>n_candidates</th>"
            "</tr>")
        out(f"<tr>"
            f"<td><code>{j['anchor']}</code></td>"
            f"<td>{j['j_score']:.3f}</td>"
            f"<td>{_has_gs_badge(j['has_gs'])}</td>"
            f"<td>{_band_badge(j['bands'])}</td>"
            f"<td>{j['n_candidates']}</td>"
            f"</tr>")
        out("</table>")
        out('<div class="cand-section">')
        out(f'<span class="cand-label">Jaccard candidates ({j["n_candidates"]}):</span>')
        out(_render_jaccard_candidates(j))
        out("</div>")  # cand-section
        out("</div>")  # phase-block

        # ── Phase 2 — NCBI Rescue
        out('<div class="phase-block">')
        out('<div class="phase-title">Phase 2 &mdash; NCBI Rescue</div>')
        if r is None:
            out('<span class="na-note">Not applicable &mdash; '
                'taxon auto-accepted by Jaccard</span>')
        else:
            out("<table>")
            out("<tr><th>canonical name</th><th>rank</th><th>top_score</th>"
                "<th>n_top_ties</th><th>confidence</th>"
                "<th>match_level</th><th>final_band</th></tr>")
            canon = r["canonical"] or "—"
            fb    = _band_badge(r["final_band"]) if r["final_band"] else "—"
            out(f"<tr>"
                f"<td><code>{canon}</code></td>"
                f"<td>{r['rank'] or '—'}</td>"
                f"<td>{r['top_score']}</td>"
                f"<td>{r['n_top_ties']}</td>"
                f"<td><code>{r['confidence'] or '—'}</code></td>"
                f"<td><code>{r['match_level'] or '—'}</code></td>"
                f"<td>{fb}</td>"
                f"</tr>")
            out("</table>")
            out(f'<p class="rationale"><b>Scoring rationale:</b> '
                f'{r["rationale_scoring"] or "—"}</p>')
            out(f'<p class="rationale"><b>Final rationale:</b> '
                f'{r["rationale_final"] or "—"}</p>')
            out('<div class="cand-section">')
            out(f'<span class="cand-label">NCBI candidates ({r["n_candidates"]}):</span>')
            out(_render_ncbi_candidates(r))
            out("</div>")  # cand-section
        out("</div>")  # phase-block

        out("</div>")  # taxon-body

        # ── pipeline path footer
        ncbi_band = r["final_band"] if r else "skipped"
        nb = (_band_badge(ncbi_band) if ncbi_band != "skipped"
              else '<span style="color:#bbb">skipped</span>')
        out(f'<div class="path-line">'
            f'Pipeline path:&nbsp; {_band_badge(j["bands"])} '
            f'<span class="arrow">&rarr;</span> NCBI&nbsp;{nb} '
            f'<span class="arrow">&rarr;</span> {_badge(status, color)}'
            f'</div>')

        out("</div>")  # taxon-card

    out("</body></html>")
    return "\n".join(w)


# ── public entry point ─────────────────────────────────────────────────────────

def generate_pdf_report(run_dir: Path) -> Path:
    """
    Reads all debug files for *run_dir* and writes ``debug_report.pdf``.
    Returns the path to the generated file.
    Raises ImportError if weasyprint is not installed.
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError(
            "weasyprint is required for PDF reports.\n"
            "Install with: .venv/bin/pip install weasyprint"
        )

    records, stats, report, dedup_info = _load(run_dir)
    html = _build_html(records, stats, report, dedup_info, run_dir)

    out_path = run_dir / "debug_report.pdf"
    HTML(string=html).write_pdf(str(out_path))
    return out_path
