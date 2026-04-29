import pickle
import math
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import (
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_STEEL,
    REGION_DISPLAY_NAMES,
    RUN_STEEL,
)


def _get_column_name(df, target_name: str) -> str:
    for column in df.columns:
        if str(column).strip().lower() == target_name.lower():
            return column
    raise KeyError(f"Could not find column '{target_name}' in dataframe columns {list(df.columns)}")


fig = make_subplots(
    rows=2,
    cols=1,
    vertical_spacing=0.17,
    subplot_titles=("a) Over GDP per capita", "b) Over time"),
)
extrapolated_region = REGION_DISPLAY_NAMES["JPN"]


pickle_path = PATH_STEEL / f"{RUN_STEEL}.pickle"
with pickle_path.open("rb") as file_handle:
    model = pickle.load(file_handle)
    mfa = model.future_mfa

stock = mfa.stocks["in_use"].stock.sum_to(("t", "r"))
stock_pc = stock / mfa.parameters["population"]
stock_pc = stock_pc[{"t": mfa.dims["h"]}].to_df().reset_index()
gdppc_hist = mfa.parameters["gdppc"][{"t": mfa.dims["h"]}].to_df().reset_index()

time_col_stock = _get_column_name(stock_pc, "Historic Time")
region_col_stock = _get_column_name(stock_pc, "Region")
value_col_stock = _get_column_name(stock_pc, "value")

time_col_gdppc_hist = _get_column_name(gdppc_hist, "Historic Time")
region_col_gdppc_hist = _get_column_name(gdppc_hist, "Region")
value_col_gdppc_hist = _get_column_name(gdppc_hist, "value")

stock_pc = stock_pc[stock_pc[time_col_stock] >= 1920].copy()
gdppc_hist = gdppc_hist[gdppc_hist[time_col_gdppc_hist] >= 1920].copy()

extrapolated_region_code = None

for region, region_df in stock_pc.groupby(region_col_stock):
    region_df = region_df.sort_values(time_col_stock)
    region_code = str(region)
    legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
    is_extrapolated_region = legend_label == extrapolated_region

    gdppc_region_df = gdppc_hist[gdppc_hist[region_col_gdppc_hist] == region].sort_values(
        time_col_gdppc_hist
    )
    hist_merged = region_df.merge(
        gdppc_region_df,
        left_on=[time_col_stock, region_col_stock],
        right_on=[time_col_gdppc_hist, region_col_gdppc_hist],
        suffixes=("_stock", "_gdppc"),
    )

    if is_extrapolated_region:
        extrapolated_region_code = region_code

    line_color = "black" if is_extrapolated_region else "#B0B0B0"
    line_width = 3 if is_extrapolated_region else 1.5
    trace_name = "Extrapolated region" if is_extrapolated_region else "Other regions"
    legend_group = (
        "historical_extrapolated_region" if is_extrapolated_region else "historical_other"
    )

    fig.add_trace(
        go.Scatter(
            x=hist_merged[f"{value_col_gdppc_hist}_gdppc"],
            y=hist_merged[f"{value_col_stock}_stock"],
            mode="lines",
            name=trace_name,
            legendgroup=legend_group,
            showlegend=False,
            line={"color": line_color, "width": line_width},
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=region_df[time_col_stock],
            y=region_df[value_col_stock],
            mode="lines",
            name=trace_name,
            legendgroup=legend_group,
            showlegend=False,
            line={"color": line_color, "width": line_width},
        ),
        row=2,
        col=1,
    )

if extrapolated_region_code is None:
    raise ValueError(f"Could not identify region '{extrapolated_region}' in historical stock data.")

stock_handler = model.stock_handler
sat_level = model.sector_specific_sat_level

if not hasattr(stock_handler, "pure_regression"):
    raise AttributeError(
        "The loaded pickle does not contain stock_handler.pure_regression. "
        "Please rerun the model with the updated stock_extrapolation code and regenerate the pickle."
    )


def _to_region_df(stock_pc_array):
    region_series = (stock_pc_array * sat_level).sum_to(("t", "r"))
    return region_series[{"r": extrapolated_region_code}].to_df().reset_index()


pure_df = _to_region_df(stock_handler.pure_regression)
fitted_df = _to_region_df(stock_handler.fitted_regression)
smoothed_df = _to_region_df(stock_handler.stocks_pc)
gdppc_full_df = mfa.parameters["gdppc"].to_df().reset_index()

time_col_extrap = _get_column_name(pure_df, "Time")
value_col_extrap = _get_column_name(pure_df, "value")
time_col_gdppc_full = _get_column_name(gdppc_full_df, "Time")
region_col_gdppc_full = _get_column_name(gdppc_full_df, "Region")
value_col_gdppc_full = _get_column_name(gdppc_full_df, "value")

extrapolated_region_gdppc_full_df = gdppc_full_df[
    gdppc_full_df[region_col_gdppc_full] == extrapolated_region_code
]
gdppc_1920_row = extrapolated_region_gdppc_full_df[
    extrapolated_region_gdppc_full_df[time_col_gdppc_full] == 1920
]
if gdppc_1920_row.empty:
    raise ValueError(
        f"Could not find GDP per capita value in 1920 for region '{extrapolated_region}'."
    )
gdppc_1920 = float(gdppc_1920_row[value_col_gdppc_full].iloc[0])
last_hist_gdppc_row = extrapolated_region_gdppc_full_df[
    extrapolated_region_gdppc_full_df[time_col_gdppc_full] == LAST_HISTORICAL_YEAR_STEEL
]
if last_hist_gdppc_row.empty:
    raise ValueError(
        "Could not find GDP per capita value at the last historical year "
        f"for region '{extrapolated_region}'."
    )
last_hist_gdppc = float(last_hist_gdppc_row[value_col_gdppc_full].iloc[0])

# Show common regression only from 1920 onward.
pure_df = pure_df[pure_df[time_col_extrap] >= 1920].copy()

# Show only future years for regional adaptation and transition smoothing.
fitted_df = fitted_df[fitted_df[time_col_extrap] >= LAST_HISTORICAL_YEAR_STEEL].copy()
smoothed_df = smoothed_df[smoothed_df[time_col_extrap] >= LAST_HISTORICAL_YEAR_STEEL].copy()


def _merge_extrap_with_gdppc(extrap_df):
    return extrap_df.merge(
        extrapolated_region_gdppc_full_df,
        left_on=time_col_extrap,
        right_on=time_col_gdppc_full,
        suffixes=("_stock", "_gdppc"),
    )


pure_gdppc_df = _merge_extrap_with_gdppc(pure_df)
fitted_gdppc_df = _merge_extrap_with_gdppc(fitted_df)
smoothed_gdppc_df = _merge_extrap_with_gdppc(smoothed_df)

fig.add_trace(
    go.Scatter(
        x=pure_gdppc_df[f"{value_col_gdppc_full}_gdppc"],
        y=pure_gdppc_df[f"{value_col_extrap}_stock"],
        mode="lines",
        name="Step 1: Common regression",
        legendgroup="pure_regression",
        showlegend=False,
        line={"color": "#1f77b4", "width": 3},
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=pure_df[time_col_extrap],
        y=pure_df[value_col_extrap],
        mode="lines",
        name="Step 1: Common regression",
        legendgroup="pure_regression",
        showlegend=False,
        line={"color": "#1f77b4", "width": 3},
    ),
    row=2,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=fitted_gdppc_df[f"{value_col_gdppc_full}_gdppc"],
        y=fitted_gdppc_df[f"{value_col_extrap}_stock"],
        mode="lines",
        name="Step 2: Regional adaptation",
        legendgroup="after_fit",
        showlegend=False,
        line={"color": "#ff7f0e", "width": 3},
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=fitted_df[time_col_extrap],
        y=fitted_df[value_col_extrap],
        mode="lines",
        name="Step 2: Regional adaptation",
        legendgroup="after_fit",
        showlegend=False,
        line={"color": "#ff7f0e", "width": 3},
    ),
    row=2,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=smoothed_gdppc_df[f"{value_col_gdppc_full}_gdppc"],
        y=smoothed_gdppc_df[f"{value_col_extrap}_stock"],
        mode="lines",
        name="Step 3: Transition smoothing",
        legendgroup="after_smooth_transition",
        showlegend=False,
        line={"color": "#2ca02c", "width": 3},
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=smoothed_df[time_col_extrap],
        y=smoothed_df[value_col_extrap],
        mode="lines",
        name="Step 3: Transition smoothing",
        legendgroup="after_smooth_transition",
        showlegend=False,
        line={"color": "#2ca02c", "width": 3},
    ),
    row=2,
    col=1,
)

fig.add_shape(
    type="line",
    x0=last_hist_gdppc,
    x1=last_hist_gdppc,
    y0=0,
    y1=12.5,
    xref="x",
    yref="y",
    line={"dash": "dash", "color": "black"},
)
fig.add_shape(
    type="line",
    x0=LAST_HISTORICAL_YEAR_STEEL,
    x1=LAST_HISTORICAL_YEAR_STEEL,
    y0=0,
    y1=12.5,
    xref="x2",
    yref="y2",
    line={"dash": "dash", "color": "black"},
)
fig.update_xaxes(
    title_text="GDP per capita [USD 2017]",
    title_standoff=4,
    type="log",
    range=[math.log10(gdppc_1920), math.log10(500000)],
    row=1,
    col=1,
)
fig.update_xaxes(title_text="Year", title_standoff=4, range=[1920, 2175], row=2, col=1)
fig.update_yaxes(
    title_text="In-use stock per capita [t]", title_standoff=4, range=[0, 12.7], row=1, col=1
)
fig.update_yaxes(
    title_text="In-use stock per capita [t]", title_standoff=4, range=[0, 12.7], row=2, col=1
)

figure_height = 900
figure_width = 630

within_group_spacing = 0.05 * 900 / figure_height
title_to_group_spacing = 0.055 * 900 / figure_height

top_hist_group_top_y = 0.5
top_extrap_group_top_y = 0.86

bottom_hist_group_top_y = 0.92
bottom_extrap_group_top_y = 0.86

hist_group_x = 0.02
extrap_group_x = 0.72


def _add_historical_group(
    x_left: float,
    group_top_y: float,
    yref: str,
    within_group_spacing: float,
    title_to_group_spacing: float,
):
    title_y = group_top_y + title_to_group_spacing
    fig.add_annotation(
        x=x_left,
        y=title_y,
        xref="paper",
        yref=yref,
        text="<b>Historical</b>",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "black", "size": 14},
    )
    fig.add_annotation(
        x=x_left,
        y=group_top_y,
        xref="paper",
        yref=yref,
        text="Extrapolated region",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "black", "size": 13},
    )
    fig.add_annotation(
        x=x_left,
        y=group_top_y - within_group_spacing,
        xref="paper",
        yref=yref,
        text="Other regions",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "#808080", "size": 13},
    )


def _add_extrapolation_group(
    x_right: float,
    group_top_y: float,
    yref: str,
    within_group_spacing: float,
    title_to_group_spacing: float,
):
    title_y = group_top_y + title_to_group_spacing
    fig.add_annotation(
        x=x_right,
        y=title_y,
        xref="paper",
        yref=yref,
        text="<b>Extrapolation</b>",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "black", "size": 14},
    )
    fig.add_annotation(
        x=x_right,
        y=group_top_y - 2 * within_group_spacing,
        xref="paper",
        yref=yref,
        text="Step 1: Common regression",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "#1f77b4", "size": 13},
    )
    fig.add_annotation(
        x=x_right,
        y=group_top_y - within_group_spacing,
        xref="paper",
        yref=yref,
        text="Step 2: Regional adaptation",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "#ff7f0e", "size": 13},
    )
    fig.add_annotation(
        x=x_right,
        y=group_top_y,
        xref="paper",
        yref=yref,
        text="Step 3: Transition smoothing",
        showarrow=False,
        xanchor="left",
        align="left",
        font={"color": "#2ca02c", "size": 13},
    )


_add_historical_group(
    x_left=hist_group_x,
    group_top_y=top_hist_group_top_y,
    yref="y domain",
    within_group_spacing=within_group_spacing,
    title_to_group_spacing=title_to_group_spacing,
)
_add_extrapolation_group(
    x_right=extrap_group_x,
    group_top_y=top_extrap_group_top_y,
    yref="y domain",
    within_group_spacing=within_group_spacing,
    title_to_group_spacing=title_to_group_spacing,
)
_add_historical_group(
    x_left=hist_group_x,
    group_top_y=bottom_hist_group_top_y,
    yref="y2 domain",
    within_group_spacing=within_group_spacing,
    title_to_group_spacing=title_to_group_spacing,
)
_add_extrapolation_group(
    x_right=extrap_group_x,
    group_top_y=bottom_extrap_group_top_y,
    yref="y2 domain",
    within_group_spacing=within_group_spacing,
    title_to_group_spacing=title_to_group_spacing,
)

# Slightly raise subplot titles without affecting custom label annotations.
for annotation in fig.layout.annotations:
    if annotation.text in ("a) Over GDP per capita", "b) Over time"):
        annotation.y = annotation.y + 0.02


fig.update_layout(
    height=figure_height,
    width=figure_width,
    showlegend=False,
    template="plotly_white",
)


fig.show()
