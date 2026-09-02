import argparse
import os

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import scripts_paper._utils as _utils
from scripts_paper._constants import figure_output_path, get_material_config

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

X_RANGE = [2000, 2100]
X_TICKS = [2000, 2050, 2100]
LINE_WIDTH_SCALE = 1.5
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 2 * LINE_WIDTH_SCALE
MAXIMUM_LEGENDTEXT_BRIGHTNESS = 0.4
LEGEND_FONT_SIZE = 13


def _build_figure(config, aggregate_regions: bool) -> go.Figure:
    mfa = _utils.load_future_mfa(config.material)

    def _load_flow(flow_name: str):
        df = (mfa.flows[flow_name].sum_to(("t", "r")) / 1e6).to_df().reset_index()
        time_col = _utils.get_column_name(df, "Time")
        region_col = _utils.get_column_name(df, "Region")
        value_col = _utils.get_column_name(df, "value")
        df = _utils.aggregate_region_timeseries(
            df,
            time_col,
            region_col,
            value_col,
            aggregate_regions=aggregate_regions,
        )
        return df, time_col, region_col, value_col

    data_imports, time_col, region_col, value_col = _load_flow(config.trade_imports_flow_name)
    data_exports, _, _, _ = _load_flow(config.trade_exports_flow_name)
    data_demand, _, _, _ = _load_flow(config.trade_demand_flow_name)
    data_supply, _, _, _ = _load_flow(config.trade_supply_flow_name)

    imports_share = data_imports.merge(
        data_demand,
        on=[time_col, region_col],
        suffixes=("_imports", "_demand"),
    )
    imports_share[value_col] = (
        imports_share[f"{value_col}_imports"] / imports_share[f"{value_col}_demand"]
    )
    imports_share.loc[imports_share[f"{value_col}_demand"] == 0, value_col] = None
    imports_share = imports_share[[time_col, region_col, value_col]]

    exports_share = data_exports.merge(
        data_supply,
        on=[time_col, region_col],
        suffixes=("_exports", "_supply"),
    )
    exports_share[value_col] = (
        exports_share[f"{value_col}_exports"] / exports_share[f"{value_col}_supply"]
    )
    exports_share.loc[exports_share[f"{value_col}_supply"] == 0, value_col] = None
    exports_share = exports_share[[time_col, region_col, value_col]]

    region_codes = _utils.ordered_regions(
        sorted(
            set(data_imports[region_col])
            .union(set(data_exports[region_col]))
            .union(set(data_demand[region_col]))
            .union(set(data_supply[region_col]))
        ),
        reverse=True,
        aggregate_regions=aggregate_regions,
    )

    region_colors = {}

    def _legend_name(label: str, color: str) -> str:
        return _utils.legend_name(label, color, MAXIMUM_LEGENDTEXT_BRIGHTNESS)

    fig = make_subplots(
        rows=2,
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.06,
        horizontal_spacing=0.12,
    )

    seen_regions: set = set()

    def _add_region_traces(df, row: int, col: int, include_legend: bool = False):
        for region_code in region_codes:
            region_df = df[df[region_col] == region_code].sort_values(time_col)
            if region_df.empty:
                continue

            legend_label = _utils.get_region_label(region_code, aggregate_regions=aggregate_regions)
            region_color = _utils.get_region_color(
                region_code, region_colors, aggregate_regions=aggregate_regions
            )
            show_legend = include_legend and region_code not in seen_regions

            fig.add_trace(
                go.Scatter(
                    x=region_df[time_col],
                    y=region_df[value_col],
                    mode="lines",
                    name=_legend_name(legend_label, region_color),
                    legendgroup=region_code,
                    showlegend=show_legend,
                    line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
                ),
                row=row,
                col=col,
            )
            if show_legend:
                seen_regions.add(region_code)

    _add_region_traces(data_exports, row=1, col=1, include_legend=True)
    _add_region_traces(data_imports, row=2, col=1, include_legend=False)
    _add_region_traces(exports_share, row=1, col=2, include_legend=False)
    _add_region_traces(imports_share, row=2, col=2, include_legend=False)

    for row in (1, 2):
        for col in (1, 2):
            fig.add_vline(
                x=config.last_historical_year,
                line_dash="dash",
                line_color="black",
                line_width=LINE_WIDTH_VLINE,
                row=row,
                col=col,
            )

    fig.update_yaxes(title_text="Exports (Mt)", title_standoff=4, row=1, col=1)
    fig.update_yaxes(
        title_text="Imports (Mt)", title_standoff=4, autorange="reversed", row=2, col=1
    )
    fig.update_yaxes(title_text="Export share", title_standoff=4, row=1, col=2)
    fig.update_yaxes(
        title_text="Import share",
        title_standoff=4,
        autorange="reversed",
        row=2,
        col=2,
    )

    for col in (1, 2):
        for row in (1, 2):
            fig.update_xaxes(
                range=X_RANGE,
                tickmode="array",
                tickvals=X_TICKS,
                row=row,
                col=col,
            )
        fig.update_xaxes(title_text="Year", title_standoff=4, row=2, col=col)

    fig.update_layout(
        template="plotly_white",
        width=750 if aggregate_regions else 900,
        height=500,
        legend={
            "y": 0.5,
            "yanchor": "middle",
            "font": {"size": LEGEND_FONT_SIZE},
            "bordercolor": "black",
            "borderwidth": 1,
        },
        margin={"t": 80, "b": 50, "l": 50, "r": 50},
    )
    return fig


def main(material: str = "steel", use_h12: bool = False, show: bool = True):
    config = get_material_config(material)
    fig = _build_figure(config, aggregate_regions=not use_h12)
    output_path = figure_output_path(
        f"figure_10_{config.material}_{_utils.region_mode_suffix(use_h12)}.png"
    )
    fig.write_image(
        output_path,
        width=fig.layout.width,
        height=fig.layout.height,
        scale=3,
    )
    if show:
        fig.show()
    return fig


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", choices=["plastics", "steel", "cement"], default="steel")
    parser.add_argument("--h12", action="store_true")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    main(material=args.material, use_h12=args.h12, show=not args.no_show)
