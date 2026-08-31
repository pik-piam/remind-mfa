import pickle
import pathlib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scripts_paper._constants import (
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_STEEL,
    REGION_DISPLAY_NAMES,
    RUN_STEEL,
)
import os
import scripts_paper._utils as _utils
from scripts_paper._utils import (
    get_column_name as _get_column_name,
    aggregate_region_timeseries as _aggregate_region_timeseries,
    ordered_regions as _ordered_regions,
)

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

DIRECTORY = PATH_STEEL
TRADE_NAME = "steel"
RUN = RUN_STEEL
X_RANGE = [2000, 2100]
X_TICKS = [2000, 2050, 2100]
LINE_WIDTH_SCALE = 1.5
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 2 * LINE_WIDTH_SCALE
MAXIMUM_LEGENDTEXT_BRIGHTNESS = 0.4
LEGEND_FONT_SIZE = 13


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

    def _get_region_color(region: str) -> str:
        return _utils.get_region_color(region, region_colors)

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

            legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
            region_color = _get_region_color(region_code)
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
        legend={
            "y": 0.5,
            "yanchor": "middle",
            "font": {"size": LEGEND_FONT_SIZE},
            "bordercolor": "black",
            "borderwidth": 1,
        },
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
