import pickle
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import (
    COLOR_PALETTE,
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_STEEL,
    REGION_DISPLAY_NAMES,
    RUN_STEEL,
)

DIRECTORY = PATH_STEEL
TRADE_NAME = "steel"
RUN = RUN_STEEL
X_RANGE = [2010, 2100]


def _get_column_name(df, target_name: str) -> str:
    for column in df.columns:
        if str(column).strip().lower() == target_name.lower():
            return column
    raise KeyError(f"Could not find column '{target_name}' in dataframe columns {list(df.columns)}")


def _build_figure(data_imports, data_exports) -> go.Figure:
    time_col = _get_column_name(data_imports, "Time")
    region_col = _get_column_name(data_imports, "Region")
    value_col = _get_column_name(data_imports, "value")

    data_imports[region_col] = data_imports[region_col].astype(str)
    data_exports[region_col] = data_exports[region_col].astype(str)

    region_codes = sorted(
        dict.fromkeys(data_imports[region_col]),
        key=lambda code: REGION_DISPLAY_NAMES.get(code, code),
    )
    region_color_map = {
        region_code: COLOR_PALETTE[i % len(COLOR_PALETTE)]
        for i, region_code in enumerate(region_codes)
    }

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
    )

    # Add exports to upper subplot (row=1)
    for region_code in region_codes:
        region_df = data_exports[data_exports[region_col] == region_code].sort_values(time_col)
        fig.add_trace(
            go.Scatter(
                x=region_df[time_col],
                y=region_df[value_col],
                mode="lines",
                name=REGION_DISPLAY_NAMES.get(region_code, region_code),
                legendgroup=region_code,
                showlegend=True,
                line={"color": region_color_map[region_code]},
            ),
            row=1,
            col=1,
        )

    # Add imports to lower subplot (row=2) with inverted y-axis (0 on top)
    for region_code in region_codes:
        region_df = data_imports[data_imports[region_col] == region_code].sort_values(time_col)
        fig.add_trace(
            go.Scatter(
                x=region_df[time_col],
                y=region_df[value_col],
                mode="lines",
                name=REGION_DISPLAY_NAMES.get(region_code, region_code),
                legendgroup=region_code,
                showlegend=False,
                line={"color": region_color_map[region_code]},
            ),
            row=2,
            col=1,
        )

    # Add vertical line at historical year cutoff to both subplots
    fig.add_vline(x=LAST_HISTORICAL_YEAR_STEEL, line_dash="dash", line_color="black", row=1, col=1)
    fig.add_vline(x=LAST_HISTORICAL_YEAR_STEEL, line_dash="dash", line_color="black", row=2, col=1)

    # Upper subplot: exports
    fig.update_yaxes(
        title_text="Exports [Mt]",
        title_standoff=4,
        row=1,
        col=1,
    )

    # Lower subplot: imports with inverted y-axis (0 on top, positive numbers)
    fig.update_yaxes(
        title_text="Imports [Mt]",
        title_standoff=4,
        autorange="reversed",
        row=2,
        col=1,
    )

    # X-axis label only on lower subplot
    fig.update_xaxes(title_text="Year", title_standoff=4, range=X_RANGE, row=2, col=1)

    fig.update_layout(template="plotly_white")
    return fig


pickle_path = DIRECTORY / f"{RUN}.pickle"
with pickle_path.open("rb") as file_handle:
    mfa = pickle.load(file_handle).future_mfa

data_imports = (mfa.trade_set[TRADE_NAME].imports.sum_to(("t", "r")) / 1e6).to_df().reset_index()
data_exports = (mfa.trade_set[TRADE_NAME].exports.sum_to(("t", "r")) / 1e6).to_df().reset_index()
fig = _build_figure(data_imports, data_exports)
fig.show()
