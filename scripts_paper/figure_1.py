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
)


@dataclass(frozen=True)
class RunConfig:
    directory: pathlib.Path
    label: str
    run_name: str
    flow_name: str
    last_historical_year: int


RUN_CONFIGS = [
    RunConfig(
        directory=PATH_CEMENT,
        label="a) Cement",
        run_name=RUN_CEMENT,
        flow_name="prod_cement => prod_product",
        last_historical_year=LAST_HISTORICAL_YEAR_CEMENT,
    ),
    RunConfig(
        directory=PATH_PLASTICS,
        label="b) Plastics",
        run_name=RUN_PLASTICS,
        flow_name="virgin => primary_market",
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


fig = make_subplots(
    rows=len(RUN_CONFIGS),
    cols=2,
    shared_xaxes=False,
    horizontal_spacing=0.12,
)

seen_regions = set()
region_colors = {}


def _get_region_color(region: str) -> str:
    if region not in region_colors:
        region_colors[region] = COLOR_PALETTE[len(region_colors) % len(COLOR_PALETTE)]
    return region_colors[region]


for i, config in enumerate(RUN_CONFIGS):
    row = i + 1
    pickle_path = config.directory / f"{config.run_name}.pickle"
    with pickle_path.open("rb") as file_handle:
        mfa = pickle.load(file_handle).future_mfa
    flow = (mfa.flows[config.flow_name].sum_to(("t", "r")) / 1e6).to_df().reset_index()
    stock = mfa.stocks["in_use"].stock.sum_to(("t", "r"))
    stock_pc = (stock / mfa.parameters["population"]).to_df().reset_index()

    time_col_flow = _get_column_name(flow, "Time")
    region_col_flow = _get_column_name(flow, "Region")
    value_col_flow = _get_column_name(flow, "value")

    time_col_stock = _get_column_name(stock_pc, "Time")
    region_col_stock = _get_column_name(stock_pc, "Region")
    value_col_stock = _get_column_name(stock_pc, "value")

    for region, region_df in stock_pc.groupby(region_col_stock):
        region_df = region_df.sort_values(time_col_stock)
        region_code = str(region)
        legend_label = REGION_DISPLAY_NAMES.get(region_code, region_code)
        show_legend = region_code not in seen_regions
        region_color = _get_region_color(region_code)
        fig.add_trace(
            go.Scatter(
                x=region_df[time_col_stock],
                y=region_df[value_col_stock],
                mode="lines",
                name=legend_label,
                legendgroup=region_code,
                showlegend=show_legend,
                line={"color": region_color},
            ),
            row=row,
            col=1,
        )
        seen_regions.add(region_code)

    for region, region_df in flow.groupby(region_col_flow):
        region_df = region_df.sort_values(time_col_flow)
        region_code = str(region)
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
                line={"color": region_color},
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


fig.show()
