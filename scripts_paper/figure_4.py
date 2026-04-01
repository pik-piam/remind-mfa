import pickle
import flodym as fd
import pathlib
import math
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import (
    COLOR_PALETTE,
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_STEEL,
    REGION_DISPLAY_NAMES,
    RUN_STEEL,
    RUN_STEEL_SSP1,
    RUN_STEEL_SSP1_LD,
)

DIRECTORY = PATH_STEEL
FLOW_NAME = "forming => ip_market"
RUNS = [RUN_STEEL, RUN_STEEL_SSP1, RUN_STEEL_SSP1_LD]
# RUNS = None
LABELS = ["SSP2", "SSP1", "SSP1_LD"]
X_RANGE = [2010, 2100]
SCENARIO_COLORS = COLOR_PALETTE[::3]
RUN_COLOR_MAP = {label: SCENARIO_COLORS[i] for i, label in enumerate(LABELS)}


def _get_column_name(df, target_name: str) -> str:
    for column in df.columns:
        if str(column).strip().lower() == target_name.lower():
            return column
    raise KeyError(f"Could not find column '{target_name}' in dataframe columns {list(df.columns)}")


def _build_comparison_figure(array: fd.FlodymArray, subplot_dim: str | None = None) -> go.Figure:
    if subplot_dim is None:
        data = array.sum_to(("t", "X")).to_df().reset_index()
        time_col = _get_column_name(data, "Time")
        run_col = _get_column_name(data, "Run")
        value_col = _get_column_name(data, "value")

        fig = make_subplots(rows=1, cols=1)
        for run_label, run_df in data.groupby(run_col):
            run_df = run_df.sort_values(time_col)
            fig.add_trace(
                go.Scatter(
                    x=run_df[time_col],
                    y=run_df[value_col],
                    mode="lines",
                    name=str(run_label),
                    legendgroup=str(run_label),
                    line={"color": RUN_COLOR_MAP.get(str(run_label))},
                ),
                row=1,
                col=1,
            )
        fig.add_vline(
            x=LAST_HISTORICAL_YEAR_STEEL, line_dash="dash", line_color="black", row=1, col=1
        )
    else:
        data = array.sum_to(("t", "X", subplot_dim)).to_df().reset_index()
        time_col = _get_column_name(data, "Time")
        run_col = _get_column_name(data, "Run")
        region_col = _get_column_name(data, "Region")
        value_col = _get_column_name(data, "value")

        data[region_col] = data[region_col].astype(str)
        region_codes = sorted(
            dict.fromkeys(data[region_col]),
            key=lambda code: REGION_DISPLAY_NAMES.get(code, code),
        )
        n_cols = math.ceil(math.sqrt(len(region_codes)))
        n_rows = math.ceil(len(region_codes) / n_cols)
        subplot_titles = [REGION_DISPLAY_NAMES.get(code, code) for code in region_codes]

        fig = make_subplots(
            rows=n_rows,
            cols=n_cols,
            subplot_titles=subplot_titles,
            horizontal_spacing=0.08,
            vertical_spacing=0.20,
        )

        for i_region, region_code in enumerate(region_codes):
            row = i_region // n_cols + 1
            col = i_region % n_cols + 1
            region_df = data[data[region_col] == region_code]

            for run_label, run_df in region_df.groupby(run_col):
                run_df = run_df.sort_values(time_col)
                fig.add_trace(
                    go.Scatter(
                        x=run_df[time_col],
                        y=run_df[value_col],
                        mode="lines",
                        name=str(run_label),
                        legendgroup=str(run_label),
                        showlegend=i_region == 0,
                        line={"color": RUN_COLOR_MAP.get(str(run_label))},
                    ),
                    row=row,
                    col=col,
                )

            fig.add_vline(
                x=LAST_HISTORICAL_YEAR_STEEL,
                line_dash="dash",
                line_color="black",
                row=row,
                col=col,
            )

    fig.for_each_xaxis(lambda axis: axis.update(title_text="Year", title_standoff=4, range=X_RANGE))
    fig.for_each_yaxis(lambda axis: axis.update(title_text="Production [Mt]", title_standoff=4))
    fig.update_layout(template="plotly_white")
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
comparison_array = fd.flodym_array_stack(arrays, dimension=new_dim) / 1e6

fig = _build_comparison_figure(comparison_array, subplot_dim="r")
fig.show()

fig = _build_comparison_figure(comparison_array, subplot_dim=None)
fig.show()
