import plotly.graph_objects as go
import pathlib

show_all = [
    "Local<br>demand",
    "Imports",
    "Exports",
    "Local<br>production",
]
stages_show = {
    "historical": [3],
    "growing": [0, 1, 3],
    "shrinking": [0, 1, 3],
}
demand_cases = ["historical", "growing", "shrinking"]
show_labels = False

for demand_case, stage in ((d, s) for d, sv in stages_show.items() for s in sv):

    show = show_all[0 : stage + 1]
    # Simple illustrative trade balance around a market node.

    if demand_case == "historical":
        production = 1
        imports = 2
        exports = 1
        demand = 2
    elif demand_case == "growing":
        production = 6.56155
        imports = 4
        exports = 2.56155
        demand = 8
    elif demand_case == "shrinking":
        production = 1
        imports = 0.5
        exports = 1
        demand = 0.5

    height_factor = production + imports

    # ── Appearance tables ────────────────────────────────────────────────────────
    # Internal node IDs are kept separate from visible labels so helper nodes can
    # stay permanently invisible.
    _NODES = [
        "_IMPORTS_OUTER",
        "Imports",
        "_PRODUCTION_OUTER",
        "Local<br>production",
        "_MARKET",
        "Exports",
        "_EXPORTS_OUTER",
        "Local<br>demand",
        "_DEMAND_OUTER",
    ]
    _NODE_LABELS_FULL = {
        "_IMPORTS_OUTER": "",
        "Imports": "Imports",
        "_PRODUCTION_OUTER": "",
        "Local<br>production": "Local<br>production",
        "_MARKET": "",
        "Exports": "Exports",
        "_EXPORTS_OUTER": "",
        "Local<br>demand": "Local<br>demand",
        "_DEMAND_OUTER": "",
    }
    _NODE_COLORS_FULL = {
        "_IMPORTS_OUTER": "white",
        "Imports": "#888888",
        "_PRODUCTION_OUTER": "white",
        "Local<br>production": "#888888",
        "_MARKET": "#888888",
        "Exports": "#888888",
        "_EXPORTS_OUTER": "white",
        "Local<br>demand": "#888888",
        "_DEMAND_OUTER": "white",
    }
    # Link ownership controls visibility by stage.
    _LINK_NODES = [
        "_IMPORTS_OUTER",
        "Imports",
        "Local<br>production",
        "Local<br>production",
        "Exports",
        "Exports",
        "Local<br>demand",
        "Local<br>demand",
    ]
    _LINK_COLORS_FULL = [
        "white",  # Outer helper → Imports
        "rgba(140, 184, 140, 0.65)",  # Imports  → Market
        "rgba(140, 168, 192, 0.65)",  # Outer helper → Local production
        "rgba(140, 168, 192, 0.65)",  # Local production → Market
        "rgba(140, 184, 140, 0.65)",  # Market → Exports
        "white",  # Exports → Outer helper
        "rgba(140, 168, 192, 0.65)",  # Market → Local demand
        "rgba(140, 168, 192, 0.65)",  # Local demand → Outer helper
    ]

    _always_visible_nodes = {
        "_IMPORTS_OUTER",
        "_MARKET",
        "_PRODUCTION_OUTER",
        "_EXPORTS_OUTER",
        "_DEMAND_OUTER",
    }
    _visible = set(show) | _always_visible_nodes
    node_labels = [_NODE_LABELS_FULL[n] if show_labels and n in _visible else "" for n in _NODES]
    node_colors = [_NODE_COLORS_FULL[n] if n in _visible else "white" for n in _NODES]
    # Fixed node placement:
    # - Imports/Exports on top
    # - Local production/demand on bottom at same x as Imports/Exports
    # - Invisible helper nodes further out; production-side helper moves to top
    #   when local production is not shown to avoid a stray bottom-left anchor.
    y_top = 0.18
    y_bottom = 0.82
    node_x = [0.02, 0.26, 0.02, 0.26, 0.50, 0.74, 0.98, 0.74, 0.98]
    node_y = [y_top, y_top, y_bottom, y_bottom, 0.50, y_top, y_top, y_bottom, y_bottom]
    link_colors = [
        c if i in {0, 5} or _LINK_NODES[i] in _visible else "rgba(255,255,255,0)"
        for i, c in enumerate(_LINK_COLORS_FULL)
    ]

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                node={
                    "label": node_labels,
                    "pad": 20,
                    "thickness": 24,
                    "color": node_colors,
                    "x": node_x,
                    "y": node_y,
                    "line": {"width": 0},
                },
                link={
                    "source": [0, 1, 2, 3, 4, 5, 4, 7],
                    "target": [1, 4, 3, 4, 5, 6, 7, 8],
                    "value": [
                        imports,
                        imports,
                        production,
                        production,
                        exports,
                        exports,
                        demand,
                        demand,
                    ],
                    "color": link_colors,
                },
                textfont={
                    "size": 16,
                    "color": "black",
                    "family": "Arial",
                    "weight": 700,
                    "shadow": "none",
                },
            )
        ]
    )

    fig.update_layout(
        font={"size": 16, "color": "black", "family": "Arial"},
        width=600,
        height=15 * height_factor + 200,
    )

    output_path = pathlib.Path(__file__).with_name(f"trade_{demand_case}_{stage}.png")
    fig.write_image(
        output_path,
        width=fig.layout.width,
        height=fig.layout.height,
        scale=3,
    )

    fig.show()
