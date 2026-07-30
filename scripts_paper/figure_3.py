import pickle
import pathlib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import (
    COLOR_PALETTE,
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_STEEL,
    REGION_DISPLAY_NAMES,
    RUN_STEEL,
    AGG_REGIONS,
    AGG_REGION_ORDER,
    AGG_COLOR_PALETTE,
)
import os

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

DIRECTORY = PATH_STEEL
TRADE_NAME = "steel"
RUN = RUN_STEEL
X_RANGE = [2000, 2100]
X_TICKS = [2000, 2050, 2100]
LINE_WIDTH_SCALE = 0.9
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 2 * LINE_WIDTH_SCALE
SYMBOL_CYCLE = [
    "circle",
    "square",
    "diamond",
    "triangle-up",
    "cross",
    "x",
    "triangle-down",
    "pentagon",
]


def _get_column_name(df, target_name: str) -> str:
    for column in df.columns:
        if str(column).strip().lower() == target_name.lower():
            return column
    raise KeyError(f"Could not find column '{target_name}' in dataframe columns {list(df.columns)}")


def _map_region(region: str) -> str:
    return AGG_REGIONS.get(str(region), str(region))


def _aggregate_region_timeseries(df, time_col: str, region_col: str, value_col: str):
    aggregated = df.copy()
    aggregated[region_col] = aggregated[region_col].map(_map_region)
    return (
        aggregated.groupby([time_col, region_col], as_index=False)[value_col]
        .sum()
        .sort_values([region_col, time_col])
    )


def _ordered_regions(present_regions, reverse: bool = False):
    ordered_from_config = AGG_REGION_ORDER[::-1] if reverse else AGG_REGION_ORDER
    present = [str(region) for region in present_regions]
    configured = [region for region in ordered_from_config if region in present]
    remainder = sorted(region for region in present if region not in set(AGG_REGION_ORDER))
    if reverse:
        remainder = remainder[::-1]
    return configured + remainder


def _build_figure(data_imports, data_exports, data_fabrication, data_forming) -> go.Figure:
    time_col = _get_column_name(data_imports, "Time")
    region_col = _get_column_name(data_imports, "Region")
    value_col = _get_column_name(data_imports, "value")

    data_imports = _aggregate_region_timeseries(data_imports, time_col, region_col, value_col)
    data_exports = _aggregate_region_timeseries(data_exports, time_col, region_col, value_col)
    data_fabrication = _aggregate_region_timeseries(
        data_fabrication, time_col, region_col, value_col
    )
    data_forming = _aggregate_region_timeseries(data_forming, time_col, region_col, value_col)

    # Relative trade shares: imports/fabrication and exports/forming (both region-time matched).
    imports_share = data_imports.merge(
        data_fabrication,
        on=[time_col, region_col],
        suffixes=("_imports", "_fabrication"),
    )
    imports_share[value_col] = (
        imports_share[f"{value_col}_imports"] / imports_share[f"{value_col}_fabrication"]
    )
    imports_share.loc[imports_share[f"{value_col}_fabrication"] == 0, value_col] = None
    imports_share = imports_share[[time_col, region_col, value_col]]

    exports_share = data_exports.merge(
        data_forming,
        on=[time_col, region_col],
        suffixes=("_exports", "_forming"),
    )
    exports_share[value_col] = (
        exports_share[f"{value_col}_exports"] / exports_share[f"{value_col}_forming"]
    )
    exports_share.loc[exports_share[f"{value_col}_forming"] == 0, value_col] = None
    exports_share = exports_share[[time_col, region_col, value_col]]

    region_codes = _ordered_regions(
        sorted(
            set(data_imports[region_col])
            .union(set(data_exports[region_col]))
            .union(set(data_fabrication[region_col]))
            .union(set(data_forming[region_col]))
        ),
        reverse=True,
    )

    region_colors = {}
    region_symbols = {}

    def _get_region_color(region: str) -> str:
        if region not in region_colors:
            region_colors[region] = AGG_COLOR_PALETTE.get(
                region, COLOR_PALETTE[len(region_colors) % len(COLOR_PALETTE)]
            )
        return region_colors[region]

    def _get_region_symbol(region: str) -> str:
        if region not in region_symbols:
            region_symbols[region] = SYMBOL_CYCLE[len(region_symbols) % len(SYMBOL_CYCLE)]
        return region_symbols[region]

    fig = make_subplots(
        rows=2,
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.06,
        horizontal_spacing=0.12,
    )

    def _add_region_traces(df, row: int, col: int, include_legend: bool = False):
        for region_code in region_codes:
            region_df = df[df[region_col] == region_code].sort_values(time_col)
            if region_df.empty:
                continue

            legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
            region_color = _get_region_color(region_code)
            region_symbol = _get_region_symbol(region_code)

            fig.add_trace(
                go.Scatter(
                    x=region_df[time_col],
                    y=region_df[value_col],
                    mode="lines",
                    name=legend_label,
                    legendgroup=region_code,
                    showlegend=False,
                    line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
                ),
                row=row,
                col=col,
            )

            marker_df = region_df.iloc[::20]
            fig.add_trace(
                go.Scatter(
                    x=marker_df[time_col],
                    y=marker_df[value_col],
                    mode="markers",
                    name=legend_label,
                    legendgroup=region_code,
                    showlegend=False,
                    marker={"color": region_color, "size": 9, "symbol": region_symbol},
                ),
                row=row,
                col=col,
            )

            if include_legend:
                fig.add_trace(
                    go.Scatter(
                        x=[1700, 1700],
                        y=[0, 0.1],
                        mode="lines+markers",
                        name=legend_label,
                        legendgroup=region_code,
                        showlegend=True,
                        marker={"color": region_color, "size": 9, "symbol": region_symbol},
                        line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
                    ),
                    row=row,
                    col=col,
                )

    _add_region_traces(data_exports, row=1, col=1, include_legend=True)
    _add_region_traces(data_imports, row=2, col=1, include_legend=False)
    _add_region_traces(exports_share, row=1, col=2, include_legend=False)
    _add_region_traces(imports_share, row=2, col=2, include_legend=False)

    # Add vertical historical-year cutoff to all subplots.
    for row in (1, 2):
        for col in (1, 2):
            fig.add_vline(
                x=LAST_HISTORICAL_YEAR_STEEL,
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
        width=750,
        height=500,
        legend={"y": 0.5, "yanchor": "middle"},
        margin={"t": 50, "b": 50, "l": 50, "r": 50},
    )
    return fig


pickle_path = DIRECTORY / f"{RUN}.pickle"
with pickle_path.open("rb") as file_handle:
    mfa = pickle.load(file_handle).future_mfa

data_imports = (mfa.trade_set[TRADE_NAME].imports.sum_to(("t", "r")) / 1e6).to_df().reset_index()
data_exports = (mfa.trade_set[TRADE_NAME].exports.sum_to(("t", "r")) / 1e6).to_df().reset_index()
data_fabrication = (
    (mfa.flows["ip_market => fabrication"].sum_to(("t", "r")) / 1e6).to_df().reset_index()
)
data_forming = (mfa.flows["forming => ip_market"].sum_to(("t", "r")) / 1e6).to_df().reset_index()
fig = _build_figure(data_imports, data_exports, data_fabrication, data_forming)
output_path = pathlib.Path(__file__).with_name("figure_3.png")
fig.write_image(
    output_path,
    width=fig.layout.width,
    height=fig.layout.height,
    scale=3,
)
fig.show()
