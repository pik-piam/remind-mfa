import argparse
import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import _utils
from _constants import CMAP_5, figure_output_path, get_material_config

X_RANGE = [2000, 2100]
X_TICKS = [2000, 2050, 2100]
LINE_WIDTH_SCALE = 1.5
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 1.2 * LINE_WIDTH_SCALE
AXIS_LABEL_FONT_SIZE = 14
LEFT_COLUMN_Y_LABEL_X = -0.075
SERIES_COLOR = CMAP_5[2]
STEEL_CONFIG = get_material_config("steel")
PLOT_CONFIG = {
    "gdppc": {
        "source_name": "gdppc",
        "output_prefix": "gdppc",
        "y_axis_title": "GDP per capita ($/cap/yr)",
        "scale": 1,
    },
    "population": {
        "source_name": "population",
        "output_prefix": "pop",
        "y_axis_title": "Population (bn people)",
        "scale": 1e9,
    },
}


def _load_parameter_df(parameter_name: str, aggregate_regions: bool):
    model = _utils.load_model(STEEL_CONFIG.material)
    df = model.parameters[parameter_name].to_df().reset_index()
    time_col = _utils.get_column_name(df, "Time")
    region_col = _utils.get_column_name(df, "Region")
    value_col = _utils.get_column_name(df, "value")
    df = _utils.aggregate_region_timeseries(
        df,
        time_col,
        region_col,
        value_col,
        aggregate_regions=aggregate_regions,
    )
    return df, time_col, region_col, value_col


def _panel_position(index: int, n_cols: int):
    row = index // n_cols + 1
    col = index % n_cols + 1
    return row, col


def _yaxis_layout_name(row: int, col: int, n_cols: int) -> str:
    axis_index = (row - 1) * n_cols + col
    return "yaxis" if axis_index == 1 else f"yaxis{axis_index}"


def _build_figure(parameter_name: str, aggregate_regions: bool) -> go.Figure:
    plot_config = PLOT_CONFIG[parameter_name]
    data, time_col, region_col, value_col = _load_parameter_df(
        plot_config["source_name"],
        aggregate_regions=aggregate_regions,
    )
    data[value_col] = data[value_col] / plot_config["scale"]

    region_panels = _utils.ordered_regions(
        sorted(set(data[region_col].astype(str))),
        reverse=True,
        aggregate_regions=aggregate_regions,
    )
    n_panels = len(region_panels)
    n_cols = 3 if n_panels <= 6 else 4
    n_rows = math.ceil(n_panels / n_cols)
    subplot_titles = [
        _utils.get_region_label(region, aggregate_regions=aggregate_regions)
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
        region_df = data[data[region_col].astype(str) == str(region_code)].sort_values(time_col)
        if region_df.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=region_df[time_col],
                y=region_df[value_col],
                mode="lines",
                showlegend=False,
                line={"color": SERIES_COLOR, "width": LINE_WIDTH_DEFAULT},
            ),
            row=row,
            col=col,
        )
        fig.add_vline(
            x=STEEL_CONFIG.last_historical_year,
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
            tickmode="array",
            tickvals=X_TICKS,
        )
    )
    fig.for_each_yaxis(lambda axis: axis.update(title_text="", showgrid=True))

    for row in range(1, n_rows + 1):
        yaxis = getattr(fig.layout, _yaxis_layout_name(row=row, col=1, n_cols=n_cols), None)
        if yaxis is None or yaxis.domain is None:
            continue
        y0, y1 = yaxis.domain
        fig.add_annotation(
            x=LEFT_COLUMN_Y_LABEL_X,
            y=0.5 * (y0 + y1),
            xref="paper",
            yref="paper",
            text=plot_config["y_axis_title"],
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
        margin={"t": 80, "b": 70, "l": 90, "r": 50},
        showlegend=False,
    )
    return fig


def main(use_h12: bool = False, show: bool = True):
    for parameter_name, plot_config in PLOT_CONFIG.items():
        fig = _build_figure(parameter_name, aggregate_regions=not use_h12)
        output_path = figure_output_path(
            f"{plot_config['output_prefix']}_{_utils.region_mode_suffix(use_h12)}.png"
        )
        fig.write_image(
            output_path,
            width=fig.layout.width,
            height=fig.layout.height,
            scale=3,
        )
        if show:
            fig.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--h12", action="store_true")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    main(use_h12=args.h12, show=not args.no_show)
