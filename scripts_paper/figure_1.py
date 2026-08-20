import pickle
import flodym as fd
import pathlib
from dataclasses import dataclass
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import (
    COLOR_PALETTE,
    LAST_HISTORICAL_YEAR_CEMENT,
    LAST_HISTORICAL_YEAR_PLASTICS,
    LAST_HISTORICAL_YEAR_STEEL,
    PATH_CEMENT,
    PATH_PLASTICS,
    PATH_STEEL,
    REGION_DISPLAY_NAMES,
    RUN_CEMENT,
    RUN_PLASTICS,
    RUN_STEEL,
    AGG_REGIONS,
    AGG_REGION_ORDER,
    AGG_COLOR_PALETTE,
)
import os

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


@dataclass(frozen=True)
class RunConfig:
    directory: pathlib.Path
    label: str
    run_name: str
    flow_name: str
    last_historical_year: int
    stock_index: str = None


RUN_CONFIGS = [
    RunConfig(
        directory=PATH_PLASTICS,
        label="a) Plastics",
        run_name=RUN_PLASTICS,
        flow_name="polymerization => primary_market",
        last_historical_year=LAST_HISTORICAL_YEAR_PLASTICS,
    ),
    RunConfig(
        directory=PATH_STEEL,
        label="b) Steel",
        run_name=RUN_STEEL,
        flow_name="forming => ip_market",
        last_historical_year=LAST_HISTORICAL_YEAR_STEEL,
    ),
    RunConfig(
        directory=PATH_CEMENT,
        label="c) Cement",
        run_name=RUN_CEMENT,
        flow_name="prod_cement => market_cement",
        last_historical_year=LAST_HISTORICAL_YEAR_CEMENT,
        stock_index="cement",
    ),
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


fig = make_subplots(
    rows=3,
    cols=len(RUN_CONFIGS),
    shared_xaxes=False,
    horizontal_spacing=0.08,
)

LINE_WIDTH_SCALE = 0.75
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_STACK = 0.5 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 2 * LINE_WIDTH_SCALE
LEFT_Y_TITLE_X = 0
LEFT_Y_TITLE_XSHIFT = -30

seen_regions = set()
region_colors = {}
region_symbols = {}
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


for i, config in enumerate(RUN_CONFIGS):
    col = i + 1
    pickle_path = config.directory / f"{config.run_name}.pickle"
    with pickle_path.open("rb") as file_handle:
        mfa = pickle.load(file_handle).future_mfa

    flow = (mfa.flows[config.flow_name].sum_to(("t", "r")) / 1e6).to_df().reset_index()
    time_col_flow = _get_column_name(flow, "Time")
    region_col_flow = _get_column_name(flow, "Region")
    value_col_flow = _get_column_name(flow, "value")
    flow = _aggregate_region_timeseries(flow, time_col_flow, region_col_flow, value_col_flow)

    stock = mfa.stocks["in_use"].stock
    if config.stock_index is not None:
        stock = stock[config.stock_index]
    stock = stock.sum_to(("t", "r")).to_df().reset_index()
    population = mfa.parameters["population"].sum_to(("t", "r")).to_df().reset_index()

    time_col_stock = _get_column_name(stock, "Time")
    region_col_stock = _get_column_name(stock, "Region")
    value_col_stock = _get_column_name(stock, "value")

    time_col_pop = _get_column_name(population, "Time")
    region_col_pop = _get_column_name(population, "Region")
    value_col_pop = _get_column_name(population, "value")

    stock = _aggregate_region_timeseries(stock, time_col_stock, region_col_stock, value_col_stock)
    population = _aggregate_region_timeseries(
        population, time_col_pop, region_col_pop, value_col_pop
    )

    stock_pc = stock.merge(
        population,
        left_on=[time_col_stock, region_col_stock],
        right_on=[time_col_pop, region_col_pop],
        suffixes=("_stock", "_population"),
    )
    stock_pc[value_col_stock] = (
        stock_pc[f"{value_col_stock}_stock"] / stock_pc[f"{value_col_pop}_population"]
    )
    stock_pc = stock_pc[[time_col_stock, region_col_stock, value_col_stock]]

    production_pc = flow.merge(
        population,
        left_on=[time_col_flow, region_col_flow],
        right_on=[time_col_pop, region_col_pop],
        suffixes=("_production", "_population"),
    )
    production_pc[value_col_flow] = (
        production_pc[f"{value_col_flow}_production"]
        / production_pc[f"{value_col_pop}_population"]
        * 1e6
    )
    production_pc = production_pc[[time_col_flow, region_col_flow, value_col_flow]]

    global_avg = stock.groupby(time_col_stock, as_index=False)[value_col_stock].sum()
    global_population = population.groupby(time_col_pop, as_index=False)[value_col_pop].sum()
    global_avg = global_avg.merge(
        global_population,
        left_on=time_col_stock,
        right_on=time_col_pop,
        suffixes=("_stock", "_population"),
    )
    global_avg[value_col_stock] = (
        global_avg[f"{value_col_stock}_stock"] / global_avg[f"{value_col_pop}_population"]
    )

    global_production = flow.groupby(time_col_flow, as_index=False)[value_col_flow].sum()
    global_production = global_production.merge(
        global_population,
        left_on=time_col_flow,
        right_on=time_col_pop,
        suffixes=("_production", "_population"),
    )
    global_production[value_col_flow] = (
        global_production[f"{value_col_flow}_production"]
        / global_production[f"{value_col_pop}_population"]
        * 1e6
    )

    flow_total = flow.groupby(time_col_flow, as_index=False)[value_col_flow].sum()
    flow_gt = flow.copy()
    flow_gt[value_col_flow] = flow_gt[value_col_flow] / 1000
    flow_total_gt = flow_total.copy()
    flow_total_gt[value_col_flow] = flow_total_gt[value_col_flow] / 1000

    stock_regions = _ordered_regions(stock_pc[region_col_stock].unique(), reverse=True)
    for region_code in stock_regions:
        region_df = stock_pc[stock_pc[region_col_stock] == region_code].sort_values(time_col_stock)
        legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
        show_legend = region_code not in seen_regions
        region_color = _get_region_color(region_code)
        region_symbol = _get_region_symbol(region_code)

        # Trace 1: Continuous line on plot
        fig.add_trace(
            go.Scatter(
                x=region_df[time_col_stock],
                y=region_df[value_col_stock],
                mode="lines",
                name=legend_label,
                legendgroup=region_code,
                showlegend=False,
                line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
            ),
            row=1,
            col=col,
        )

        # Trace 2: Markers every 20th point on plot
        marker_df = region_df.iloc[::20]
        fig.add_trace(
            go.Scatter(
                x=marker_df[time_col_stock],
                y=marker_df[value_col_stock],
                mode="markers",
                name=legend_label,
                legendgroup=region_code,
                showlegend=False,
                marker={"color": region_color, "size": 9, "symbol": region_symbol},
            ),
            row=1,
            col=col,
        )

        # Trace 3: Legend entry with markers on all points and dummy line outside range
        legend_x = [1700, 1700]
        legend_y = [0, 0.1]
        fig.add_trace(
            go.Scatter(
                x=legend_x,
                y=legend_y,
                mode="lines+markers",
                name=legend_label,
                legendgroup=region_code,
                showlegend=show_legend,
                marker={"color": region_color, "size": 9, "symbol": region_symbol},
                line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
            ),
            row=1,
            col=col,
        )
        seen_regions.add(region_code)

        #

    fig.add_trace(
        go.Scatter(
            x=global_avg[time_col_stock],
            y=global_avg[value_col_stock],
            mode="lines",
            name="World",
            legendgroup="world",
            showlegend=(col == 1),
            line={"color": "black", "width": LINE_WIDTH_DEFAULT, "dash": "dot"},
        ),
        row=1,
        col=col,
    )

    production_regions = _ordered_regions(production_pc[region_col_flow].unique(), reverse=False)
    for region_code in production_regions:
        region_df = production_pc[production_pc[region_col_flow] == region_code].sort_values(
            time_col_flow
        )
        legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
        show_legend = region_code not in seen_regions
        region_color = _get_region_color(region_code)
        region_symbol = _get_region_symbol(region_code)

        fig.add_trace(
            go.Scatter(
                x=region_df[time_col_flow],
                y=region_df[value_col_flow],
                mode="lines",
                name=legend_label,
                legendgroup=region_code,
                showlegend=False,
                line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
            ),
            row=2,
            col=col,
        )

        marker_df = region_df.iloc[::20]
        fig.add_trace(
            go.Scatter(
                x=marker_df[time_col_flow],
                y=marker_df[value_col_flow],
                mode="markers",
                name=legend_label,
                legendgroup=region_code,
                showlegend=False,
                marker={"color": region_color, "size": 9, "symbol": region_symbol},
            ),
            row=2,
            col=col,
        )

        legend_x = [1700, 1700]
        legend_y = [0, 0.1]
        fig.add_trace(
            go.Scatter(
                x=legend_x,
                y=legend_y,
                mode="lines+markers",
                name=legend_label,
                legendgroup=region_code,
                showlegend=show_legend,
                marker={"color": region_color, "size": 9, "symbol": region_symbol},
                line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
            ),
            row=2,
            col=col,
        )
        seen_regions.add(region_code)

    fig.add_trace(
        go.Scatter(
            x=global_production[time_col_flow],
            y=global_production[value_col_flow],
            mode="lines",
            name="World",
            legendgroup="world",
            showlegend=False,
            line={"color": "black", "width": LINE_WIDTH_DEFAULT, "dash": "dot"},
        ),
        row=2,
        col=col,
    )

    flow_regions = _ordered_regions(flow_gt[region_col_flow].unique(), reverse=True)
    for region_code in flow_regions:
        region_df = flow_gt[flow_gt[region_col_flow] == region_code].sort_values(time_col_flow)
        legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
        region_color = _get_region_color(region_code)
        fig.add_trace(
            go.Scatter(
                x=region_df[time_col_flow],
                y=region_df[value_col_flow],
                mode="lines",
                name=legend_label,
                legendgroup=region_code,
                showlegend=False,
                line={"color": region_color, "width": LINE_WIDTH_STACK},
                stackgroup=f"flow_col_{col}",
                fillcolor=region_color,
            ),
            row=3,
            col=col,
        )

    fig.add_trace(
        go.Scatter(
            x=flow_total_gt[time_col_flow],
            y=flow_total_gt[value_col_flow],
            mode="lines",
            name="World",
            legendgroup="world",
            showlegend=False,
            line={"color": "black", "width": LINE_WIDTH_DEFAULT, "dash": "dot"},
        ),
        row=3,
        col=col,
    )

    for metric_row in range(1, 4):
        fig.add_vline(
            x=config.last_historical_year,
            line_dash="dash",
            line_color="black",
            line_width=LINE_WIDTH_VLINE,
            row=metric_row,
            col=col,
        )
        fig.update_xaxes(
            title_text="Year", title_standoff=4, range=[1950, 2100], row=metric_row, col=col
        )

    fig.update_yaxes(title_text="", row=1, col=col)
    fig.update_yaxes(title_text="", row=2, col=col)
    fig.update_yaxes(title_text="", row=3, col=col)

for col, config in enumerate(RUN_CONFIGS, start=1):
    col_domain = fig.get_subplot(1, col).xaxis.domain
    fig.add_annotation(
        x=(col_domain[0] + col_domain[1]) / 2,
        y=1.05,
        xref="paper",
        yref="paper",
        text=f"<b>{config.label}</b>",
        showarrow=False,
        xanchor="center",
        font={"size": 16},
        # align="center",
    )

left_y_labels = [
    "<b>In-use stock per capita (t)</b>",
    "<b>Production per capita (t)</b>",
    "<b>Production (Gt)</b>",
]
for row, label in enumerate(left_y_labels, start=1):
    row_domain = fig.get_subplot(row, 1).yaxis.domain
    fig.add_annotation(
        x=LEFT_Y_TITLE_X,
        xshift=LEFT_Y_TITLE_XSHIFT,
        y=(row_domain[0] + row_domain[1]) / 2,
        xref="paper",
        yref="paper",
        text=label,
        showarrow=False,
        textangle=-90,
        xanchor="right",
        yanchor="middle",
        font={"size": 16},
    )


fig.update_layout(
    height=300 * len(RUN_CONFIGS) + 100,
    width=900,
    template="plotly_white",
    legend={
        "orientation": "h",
        "x": 0.5,
        "xanchor": "center",
        "y": 1.08,
        "yanchor": "bottom",
        "bordercolor": "black",
        "borderwidth": 1,
    },
    margin={"t": 130, "b": 60, "l": 80, "r": 50},
)


# Save a high-resolution static copy while preserving on-figure relative sizing.
output_path = pathlib.Path(__file__).with_name("figure_1.png")
fig.write_image(
    output_path,
    width=fig.layout.width,
    height=fig.layout.height,
    scale=3,
)


fig.show()
