"""
Generates a Sankey diagram (All Taxa → Jaccard tier → Final band)
using Plotly and exports it to PNG via kaleido.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ── Colour palette ─────────────────────────────────────────────────────────────

_NODE_COLOURS = {
    "All Taxa":     "#5C9EAD",
    "auto-accept":  "#1B5E20",
    "grey-zone":    "#607D8B",
    "flag":         "#E64A19",
    "not-accept":   "#B71C1C",
    "green":        "#1B5E20",
    "yellow_green": "#8BC34A",
    "yellow":       "#F9A825",
    "red":          "#C62828",
    "black":        "#212121",
}

_DISPLAY_LABELS = {
    "All Taxa":     "All Taxa",
    "auto-accept":  "auto-accept",
    "grey-zone":    "grey-zone",
    "flag":         "flag",
    "not-accept":   "not-accept",
    "green":        "green",
    "yellow_green": "yellow-green",
    "yellow":       "yellow",
    "red":          "red",
    "black":        "black",
}

_JACCARD_ORDER = ["auto-accept", "grey-zone", "flag", "not-accept"]
_FINAL_ORDER   = ["green", "yellow_green", "yellow", "red", "black"]

_LINK_COLOUR = "rgba(160, 160, 160, 0.35)"


def generate_sankey(run_dir: Path) -> Path | None:
    """Build and save plots/panel_C_sankey.png inside run_dir."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        logger.warning("[PLOTS] plotly not installed — run: pip install plotly kaleido")
        return None

    mapping_csv = run_dir / "results" / "final_mapping.csv"
    if not mapping_csv.exists():
        logger.warning(f"[PLOTS] final_mapping.csv not found: {mapping_csv}")
        return None

    df = pd.read_csv(mapping_csv)

    # Derive final band (auto-accept → green, rescue result or black)
    if "final_band" not in df.columns:
        df["final_band"] = None

    def _resolve_final(row: pd.Series) -> str:
        if row["bands"] == "auto-accept":
            return "green"
        fb = row["final_band"]
        if pd.notna(fb) and str(fb).strip() not in ("", "nan"):
            return str(fb).strip()
        return "black"

    df["_final"] = df.apply(_resolve_final, axis=1)

    # ── Nodes ──────────────────────────────────────────────────────────────────
    jaccard_present = [b for b in _JACCARD_ORDER if b in df["bands"].values]
    final_present   = [b for b in _FINAL_ORDER   if b in df["_final"].values]
    all_nodes       = ["All Taxa"] + jaccard_present + final_present
    idx             = {n: i for i, n in enumerate(all_nodes)}

    counts: dict[str, int] = {"All Taxa": len(df)}
    for b in jaccard_present:
        counts[b] = int((df["bands"] == b).sum())
    for b in final_present:
        counts[b] = int((df["_final"] == b).sum())

    node_labels = [
        f"{_DISPLAY_LABELS.get(n, n)}<br><b>{counts.get(n, 0)}</b>"
        for n in all_nodes
    ]
    node_colors = [_NODE_COLOURS.get(n, "#90A4AE") for n in all_nodes]

    # ── Links ──────────────────────────────────────────────────────────────────
    sources: list[int] = []
    targets: list[int] = []
    values:  list[int] = []

    # All Taxa → each Jaccard band
    for band in jaccard_present:
        n = counts[band]
        if n > 0:
            sources.append(idx["All Taxa"])
            targets.append(idx[band])
            values.append(n)

    # Each Jaccard band → each Final band
    for jband in jaccard_present:
        sub = df[df["bands"] == jband]
        for fband in final_present:
            n = int((sub["_final"] == fband).sum())
            if n > 0:
                sources.append(idx[jband])
                targets.append(idx[fband])
                values.append(n)

    link_colors = [_LINK_COLOUR] * len(sources)

    # ── Figure ─────────────────────────────────────────────────────────────────
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20,
            thickness=24,
            line=dict(color="white", width=0.8),
            label=node_labels,
            color=node_colors,
            hovertemplate="%{label}<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
            hovertemplate="%{source.label} → %{target.label}: <b>%{value}</b><extra></extra>",
        ),
        textfont=dict(size=12, color="#1a1a1a", family="Arial, sans-serif"),
    ))

    fig.update_layout(
        title=dict(
            text="Mapping flow: All Taxa → Jaccard tier → Final band",
            font=dict(size=14, color="#333333", family="Arial, sans-serif"),
            x=0.5,
            xanchor="center",
        ),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=40, r=40, t=60, b=20),
        width=960,
        height=500,
    )

    plots_dir = run_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    out_png = plots_dir / "panel_C_sankey.png"

    try:
        fig.write_image(str(out_png), width=960, height=500, scale=2)
        return out_png
    except Exception as exc:
        logger.warning(f"[PLOTS] PNG export failed: {exc}")
        logger.warning("[PLOTS] Ensure kaleido is installed: pip install kaleido")
        return None
