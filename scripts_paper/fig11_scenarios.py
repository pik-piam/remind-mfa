import argparse
import math
import os
import warnings

import flodym as fd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import scripts_paper._utils as _utils
from scripts_paper._constants import CMAP_5, SCENARIO_LABELS, figure_output_path, get_material_config

os.environ["BROWSER_PATH"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

X_RANGE = [2000, 2100]
X_TICKS = [2000, 2050, 2100]
SCENARIO_COLORS = CMAP_5[::-2]
LINE_WIDTH_SCALE = 1.5
LINE_WIDTH_DEFAULT = 2 * LINE_WIDTH_SCALE
LINE_WIDTH_VLINE = 1.2 * LINE_WIDTH_SCALE
LEGEND_FONT_SIZE = 13
MAXIMUM_LEGENDTEXT_BRIGHTNESS = 0.4


def _legend_name(label: str, color: str) -> str:
    return _utils.legend_name(label, color, MAXIMUM_LEGENDTEXT_BRIGHTNESS)


def _available_runs(config):
    runs = []
    missing_labels = []
    for label, run_name in zip(SCENARIO_LABELS, config.scenario_runs, strict=False):
        if run_name is None:
            missing_labels.append(label)
            continue
        pickle_path = _utils.run_pickle_path(config.directory, run_name)
        if pickle_path.exists():
            runs.append((label, run_name))
        else:
            missing_labels.append(label)
    if not runs:
        raise FileNotFoundError(f"No scenario runs available for material '{config.material}'")
    if missing_labels:
        warnings.warn(
            f"Missing scenario runs for {config.material}: {', '.join(missing_labels)}. "
            "Figure 11 will use the available runs only.",
            stacklevel=2,
        )
    return runs


def _build_comparison_array(config, runs):
    labels = [label for label, _ in runs]
    arrays = []
    for _, run_name in runs:
        mfa = _utils.load_future_mfa(config.directory, run_name)
        arrays.append(mfa.flows[config.production_flow_name])
    new_dim = fd.Dimension(letter="X", name="Run", items=labels)
    return fd.flodym_array_stack(arrays, dimension=new_dim) / 1e9


def _build_comparison_figure(config, array: fd.FlodymArray, aggregate_regions: bool) -> go.Figure:
    data = array.sum_to(("t", "X", "r")).to_df().reset_index()
    data_glob = array.sum_to(("t", "X")).to_df().reset_index()
    time_col = _utils.get_column_name(data, "Time")
    region_col = _utils.get_column_name(data, "Region")
    value_col = _utils.get_column_name(data, "value")

    scenario_candidates = [
        col for col in data.columns if col not in {time_col, region_col, value_col}
    ]
    if len(scenario_candidates) != 1:
        raise KeyError(
            f"Expected exactly one scenario dimension column, found {scenario_candidates}"
        )
    run_col = scenario_candidates[0]

    data[region_col] = data[region_col].astype(str)
    data = _utils.aggregate_region_timeseries(
        data,
        time_col,
        region_col,
        value_col,
        aggregate_regions=aggregate_regions,
    )
    data_glob = data_glob.rename(columns={_utils.get_column_name(data_glob, "value"): value_col})
    world_panel = (
        data_glob.groupby([time_col, run_col], as_index=False)[value_col]
        .sum()
        .sort_values([run_col, time_col])
    )

    present_regions = sorted(set(data[region_col]))
    region_panels = _utils.ordered_regions(
        present_regions,
        reverse=True,
        aggregate_regions=aggregate_regions,
    )
    n_panels = 1 + len(region_panels)
    n_cols = 3 if n_panels <= 6 else 4
    n_rows = math.ceil(n_panels / n_cols)
    subplot_titles = ["<b>World</b>"] + [
        _utils.get_region_label(region, aggregate_regions=aggregate_regions)
        for region in region_panels
    ]

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.10,
        vertical_spacing=0.16 if n_rows <= 2 else 0.10,
    )

    run_color_map = {
        label: SCENARIO_COLORS[index % len(SCENARIO_COLORS)]
        for index, label in enumerate(array.dims["X"].items)
    }
    run_legend_rank = {label: index for index, label in enumerate(array.dims["X"].items)}

    def _panel_position(index: int):
        row = index // n_cols + 1
        col = index % n_cols + 1
        return row, col

    def _add_panel_traces(panel_df, panel_row: int, panel_col: int, legend: bool):
        ordered_runs = list(array.dims["X"].items)
        present_runs = set(panel_df[run_col].astype(str))
        for run_label in reversed([run for run in ordered_runs if run in present_runs]):
            run_df = panel_df[panel_df[run_col].astype(str) == str(run_label)].sort_values(time_col)
            if run_df.empty:
                continue
            line_color = run_color_map[str(run_label)]
            fig.add_trace(
                go.Scatter(
                    x=run_df[time_col],
                    y=run_df[value_col],
                    mode="lines",
                    name=_legend_name(str(run_label), line_color),
                    legendgroup=str(run_label),
                    showlegend=legend,
                    legendrank=run_legend_rank[str(run_label)],
                    line={"color": line_color, "width": LINE_WIDTH_DEFAULT},
                ),
                row=panel_row,
                col=panel_col,
            )

    world_row, world_col = _panel_position(0)
    _add_panel_traces(world_panel, panel_row=world_row, panel_col=world_col, legend=True)
    fig.add_vline(
        x=config.last_historical_year,
        line_dash="dash",
        line_color="black",
        line_width=LINE_WIDTH_VLINE,
        row=world_row,
        col=world_col,
    )

    for panel_index, region_code in enumerate(region_panels, start=1):
        row, col = _panel_position(panel_index)
        region_df = data[data[region_col] == region_code]
        region_panel = (
            region_df.groupby([time_col, run_col], as_index=False)[value_col]
            .sum()
            .sort_values([run_col, time_col])
        )
        _add_panel_traces(region_panel, panel_row=row, panel_col=col, legend=False)
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
            title_text="Year", title_standoff=4, range=X_RANGE, tickmode="array", tickvals=X_TICKS
        )
    )
    fig.for_each_yaxis(lambda axis: axis.update(title_text="", showgrid=True))
    fig.update_layout(
        template="plotly_white",
        width=900 if n_cols == 3 else 1200,
        height=600 if n_rows == 2 else 300 * n_rows,
        margin={"t": 120, "b": 70, "l": 90, "r": 70},
        title={"text": f"<b>{config.material.title()}</b>", "x": 0.5, "xanchor": "center"},
        legend={
            "x": 0.5,
            "y": 1.08,
            "xanchor": "center",
            "yanchor": "bottom",
            "orientation": "h",
            "traceorder": "normal",
            "font": {"size": LEGEND_FONT_SIZE},
            "bordercolor": "black",
            "borderwidth": 1,
        },
    )
    return fig


def main(material: str = "cement", use_h12: bool = False, show: bool = True):
    config = get_material_config(material)
    runs = _available_runs(config)
    comparison_array = _build_comparison_array(config, runs)
    fig = _build_comparison_figure(
        config,
        comparison_array,
        aggregate_regions=not use_h12,
    )
    output_path = figure_output_path(
        f"figure_11_{config.material}_{_utils.region_mode_suffix(use_h12)}.png"
    )
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
    parser.add_argument("--material", choices=["plastics", "steel", "cement"], default="cement")
    parser.add_argument("--h12", action="store_true")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    main(material=args.material, use_h12=args.h12, show=not args.no_show)