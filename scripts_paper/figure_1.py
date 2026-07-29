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
        directory=PATH_CEMENT,
        label="a) Cement",
        run_name=RUN_CEMENT,
        flow_name="prod_cement => market_cement",
        last_historical_year=LAST_HISTORICAL_YEAR_CEMENT,
        stock_index="cement",
    ),
    RunConfig(
        directory=PATH_PLASTICS,
        label="b) Plastics",
        run_name=RUN_PLASTICS,
        flow_name="polymerization => primary_market",
        last_historical_year=LAST_HISTORICAL_YEAR_PLASTICS,
    ),
    RunConfig(
        directory=PATH_STEEL,
        label="c) Steel",
        run_name=RUN_STEEL,
        flow_name="forming => ip_market",
        last_historical_year=LAST_HISTORICAL_YEAR_STEEL,
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
    rows=len(RUN_CONFIGS),
    cols=2,
    shared_xaxes=False,
    horizontal_spacing=0.12,
)

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
    row = i + 1
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
    stock_pc[value_col_stock] = stock_pc[f"{value_col_stock}_stock"] / stock_pc[
        f"{value_col_pop}_population"
    ]
    stock_pc = stock_pc[[time_col_stock, region_col_stock, value_col_stock]]

    global_avg = stock.groupby(time_col_stock, as_index=False)[value_col_stock].sum()
    global_population = population.groupby(time_col_pop, as_index=False)[value_col_pop].sum()
    global_avg = global_avg.merge(
        global_population,
        left_on=time_col_stock,
        right_on=time_col_pop,
        suffixes=("_stock", "_population"),
    )
    global_avg[value_col_stock] = global_avg[f"{value_col_stock}_stock"] / global_avg[
        f"{value_col_pop}_population"
    ]

    flow_total = flow.groupby(time_col_flow, as_index=False)[value_col_flow].sum()

    stock_regions = _ordered_regions(stock_pc[region_col_stock].unique(), reverse=False)
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
                line={"color": region_color},
            ),
            row=row,
            col=1,
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
            row=row,
            col=1,
        )

        # Trace 3: Legend entry with markers on all points and dummy line outside range
        legend_x = [1700, 1700]
        legend_y = [0, 1]
        fig.add_trace(
            go.Scatter(
                x=legend_x,
                y=legend_y,
                mode="lines+markers",
                name=legend_label,
                legendgroup=region_code,
                showlegend=show_legend,
                marker={"color": region_color, "size": 9, "symbol": region_symbol},
                line={"color": region_color},
            ),
            row=row,
            col=1,
        )
        seen_regions.add(region_code)

    fig.add_trace(
        go.Scatter(
            x=global_avg[time_col_stock],
            y=global_avg[value_col_stock],
            mode="lines",
            name="World",
            legendgroup="world",
            showlegend=(row == 1),
            line={"color": "black", "width": 2, "dash": "dot"},
        ),
        row=row,
        col=1,
    )

    flow_regions = _ordered_regions(flow[region_col_flow].unique(), reverse=True)
    for region_code in flow_regions:
        region_df = flow[flow[region_col_flow] == region_code].sort_values(time_col_flow)
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
                line={"color": region_color, "width": 0.5},
                stackgroup=f"flow_row_{row}",
                fillcolor=region_color,
            ),
            row=row,
            col=2,
        )

    fig.add_trace(
        go.Scatter(
            x=flow_total[time_col_flow],
            y=flow_total[value_col_flow],
            mode="lines",
            name="World",
            legendgroup="world",
            showlegend=False,
            line={"color": "black", "width": 2, "dash": "dot"},
        ),
        row=row,
        col=2,
    )

    fig.add_vline(
        x=config.last_historical_year, line_dash="dash", line_color="black", row=row, col=1
    )
    fig.add_vline(
        x=config.last_historical_year, line_dash="dash", line_color="black", row=row, col=2
    )

    fig.update_xaxes(title_text="Year", title_standoff=4, range=[1950, 2100], row=row, col=1)
    fig.update_xaxes(title_text="Year", title_standoff=4, range=[1950, 2100], row=row, col=2)
    fig.update_yaxes(title_text="In-use stock per capita [t]", title_standoff=4, row=row, col=1)
    fig.update_yaxes(title_text="Production [Mt]", title_standoff=4, row=row, col=2)

if len(RUN_CONFIGS) > 1:
    for row, config in enumerate(RUN_CONFIGS, start=1):
        row_domain = fig.get_subplot(row, 1).yaxis.domain
        fig.add_annotation(
            x=0.5,
            y=row_domain[1] + 0.02,
            xref="paper",
            yref="paper",
            text=f"<b>{config.label}</b>",
            showarrow=False,
            font={"size": 14},
        )


fig.update_layout(
    height=400 * len(RUN_CONFIGS),
    width=1000,
    template="plotly_white",
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
