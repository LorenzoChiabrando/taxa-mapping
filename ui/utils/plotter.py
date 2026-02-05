import csv
import json
import sys
from pathlib import Path

max_int = sys.maxsize
while True:
    try:
        csv.field_size_limit(max_int)
        break
    except OverflowError:
        max_int = int(max_int / 10)

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    go = None
    PLOTLY_AVAILABLE = False


class SankeyGenerator:
    NODES_DEF = [
        {"label": "Input Taxa",        "color": "#2196F3"},  # 0
        {"label": "Auto-Accepted",     "color": "#2CC985"},  # 1
        {"label": "Grey-Zone",         "color": "#808080"},  # 2
        {"label": "Flag",              "color": "#FFD700"},  # 3
        {"label": "Not-Accept",        "color": "#EF553B"},  # 4
        {"label": "UNAMBIGUOUS",       "color": "#00CC96"},  # 5
        {"label": "HIGH SIMILARITY",   "color": "#A2D149"},  # 6
        {"label": "NEAR TIER",         "color": "#FECB52"},  # 7
        {"label": "LOW SIMILARITY",    "color": "#EF553B"},  # 8
        {"label": "NO CORRESPONDENCE", "color": "#000000"}   # 9
    ]

    STATUS_MAP = {
        "unambiguous": 5,
        "high_similarity": 6,
        "near_tier": 7,
        "low_similarity": 8,
        "no_correspondence": 9
    }

    @staticmethod
    def _clean_key(text):
        if not text:
            return ""
        return str(text).lower().replace(" ", "").replace("_", "").replace("-", "").strip()

    @staticmethod
    def _node_weights_from_links(n_nodes, sources, targets, values):
        tot_in = [0] * n_nodes
        tot_out = [0] * n_nodes
        for s, t, v in zip(sources, targets, values):
            tot_out[s] += v
            tot_in[t] += v
        node_w = [max(tot_in[i], tot_out[i]) for i in range(n_nodes)]
        return node_w

    @staticmethod
    def _layout_column(node_ids, node_w, y0=0.02, y1=0.98, gap_px=20, fig_h_px=900):
        if not node_ids:
            return {}

        span = max(1e-9, (y1 - y0))
        n = len(node_ids)
        gap = gap_px / float(fig_h_px) 

        if n > 1:
            max_gap = span * 0.35 / (n - 1)
            gap = min(gap, max_gap)
        else:
            gap = 0.0

        total_gap = (n - 1) * gap
        available = span - total_gap
        if available <= 1e-9:
            gap = 0.0
            available = span

        total_w = sum(max(0, node_w[i]) for i in node_ids)

        if total_w <= 0:
            step = span / float(n + 1)
            return {nid: (y0 + step * (k + 1)) for k, nid in enumerate(node_ids)}

        y = y0
        pos = {}
        for nid in node_ids:
            w = max(0, node_w[nid])
            h = (w / total_w) * available
            pos[nid] = y + h / 2.0
            y += h + gap
        return pos

    @staticmethod
    def _build_active_mapping(keep_order, sources, targets):
        used = set(sources) | set(targets) | {0}
        active = [i for i in keep_order if i in used]
        remap = {old: new for new, old in enumerate(active)}
        return active, remap

    @classmethod
    def generate(
        cls,
        json_results: list,
        filtering_stats_path: Path,
        run_name: str,
        output_folder: Path,
        drop_zero_nodes: bool = True,
        fig_width: int = 1800,
        fig_height: int = 900, 
        node_pad_px: int = 20,
        node_thickness_px: int = 20
    ):
        if not PLOTLY_AVAILABLE:
            return None, None
        if not filtering_stats_path.exists():
            return None, None

        output_folder.mkdir(parents=True, exist_ok=True)

        try:
            with open(filtering_stats_path, "r", encoding="utf-8") as f:
                stats = json.load(f)
        except Exception:
            return None, None

        v_auto = int(stats.get("auto_accepted", 0))

        taxon_to_band = {}
        csv_path = filtering_stats_path.parent / "02_rescue_candidates.csv"
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        raw_name = row.get("taxon") or row.get("taxa_name") or row.get("query_name")
                        if not raw_name:
                            continue
                        key = cls._clean_key(raw_name)
                        raw_band = row.get("bands") or row.get("initial_band") or row.get("band") or ""
                        band_str = str(raw_band).lower()

                        if "grey" in band_str:
                            taxon_to_band[key] = 2
                        elif "flag" in band_str:
                            taxon_to_band[key] = 3
                        elif "not" in band_str:
                            taxon_to_band[key] = 4
            except Exception:
                pass

        # --- 3) Costruzione flussi ---
        origin_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        final_counts = {5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
        l1_to_l2 = {} 

        auto_assigned = 0

        for item in (json_results or []):
            name = item.get("query_name")
            status = (item.get("status") or "no_correspondence").lower().strip()
            key = cls._clean_key(name)

            origin = taxon_to_band.get(key, None)
            if origin is None:
                if auto_assigned < v_auto:
                    origin = 1
                    auto_assigned += 1
                else:
                    origin = 2

            dest = cls.STATUS_MAP.get(status, 9)
            origin_counts[origin] = origin_counts.get(origin, 0) + 1
            final_counts[dest] = final_counts.get(dest, 0) + 1
            pair = (origin, dest)
            l1_to_l2[pair] = l1_to_l2.get(pair, 0) + 1

        sources = []
        targets = []
        values = []

        for origin in [1, 2, 3, 4]:
            v = origin_counts.get(origin, 0)
            if v > 0:
                sources.append(0)
                targets.append(origin)
                values.append(v)

        for (src, tgt), v in l1_to_l2.items():
            if v > 0:
                sources.append(src)
                targets.append(tgt)
                values.append(v)

        if not values:
            return None, None

        # --- 4) Layout Nodes ---
        keep_order = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

        if drop_zero_nodes:
            active, remap = cls._build_active_mapping(keep_order, sources, targets)
            sources = [remap[s] for s in sources]
            targets = [remap[t] for t in targets]

            labels = [cls.NODES_DEF[i]["label"] for i in active]
            colors = [cls.NODES_DEF[i]["color"] for i in active]

            active_set = set(active)
            mid_old = [1, 2, 3, 4]
            fin_old = [5, 6, 7, 8, 9]
            mid_nodes = [remap[i] for i in mid_old if i in active_set]
            fin_nodes = [remap[i] for i in fin_old if i in active_set]
            left_node = remap[0]
            n_nodes = len(active)
        else:
            labels = [n["label"] for n in cls.NODES_DEF]
            colors = [n["color"] for n in cls.NODES_DEF]
            mid_nodes = [1, 2, 3, 4]
            fin_nodes = [5, 6, 7, 8, 9]
            left_node = 0
            n_nodes = len(cls.NODES_DEF)

        node_w = cls._node_weights_from_links(n_nodes, sources, targets, values)
        mid_y = cls._layout_column(mid_nodes, node_w, gap_px=node_pad_px, fig_h_px=fig_height)
        fin_y = cls._layout_column(fin_nodes, node_w, gap_px=node_pad_px, fig_h_px=fig_height)

        x_pos = [0.0] * n_nodes
        y_pos = [0.5] * n_nodes

        x_pos[left_node] = 0.01 
        
        for nid in mid_nodes:
            x_pos[nid] = 0.5  
            y_pos[nid] = mid_y.get(nid, 0.5)

        for nid in fin_nodes:
            x_pos[nid] = 0.99 
            y_pos[nid] = fin_y.get(nid, 0.5)

        fig = go.Figure(data=[go.Sankey(
            arrangement="fixed",
            node=dict(
                pad=node_pad_px,
                thickness=node_thickness_px,
                line=dict(color="black", width=0.5),
                label=labels,
                color=colors,
                x=x_pos,
                y=y_pos
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color="rgba(180, 180, 180, 0.3)"
            )
        )])

        fig.update_layout(
            font_size=14, 
            width=fig_width,  
            height=fig_height,
            margin=dict(l=10, r=10, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        html_file = output_folder / "flow_analysis.html"
        fig.write_html(str(html_file))

        png_file = output_folder / "flow_analysis.png"
        try:
            fig.write_image(str(png_file), scale=2, width=fig_width, height=fig_height)
        except Exception:
            png_file = None

        return html_file, png_file
