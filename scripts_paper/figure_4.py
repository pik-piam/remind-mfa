import pickle
import flodym as fd
import pathlib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import (
    COLOR_PALETTE,
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_STEEL,
    RUN_STEEL,
    RUN_STEEL_SSP1,
    RUN_STEEL_SSP1_LD,
    AGG_REGIONS,
    AGG_REGION_ORDER,
    CMAP_5,
)
import os

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

DIRECTORY = PATH_STEEL
FLOW_NAME = "forming => ip_market"
RUNS = [RUN_STEEL, RUN_STEEL_SSP1, RUN_STEEL_SSP1_LD]
LABELS = ["SSP2", "SSP1-drivers", "SSP1-CE"]
X_RANGE = [2000, 2100]
X_TICKS = [2000, 2050, 2100]
SCENARIO_COLORS = CMAP_5[::-2]
RUN_COLOR_MAP = {label: SCENARIO_COLORS[i] for i, label in enumerate(LABELS)}


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

    group_cols = [time_col, region_col]
    preserve_cols = [
        col for col in aggregated.columns if col not in {time_col, region_col, value_col}
    ]
    if preserve_cols:
        group_cols.extend(preserve_cols)

    return (
        aggregated.groupby(group_cols, as_index=False)[value_col]
        .sum()
        .sort_values(group_cols + [value_col])
    )


def _ordered_regions(present_regions, reverse: bool = False):
    ordered_from_config = AGG_REGION_ORDER[::-1] if reverse else AGG_REGION_ORDER
    present = [str(region) for region in present_regions]
    configured = [region for region in ordered_from_config if region in present]
    remainder = sorted(region for region in present if region not in set(AGG_REGION_ORDER))
    if reverse:
        remainder = remainder[::-1]
    return configured + remainder


def _build_comparison_figure(array: fd.FlodymArray, subplot_dim: str | None = None) -> go.Figure:
    data = array.sum_to(("t", "X", subplot_dim or "r")).to_df().reset_index()
    data_glob = array.sum_to(("t", "X")).to_df().reset_index()
    time_col = _get_column_name(data, "Time")
    region_col = _get_column_name(data, "Region")
    value_col = _get_column_name(data, "value")

    scenario_candidates = [
        col for col in data.columns if col not in {time_col, region_col, value_col}
    ]
    if len(scenario_candidates) != 1:
        raise KeyError(
            f"Expected exactly one scenario dimension column, found {scenario_candidates}"
        )
    run_col = scenario_candidates[0]

    data[region_col] = data[region_col].astype(str)
    data = _aggregate_region_timeseries(data, time_col, region_col, value_col)

    data_glob = data_glob.rename(columns={_get_column_name(data_glob, "value"): value_col})
    world_panel = (
        data_glob.groupby([time_col, run_col], as_index=False)[value_col]
        .sum()
        .sort_values([run_col, time_col])
    )

    present_regions = sorted(set(data[region_col]))
    region_panels = _ordered_regions(present_regions, reverse=True)[:5]
    subplot_titles = ["<b>World</b>"] + [region for region in region_panels]

    n_cols = 3
    n_rows = 2

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.10,
        vertical_spacing=0.22,
    )

    def _add_panel_traces(panel_df, panel_row: int, panel_col: int, legend: bool):
        # Add traces in explicit scenario order so legend order is stable.
        ordered_runs = [label for label in LABELS if label in set(panel_df[run_col].astype(str))]
        remaining_runs = [
            run
            for run in panel_df[run_col].astype(str).unique().tolist()
            if run not in set(ordered_runs)
        ]
        run_legend_rank = {label: i for i, label in enumerate(LABELS)}

        # Draw runs in reverse order to flip line layering (z-order).
        for run_label in list(reversed(ordered_runs)) + remaining_runs:
            run_df = panel_df[panel_df[run_col].astype(str) == str(run_label)].sort_values(time_col)
            if run_df.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=run_df[time_col],
                    y=run_df[value_col],
                    mode="lines",
                    name=str(run_label),
                    legendgroup=str(run_label),
                    showlegend=legend,
                    legendrank=run_legend_rank.get(str(run_label), len(LABELS) + 100),
                    line={"color": RUN_COLOR_MAP.get(str(run_label))},
                ),
                row=panel_row,
                col=panel_col,
            )

    _add_panel_traces(world_panel, panel_row=1, panel_col=1, legend=True)

    for i, region_code in enumerate(region_panels, start=1):
        if i == 1:
            row, col = 1, 2
        elif i == 2:
            row, col = 1, 3
        elif i == 3:
            row, col = 2, 1
        elif i == 4:
            row, col = 2, 2
        else:
            row, col = 2, 3

        region_df = data[data[region_col] == region_code]
        region_panel = (
            region_df.groupby([time_col, run_col], as_index=False)[value_col]
            .sum()
            .sort_values([run_col, time_col])
        )
        _add_panel_traces(region_panel, panel_row=row, panel_col=col, legend=False)

        fig.add_vline(
            x=LAST_HISTORICAL_YEAR_STEEL,
            line_dash="dash",
            line_color="black",
            row=row,
            col=col,
        )

    fig.add_vline(
        x=LAST_HISTORICAL_YEAR_STEEL,
        line_dash="dash",
        line_color="black",
        row=1,
        col=1,
    )

    fig.add_shape(
        type="rect",
        xref="x domain",
        yref="y domain",
        x0=-0.2,
        x1=1.2,
        y0=-0.3,
        y1=1.2,
        row=1,
        col=1,
        line={"color": "black", "width": 1.2},
        fillcolor="rgba(0,0,0,0)",
    )

    fig.add_annotation(
        x=-0.08,
        y=0.5,
        xref="x domain",
        yref="y domain",
        text="Production (Gt)",
        showarrow=False,
        xanchor="right",
        yanchor="middle",
        font={"size": 14},
        textangle=270,
        xshift=-35,
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=-0.08,
        y=0.5,
        xref="x domain",
        yref="y domain",
        text="Production (Gt)",
        showarrow=False,
        xanchor="right",
        yanchor="middle",
        font={"size": 14},
        textangle=270,
        xshift=-35,
        row=2,
        col=1,
    )

    fig.for_each_xaxis(
        lambda axis: axis.update(
            title_text="Year", title_standoff=4, range=X_RANGE, tickmode="array", tickvals=X_TICKS
        )
    )
    fig.for_each_yaxis(lambda axis: axis.update(title_text="", showgrid=True))
    fig.update_layout(
        template="plotly_white",
        width=900,
        height=600,
        margin={"t": 120, "b": 70, "l": 120, "r": 70},
        legend={
            "x": 0.5,
            "y": 1.12,
            "xanchor": "center",
            "yanchor": "bottom",
            "orientation": "h",
            "traceorder": "normal",
            "bgcolor": "white",
            "bordercolor": "black",
            "borderwidth": 1,
        },
    )
    return fig


run_file_names = [f"{run_name}.pickle" for run_name in RUNS]
run_file_paths = [DIRECTORY / file_name for file_name in run_file_names]
if not LABELS:
    LABELS = [pathlib.Path(f).stem for f in run_file_names]

if RUNS is not None and len(RUNS) != len(run_file_names):
    raise ValueError("run_names must have the same length as selected files")

new_dim = fd.Dimension(letter="X", name="Run", items=LABELS)

mfas = []
for pickle_path in run_file_paths:
    with pickle_path.open("rb") as file_handle:
        mfas.append(pickle.load(file_handle).future_mfa)

arrays = [mfa.flows[FLOW_NAME] for mfa in mfas]
comparison_array = fd.flodym_array_stack(arrays, dimension=new_dim) / 1e9

fig = _build_comparison_figure(comparison_array, subplot_dim="r")
output_path = pathlib.Path(__file__).with_name("figure_4.png")
fig.write_image(
    output_path,
    width=fig.layout.width,
    height=fig.layout.height,
    scale=3,
)
fig.show()
