import argparse
import csv
import math
import pathlib

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import _utils
from _constants import CMAP_5, MATERIAL_ORDER, figure_output_path, get_material_config

X_RANGE = [1950, 2100]
LINE_WIDTH_SCALE = 1.5
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 1.2 * LINE_WIDTH_SCALE
AXIS_LABEL_FONT_SIZE = 14
LEFT_COLUMN_Y_LABEL_X = -0.05
MAXIMUM_LEGENDTEXT_BRIGHTNESS = 0.4
H12_COLOR = CMAP_5[1]
ISO249_COLOR = CMAP_5[3]
REGION_MAPPING_PATH = pathlib.Path(__file__).resolve().with_name("regionmapping.csv")


def _legend_name(label: str, color: str) -> str:
    return _utils.legend_name(label, color, MAXIMUM_LEGENDTEXT_BRIGHTNESS)


def _load_country_to_h12_region_map() -> dict[str, str]:
    region_map: dict[str, str] = {}
    with REGION_MAPPING_PATH.open(newline="", encoding="utf-8") as file_handle:
        reader = csv.reader(file_handle, delimiter=";")
        next(reader, None)
        for row in reader:
            if len(row) < 4:
                continue
            country_code = row[2].strip()
            region_code = row[3].strip()
            if country_code:
                region_map[country_code] = region_code
    return region_map


COUNTRY_TO_H12_REGION = _load_country_to_h12_region_map()


def _aggregate_region_timeseries_with_map(df, time_col: str, region_col: str, value_col: str, region_map: dict[str, str]):
    aggregated = df.copy()
    aggregated[region_col] = aggregated[region_col].map(lambda region: region_map.get(str(region), str(region)))
    return aggregated.groupby([time_col, region_col], as_index=False)[value_col].sum().sort_values([time_col, region_col])


def _load_production_df(config, region_mapping: str):
    mfa = _utils.load_future_mfa(config.material, region_mapping=region_mapping)
    flow = (mfa.flows[config.production_flow_name].sum_to(("t", "r")) / 1e6).to_df().reset_index()
    time_col = _utils.get_column_name(flow, "Time")
    region_col = _utils.get_column_name(flow, "Region")
    value_col = _utils.get_column_name(flow, "value")

    if region_mapping == "iso249":
        flow = _aggregate_region_timeseries_with_map(
            flow,
            time_col,
            region_col,
            value_col,
            COUNTRY_TO_H12_REGION,
        )

    flow = flow.groupby([time_col, region_col], as_index=False)[value_col].sum().sort_values([time_col, region_col])
    return flow, time_col, region_col, value_col


def _panel_position(index: int, n_cols: int):
    row = index // n_cols + 1
    col = index % n_cols + 1
    return row, col


def _build_figure(config) -> go.Figure:
    h12_data, time_col, region_col, value_col = _load_production_df(config, region_mapping="h12")
    iso249_data, _, _, _ = _load_production_df(config, region_mapping="iso249")

    region_panels = _utils.ordered_regions(
        sorted(set(h12_data[region_col].astype(str))),
        reverse=True,
        aggregate_regions=False,
    )
    n_panels = len(region_panels)
    n_cols = 3 if n_panels <= 6 else 4
    n_rows = math.ceil(n_panels / n_cols)
    subplot_titles = [
        _utils.get_region_label(region, aggregate_regions=False)
        for region in region_panels
    ]

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.10,
        vertical_spacing=0.22 if n_rows <= 2 else 0.12,
    )

    for panel_index, region_code in enumerate(region_panels):
        row, col = _panel_position(panel_index, n_cols)
        h12_region_df = h12_data[h12_data[region_col].astype(str) == str(region_code)].sort_values(time_col)
        iso249_region_df = iso249_data[iso249_data[region_col].astype(str) == str(region_code)].sort_values(time_col)

        if not h12_region_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=h12_region_df[time_col],
                    y=h12_region_df[value_col],
                    mode="lines",
                    name=_legend_name("h12", H12_COLOR),
                    legendgroup="h12",
                    showlegend=(panel_index == 0),
                    line={"color": H12_COLOR, "width": LINE_WIDTH_DEFAULT},
                ),
                row=row,
                col=col,
            )

        if not iso249_region_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=iso249_region_df[time_col],
                    y=iso249_region_df[value_col],
                    mode="lines",
                    name=_legend_name("iso249 → h12", ISO249_COLOR),
                    legendgroup="iso249_h12",
                    showlegend=(panel_index == 0),
                    line={"color": ISO249_COLOR, "width": LINE_WIDTH_DEFAULT},
                ),
                row=row,
                col=col,
            )

        fig.add_vline(
            x=config.last_historical_year,
            line_dash="dash",
            line_color="black",
            line_width=LINE_WIDTH_VLINE,
            row=row,
            col=col,
        )

    fig.for_each_xaxis(
        lambda axis: axis.update(
            title_text="Year",
            title_font={"size": AXIS_LABEL_FONT_SIZE},
            title_standoff=4,
            range=X_RANGE,
        )
    )
    fig.for_each_yaxis(lambda axis: axis.update(title_text="", showgrid=True))

    for row in range(1, n_rows + 1):
        yaxis = getattr(fig.layout, f"yaxis{1 if row == 1 else (row - 1) * n_cols + 1}", None)
        if yaxis is None or yaxis.domain is None:
            continue
        y0, y1 = yaxis.domain
        fig.add_annotation(
            x=LEFT_COLUMN_Y_LABEL_X,
            y=0.5 * (y0 + y1),
            xref="paper",
            yref="paper",
            text="Production (Gt)",
            font={"size": AXIS_LABEL_FONT_SIZE},
            textangle=-90,
            showarrow=False,
            xanchor="center",
            yanchor="middle",
        )

    fig.update_layout(
        template="plotly_white",
        width=900 if n_cols == 3 else 1200,
        height=600 if n_rows == 2 else 300 * n_rows,
        margin={"t": 110, "b": 70, "l": 90, "r": 50},
        legend={
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": 1.05,
            "yanchor": "bottom",
            "font": {"size": 14},
            "bordercolor": "black",
            "borderwidth": 1,
        },
    )
    return fig


def main(show: bool = True):
    for material in MATERIAL_ORDER:
        config = get_material_config(material)
        fig = _build_figure(config)
        output_path = figure_output_path(f"production_{material}_h12_vs_iso249.png")
        fig.write_image(
            output_path,
            width=fig.layout.width,
            height=fig.layout.height,
            scale=3,
        )
        if show:
            fig.show()


if __name__ == "__main__":
    main(show=False)
