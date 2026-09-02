import argparse
import os

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import scripts_paper._utils as _utils
from scripts_paper._constants import MATERIAL_ORDER, figure_output_path, get_material_config

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

LINE_WIDTH_SCALE = 1.5
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_STACK = 0.5 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 1.2 * LINE_WIDTH_SCALE
LEFT_Y_TITLE_X = 0
LEFT_Y_TITLE_XSHIFT = -30
MAXIMUM_LEGENDTEXT_BRIGHTNESS = 0.4
LEGEND_FONT_SIZE = 13


def _legend_name(label: str, color: str) -> str:
    return _utils.legend_name(label, color, MAXIMUM_LEGENDTEXT_BRIGHTNESS)


def _get_region_color(region: str, region_colors: dict, aggregate_regions: bool) -> str:
    return _utils.get_region_color(region, region_colors, aggregate_regions=aggregate_regions)


def _load_run_data(config, aggregate_regions: bool):
    mfa = _utils.load_future_mfa(config.material)

    flow = (mfa.flows[config.production_flow_name].sum_to(("t", "r")) / 1e6).to_df().reset_index()
    time_col_flow = _utils.get_column_name(flow, "Time")
    region_col_flow = _utils.get_column_name(flow, "Region")
    value_col_flow = _utils.get_column_name(flow, "value")
    flow = _utils.aggregate_region_timeseries(
        flow,
        time_col_flow,
        region_col_flow,
        value_col_flow,
        aggregate_regions=aggregate_regions,
    )

    stock = mfa.stocks["in_use"].stock
    if config.stock_index is not None:
        stock = stock[config.stock_index]
    stock = stock.sum_to(("t", "r")).to_df().reset_index()
    population = mfa.parameters["population"].sum_to(("t", "r")).to_df().reset_index()

    time_col_stock = _utils.get_column_name(stock, "Time")
    region_col_stock = _utils.get_column_name(stock, "Region")
    value_col_stock = _utils.get_column_name(stock, "value")
    time_col_pop = _utils.get_column_name(population, "Time")
    region_col_pop = _utils.get_column_name(population, "Region")
    value_col_pop = _utils.get_column_name(population, "value")

    stock = _utils.aggregate_region_timeseries(
        stock,
        time_col_stock,
        region_col_stock,
        value_col_stock,
        aggregate_regions=aggregate_regions,
    )
    population = _utils.aggregate_region_timeseries(
        population,
        time_col_pop,
        region_col_pop,
        value_col_pop,
        aggregate_regions=aggregate_regions,
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

    return {
        "config": config,
        "stock_pc": stock_pc,
        "production_pc": production_pc,
        "flow_gt": flow_gt,
        "global_avg": global_avg,
        "global_production": global_production,
        "flow_total_gt": flow_total_gt,
        "time_col_stock": time_col_stock,
        "region_col_stock": region_col_stock,
        "value_col_stock": value_col_stock,
        "time_col_flow": time_col_flow,
        "region_col_flow": region_col_flow,
        "value_col_flow": value_col_flow,
    }


def main(use_h12: bool = False, mfa_regions: str = "h12", show: bool = True):
    aggregate_regions = not use_h12
    run_configs = [get_material_config(material) for material in MATERIAL_ORDER]

    fig = make_subplots(
        rows=3,
        cols=len(run_configs),
        shared_xaxes=False,
        horizontal_spacing=0.08,
    )

    seen_regions = set()
    region_colors = {}

    for col, config in enumerate(run_configs, start=1):
        run_data = _load_run_data(config, aggregate_regions=aggregate_regions)

        stock_regions = _utils.ordered_regions(
            run_data["stock_pc"][run_data["region_col_stock"]].unique(),
            reverse=True,
            aggregate_regions=aggregate_regions,
        )
        for region_code in stock_regions:
            region_df = run_data["stock_pc"][
                run_data["stock_pc"][run_data["region_col_stock"]] == region_code
            ].sort_values(run_data["time_col_stock"])
            legend_label = _utils.get_region_label(region_code, aggregate_regions=aggregate_regions)
            show_legend = region_code not in seen_regions
            region_color = _get_region_color(
                region_code, region_colors, aggregate_regions=aggregate_regions
            )

            fig.add_trace(
                go.Scatter(
                    x=region_df[run_data["time_col_stock"]],
                    y=region_df[run_data["value_col_stock"]],
                    mode="lines",
                    name=_legend_name(legend_label, region_color),
                    legendgroup=region_code,
                    showlegend=show_legend,
                    line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
                ),
                row=1,
                col=col,
            )
            seen_regions.add(region_code)

        fig.add_trace(
            go.Scatter(
                x=run_data["global_avg"][run_data["time_col_stock"]],
                y=run_data["global_avg"][run_data["value_col_stock"]],
                mode="lines",
                name=_legend_name("World", "black"),
                legendgroup="world",
                showlegend=(col == 1),
                line={"color": "black", "width": LINE_WIDTH_DEFAULT, "dash": "dot"},
            ),
            row=1,
            col=col,
        )

        production_regions = _utils.ordered_regions(
            run_data["production_pc"][run_data["region_col_flow"]].unique(),
            reverse=False,
            aggregate_regions=aggregate_regions,
        )
        for region_code in production_regions:
            region_df = run_data["production_pc"][
                run_data["production_pc"][run_data["region_col_flow"]] == region_code
            ].sort_values(run_data["time_col_flow"])
            legend_label = _utils.get_region_label(region_code, aggregate_regions=aggregate_regions)
            show_legend = region_code not in seen_regions
            region_color = _get_region_color(
                region_code, region_colors, aggregate_regions=aggregate_regions
            )

            fig.add_trace(
                go.Scatter(
                    x=region_df[run_data["time_col_flow"]],
                    y=region_df[run_data["value_col_flow"]],
                    mode="lines",
                    name=_legend_name(legend_label, region_color),
                    legendgroup=region_code,
                    showlegend=show_legend,
                    line={"color": region_color, "width": LINE_WIDTH_DEFAULT},
                ),
                row=2,
                col=col,
            )
            seen_regions.add(region_code)

        fig.add_trace(
            go.Scatter(
                x=run_data["global_production"][run_data["time_col_flow"]],
                y=run_data["global_production"][run_data["value_col_flow"]],
                mode="lines",
                name=_legend_name("World", "black"),
                legendgroup="world",
                showlegend=False,
                line={"color": "black", "width": LINE_WIDTH_DEFAULT, "dash": "dot"},
            ),
            row=2,
            col=col,
        )

        flow_regions = _utils.ordered_regions(
            run_data["flow_gt"][run_data["region_col_flow"]].unique(),
            reverse=True,
            aggregate_regions=aggregate_regions,
        )
        for region_code in flow_regions:
            region_df = run_data["flow_gt"][
                run_data["flow_gt"][run_data["region_col_flow"]] == region_code
            ].sort_values(run_data["time_col_flow"])
            legend_label = _utils.get_region_label(region_code, aggregate_regions=aggregate_regions)
            region_color = _get_region_color(
                region_code, region_colors, aggregate_regions=aggregate_regions
            )
            fig.add_trace(
                go.Scatter(
                    x=region_df[run_data["time_col_flow"]],
                    y=region_df[run_data["value_col_flow"]],
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
                x=run_data["flow_total_gt"][run_data["time_col_flow"]],
                y=run_data["flow_total_gt"][run_data["value_col_flow"]],
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
                title_text="Year",
                title_standoff=4,
                range=[1950, 2100],
                row=metric_row,
                col=col,
            )

    for col, config in enumerate(run_configs, start=1):
        col_domain = fig.get_subplot(1, col).xaxis.domain
        fig.add_annotation(
            x=(col_domain[0] + col_domain[1]) / 2,
            y=1.05,
            xref="paper",
            yref="paper",
            text=f"<b>{config.panel_label}</b>",
            showarrow=False,
            xanchor="center",
            font={"size": 16},
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
        height=300 * len(run_configs) + 100,
        width=900 if aggregate_regions else 1050,
        template="plotly_white",
        legend={
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": 1.08,
            "yanchor": "bottom",
            "font": {"size": LEGEND_FONT_SIZE},
            "bordercolor": "black",
            "borderwidth": 1,
        },
        margin={"t": 130, "b": 60, "l": 80, "r": 50},
    )

    output_path = figure_output_path(f"figure_8_{_utils.region_mode_suffix(use_h12)}.png")
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
    parser.add_argument("--h12", action="store_true")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    main(use_h12=args.h12, show=not args.no_show)
