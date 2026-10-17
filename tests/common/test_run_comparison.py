import os
import pickle
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flodym as fd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from plotly.subplots import make_subplots

from remind_mfa.common.common_config import (
    BaseVisualizationCfg,
    ConsumptionVisualizationCfg,
    GDPVisualizationCfg,
    SankeyVisualizationCfg,
    StockVisualizationCfg,
)
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.helpers import ModelNames
from remind_mfa.common.run_comparison import (
    CHANGE_COLUMN,
    REGION_COLUMN,
    WORLD,
    YEAR_COLUMN,
    ChangeVerdict,
    ChartType,
    LoadedRun,
    RunInfo,
    aligned,
    apply_filters,
    build_frame,
    change_heatmap,
    clean_title,
    common_variables,
    default_label,
    difference_figure,
    discover_runs,
    figure_change,
    format_change,
    frame_figures,
    get_array,
    get_variable,
    is_changed,
    is_sankey,
    list_variables,
    load_run,
    model_name,
    ordered_items,
    overlay_figures,
    peak_change,
    plot_toggles,
    regional_changes,
    section_title,
    stored_fields,
    summarize_changes,
    unique_labels,
    verdict_markdown,
    visualization_cfg,
    with_world,
)
from remind_mfa.steel.steel_config import SteelVisualizationCfg

T = fd.Dimension(name="Time", letter="t", items=[2020, 2050])
R = fd.Dimension(name="Region", letter="r", items=["EUR", "USA"])
G = fd.Dimension(name="Good", letter="g", items=["Construction", "Machinery"])
DIMS = fd.DimensionSet(dim_list=[T, R, G])

# 1, 2, 4, 8, ... so that every partial sum identifies its summands
VALUES = 2.0 ** np.arange(8).reshape(2, 2, 2)


class _FakeStock:
    def __init__(self, stock, inflow):
        self.stock = stock
        self.inflow = inflow
        self.outflow = None


class _FakeMFA:
    """Minimal stand-in for a `CommonMFASystem`, exposing only what the module reads."""

    def __init__(self, factor: float = 1.0, extra_flow: bool = False, flow_factor: float = 1.0):
        array = fd.FlodymArray(dims=DIMS, values=VALUES * factor, name="demand")
        flow = fd.FlodymArray(dims=DIMS, values=VALUES * factor * flow_factor, name="demand")
        self.flows = {"fabrication => good_market": flow}
        if extra_flow:
            self.flows["forming => scrap_market"] = array
        self.stocks = {"in_use": _FakeStock(stock=array, inflow=array)}
        # deliberately without the Good dimension, like the real population parameter
        self.parameters = {
            "population": fd.FlodymArray(
                dims=fd.DimensionSet(dim_list=[T, R]),
                values=VALUES.sum(axis=2) * factor,
                name="population",
            )
        }
        self.trade_set = None


class _FakeModel(CommonModel):
    """Minimal stand-in for a pickled model: a `CommonModel` without reading any data."""

    def __init__(self, factor: float = 1.0, extra_flow: bool = False, flow_factor: float = 1.0):
        self.future_mfa = _FakeMFA(factor=factor, extra_flow=extra_flow, flow_factor=flow_factor)
        self.cfg = SimpleNamespace(model=ModelNames.STEEL)


def _run(label: str, **kwargs) -> LoadedRun:
    return LoadedRun(path=Path(f"{label}/model.pickle"), label=label, data=_FakeModel(**kwargs))


@pytest.fixture
def runs() -> list[LoadedRun]:
    return [_run("SSP2"), _run("SSP1", factor=10.0)]


@pytest.fixture
def tidy(runs) -> pd.DataFrame:
    return build_frame(runs, ["flow: fabrication => good_market"])


# ── loading ────────────────────────────────────────────────────────────────────


def test_default_label_is_the_run_directory():
    path = Path("data_out/2026-09-07--12-23-18_steel_SSP2_h12/model.pickle")
    assert default_label(path) == "2026-09-07--12-23-18_steel_SSP2_h12"


def test_default_label_falls_back_to_the_file_name():
    assert default_label(Path("some_run.pickle")) == "some_run"


def _touch(path: Path, timestamp: float) -> Path:
    path.parent.mkdir(parents=True)
    path.touch()
    os.utime(path, (timestamp, timestamp))
    return path


def test_discover_runs_describes_the_runs_newest_first(tmp_path):
    older = _touch(tmp_path / "2026-09-07--12-23-18_steel_SSP2_h12" / "model.pickle", 1e9)
    newer = _touch(tmp_path / "ci_series" / "ci_cement_SSP1_eu21" / "model.pickle", 2e9)
    _touch(tmp_path / "other" / "notes.txt", 3e9)

    runs = discover_runs(tmp_path)

    assert [run.path for run in runs] == [newer, older]
    assert runs[0] == RunInfo(
        path=newer,
        display_path="ci_series/ci_cement_SSP1_eu21",
        label="ci_cement_SSP1_eu21",
        modified=datetime.fromtimestamp(2e9),
        model="cement",
        scenario="SSP1",
        region_mapping="eu21",
    )
    assert (runs[1].model, runs[1].scenario, runs[1].region_mapping) == ("steel", "SSP2", "h12")
    # a run directory stands for its pickle
    assert RunInfo.from_path(older.parent, tmp_path) == runs[1]


def test_run_info_of_a_run_elsewhere(tmp_path):
    workbook = _touch(tmp_path / "my_prefix_plastics_SSP2_high_h12" / "output_iamc.xlsx", 1e9)
    run = RunInfo.from_path(workbook, data_root=tmp_path / "data_out", label="custom")
    # outside the data root the whole path is shown
    assert run.display_path == str(workbook)
    assert run.label == "custom"
    # prefix and scenario may contain underscores
    assert (run.model, run.scenario, run.region_mapping) == ("plastics", "SSP2_high", "h12")
    unnamed = RunInfo.from_path(_touch(tmp_path / "some_run" / "model.pickle", 1e9))
    assert (unnamed.model, unnamed.scenario, unnamed.region_mapping) == (None, None, None)
    with pytest.raises(FileNotFoundError):
        RunInfo.from_path(tmp_path / "missing" / "model.pickle")


def test_unique_labels_disambiguates_repetitions():
    assert unique_labels(["a", "b", "a"]) == ["a", "b", "a (2)"]


def test_load_run_reads_a_model_pickle(tmp_path):
    run_dir = tmp_path / "2026-09-07--12-23-18_steel_SSP2_h12"
    run_dir.mkdir()
    with (run_dir / "model.pickle").open("wb") as file_handle:
        pickle.dump(_FakeModel(), file_handle)

    run = load_run(run_dir / "model.pickle")

    assert run.label == run_dir.name
    assert run.is_model
    assert model_name(run) == "steel"
    assert list(run.mfa.flows) == ["fabrication => good_market"]
    assert load_run(run_dir / "model.pickle", label="custom").label == "custom"


def test_load_run_rejects_pickles_that_are_not_models(tmp_path):
    with (tmp_path / "model.pickle").open("wb") as file_handle:
        pickle.dump({"flows": {}}, file_handle)
    with pytest.raises(RuntimeError, match="does not contain"):
        load_run(tmp_path / "model.pickle")


def test_with_label_keeps_the_data(runs):
    relabelled = runs[0].with_label("reference")
    assert relabelled.label == "reference"
    assert relabelled.data is runs[0].data
    assert runs[0].label == "SSP2"


def test_model_accessors_reject_other_sources():
    run = LoadedRun(path=Path("output_iamc.xlsx"), label="iamc", data=cast(Any, SimpleNamespace()))
    assert not run.is_model
    with pytest.raises(TypeError, match="model pickle"):
        _ = run.mfa


# ── variables and tidy frames ──────────────────────────────────────────────────


def test_list_variables_qualifies_names_by_kind(runs):
    # the fake stock has no outflow, so it offers no "stock outflow" variable
    assert list_variables(runs[0]) == [
        "flow: fabrication => good_market",
        "stock: in_use",
        "stock inflow: in_use",
        "parameter: population",
    ]


def test_common_variables_are_the_intersection():
    runs = [_run("without"), _run("with", extra_flow=True)]
    assert common_variables(runs) == list_variables(runs[0])
    assert common_variables(runs[::-1]) == list_variables(runs[0])


def test_get_array_returns_the_flodym_array(runs):
    array = get_array(runs[0], "stock inflow: in_use")
    assert isinstance(array, fd.FlodymArray)
    assert array.dims.letters == ("t", "r", "g")


def test_get_variable_returns_one_column_per_dimension(runs):
    df = get_variable(runs[0], "flow: fabrication => good_market")
    assert list(df.columns) == ["Time", "Region", "Good", "value"]
    assert len(df) == VALUES.size


def test_get_variable_rejects_unknown_names(runs):
    with pytest.raises(KeyError, match="SSP2"):
        get_variable(runs[0], "flow: does not exist")


def test_build_tidy_stacks_runs(runs, tidy):
    assert list(tidy.columns) == ["Run", "Variable", "Time", "Region", "Good", "value"]
    assert len(tidy) == 2 * VALUES.size
    # the run column keeps the given order, which drives the plotting order
    assert list(tidy["Run"].cat.categories) == ["SSP2", "SSP1"]
    assert tidy.groupby("Run", observed=True)["value"].sum().to_dict() == {
        "SSP2": VALUES.sum(),
        "SSP1": 10 * VALUES.sum(),
    }


def test_apply_filters_ignores_empty_and_unknown_selections(tidy):
    filtered = apply_filters(tidy, {"Good": ["Machinery"], "Region": [], "Nonexistent": ["x"]})
    assert set(filtered["Good"]) == {"Machinery"}
    assert set(filtered["Region"]) == {"EUR", "USA"}


def test_ordered_items_returns_builtin_types(tidy):
    # numpy scalars leak into UI controls as "np.int64(2020)", so they must not be returned
    years = ordered_items(tidy["Time"])
    assert years == [2020, 2050]
    assert all(type(year) is int for year in years)


def test_ordered_items_follow_an_explicit_category_order(tidy):
    assert ordered_items(tidy["Run"]) == ["SSP2", "SSP1"]


def test_with_world_prepends_the_sum_over_regions(tidy):
    combined = with_world(tidy)
    assert list(combined["Region"].cat.categories) == [WORLD, "EUR", "USA"]
    world = combined.query("Region == @WORLD")
    assert len(world) == len(tidy) // 2  # one row per run, year and good
    assert world["value"].sum() == pytest.approx(tidy["value"].sum())


def test_with_world_reuses_an_existing_world_region(tidy):
    reported = tidy.copy()
    reported.loc[reported["Region"] == "EUR", "Region"] = WORLD
    combined = with_world(reported)
    # the reported rows are kept as they are, rather than summed with the other regions
    assert len(combined) == len(tidy)
    assert list(combined["Region"].cat.categories) == [WORLD, "USA"]


def test_frame_figures_draw_one_aligned_figure_per_run(tidy):
    figures = frame_figures(
        with_world(tidy), x="Time", color="Good", facet="Region", title="Demand", ylabel="t"
    )

    assert list(figures) == ["SSP2", "SSP1"]
    reference, other = figures.values()
    assert aligned(reference, other)
    assert _subplot_titles(reference) == [WORLD, "EUR", "USA"]
    assert [trace.name for trace in reference.data[:2]] == ["Construction", "Machinery"]
    # an item has the same colour in every subplot
    assert reference.data[0].line.color == reference.data[2].line.color
    assert reference.data[0].line.color != reference.data[1].line.color
    # construction in EUR is the first value of each year: 1 in 2020, 16 in 2050
    assert list(reference.data[2].y) == [1.0, 16.0]
    assert list(other.data[2].y) == [10.0, 160.0]
    assert reference.layout.title.text == "Demand"
    assert reference.layout.yaxis.title.text == "t"


def test_frame_figures_sum_over_unmapped_dimensions(tidy):
    # a summed region dimension takes the World rows rather than adding them to the regions
    for frame in (tidy, with_world(tidy)):
        (trace,) = frame_figures(frame, x="Time")["SSP2"].data
        assert list(trace.y) == [15.0, 240.0]


def test_frame_figures_fill_items_a_run_lacks_with_nan(tidy):
    incomplete = tidy[~((tidy["Run"] == "SSP1") & (tidy["Good"] == "Machinery"))]
    figures = frame_figures(incomplete, x="Time", color="Good")
    assert aligned(figures["SSP2"], figures["SSP1"])
    assert np.isnan(figures["SSP1"].data[1].y).all()


def test_frame_figures_keep_variables_that_lack_a_mapped_dimension(runs):
    # the population parameter has no Good dimension, so its rows carry NaN there; they must
    # still show up when Good is mapped to the lines
    mixed = build_frame(runs, ["flow: fabrication => good_market", "parameter: population"])
    traces = frame_figures(mixed, x="Time", color="Good", facet="Variable")["SSP2"].data
    assert [trace.name for trace in traces] == ["Construction", "Machinery", "nan"] * 2
    assert list(traces[5].y) == [15.0, 240.0]


def test_frame_figures_stack_shares(tidy):
    construction, machinery = frame_figures(
        tidy, x="Time", color="Good", chart_type=ChartType.AREA, shares=True
    )["SSP2"].data
    assert (construction.fill, machinery.fill) == ("tozeroy", "tonexty")
    # construction is 1 + 4 of 15 in 2020 and 16 + 64 of 240 in 2050; the stack ends at 100 %
    assert list(construction.y) == pytest.approx([100 / 3, 100 / 3])
    assert list(machinery.y) == pytest.approx([100.0, 100.0])


def test_frame_figures_draw_bars_and_markers(tidy):
    stacked = frame_figures(tidy, x="Time", color="Good", chart_type=ChartType.BAR_STACKED)
    grouped = frame_figures(tidy, x="Time", color="Good", chart_type=ChartType.BAR_GROUPED)
    scatter = frame_figures(tidy, x="Time", color="Good", chart_type=ChartType.SCATTER)

    construction = stacked["SSP2"].data[0]
    assert construction.type == "bar"
    # the bars hold the layers, not cumulative values; the layout stacks them
    assert list(construction.x) == ["2020", "2050"] and list(construction.y) == [5.0, 80.0]
    assert stacked["SSP2"].layout.barmode == "stack"
    assert construction.offsetgroup is None
    assert grouped["SSP2"].layout.barmode == "group"
    assert [trace.offsetgroup for trace in grouped["SSP2"].data] == ["Construction", "Machinery"]
    assert {trace.mode for trace in scatter["SSP2"].data} == {"markers"}


def test_frame_figures_reject_ambiguous_or_empty_selections(tidy):
    with pytest.raises(ValueError, match="only go to one"):
        frame_figures(tidy, x="Time", color="Good", facet="Good")
    with pytest.raises(ValueError, match="empty"):
        frame_figures(tidy.iloc[:0], x="Time")


def test_clean_title():
    assert clean_title("Region=LAM") == "LAM"
    assert clean_title("Steel production  regional") == "Steel production regional"
    assert clean_title("flow: forming => ip_market") == "flow: forming => ip_market"
    assert clean_title(None) == ""


# ── visualization config for headless re-plotting ──────────────────────────────


def _steel_visualization_cfg() -> SteelVisualizationCfg:
    """A steel visualization config as a model run would store it: showing and saving figures."""
    return SteelVisualizationCfg(
        do_show_figs=True,
        do_save_figs_html=True,
        use_stock=StockVisualizationCfg(per_capita=True, over_gdp=True),
        gdp=GDPVisualizationCfg(do_visualize=False),
        production=BaseVisualizationCfg(),
        trade=BaseVisualizationCfg(do_visualize=False),
        consumption=ConsumptionVisualizationCfg(),
        sankey=SankeyVisualizationCfg(do_visualize=False),
        extrapolation=BaseVisualizationCfg(),
        sector_splits=BaseVisualizationCfg(do_visualize=False),
        scrap_demand_supply=BaseVisualizationCfg(do_visualize=False),
    )


def test_visualization_cfg_plots_headlessly_and_keeps_the_settings():
    cfg = visualization_cfg(_steel_visualization_cfg())
    assert type(cfg) is SteelVisualizationCfg
    assert (cfg.do_visualize, cfg.do_show_figs, cfg.do_save_figs, cfg.do_save_figs_html) == (
        True,
        False,
        False,
        False,
    )
    assert cfg.use_stock.per_capita and cfg.use_stock.over_gdp
    assert not cfg.trade.do_visualize


def test_visualization_cfg_switches_plot_groups():
    cfg = visualization_cfg(_steel_visualization_cfg(), plots={"trade": True, "use_stock": False})
    assert cfg.trade.do_visualize
    assert not cfg.use_stock.do_visualize
    assert cfg.use_stock.per_capita  # other settings of the group are kept
    with pytest.raises(KeyError, match="Unknown plot group"):
        visualization_cfg(_steel_visualization_cfg(), plots={"nonexistent": True})


def test_visualization_cfg_fills_fields_missing_from_old_pickles():
    # a config unpickled from an older run lacks the fields added since, both plain settings
    # and whole plot groups; accessing them raises
    old = _steel_visualization_cfg()
    del old.__dict__["do_save_figs_html"]
    del old.__dict__["scrap_demand_supply"]
    with pytest.raises(AttributeError):
        _ = old.do_save_figs_html
    stored = stored_fields(old)
    assert "do_save_figs_html" not in stored and "scrap_demand_supply" not in stored
    assert stored["use_stock"] == {
        "do_visualize": True,
        "per_capita": True,
        "over_gdp": True,
        "accumulate_gdp": False,
    }

    cfg = visualization_cfg(old, plots={"scrap_demand_supply": True})

    assert type(cfg) is SteelVisualizationCfg
    assert not cfg.do_save_figs_html  # filled with the default, then forced off
    assert cfg.scrap_demand_supply.do_visualize  # filled with the default, then switched on
    assert not cfg.gdp.do_visualize  # kept from the stored config


def test_plot_toggles_list_the_plot_groups():
    toggles = plot_toggles(_steel_visualization_cfg())
    assert toggles == {
        "use_stock": True,
        "gdp": False,
        "production": True,
        "trade": False,
        "consumption": True,
        "sankey": False,
        "extrapolation": True,
        "sector_splits": False,
        "scrap_demand_supply": False,
    }


# ── merging standard figures ───────────────────────────────────────────────────


def _standard_figure(factor: float = 1.0) -> go.Figure:
    """A figure shaped like the visualizers' output: lines, stacked areas and markers on two
    subplots."""
    fig = make_subplots(rows=1, cols=2, subplot_titles=["EUR", "USA"])
    years = [2020, 2030, 2050]
    fig.add_trace(
        go.Scatter(
            x=years,
            y=np.array([1.0, 2.0, 4.0]) * factor,
            name="EUR",
            line=dict(color="red", dash="solid"),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=np.array([1.0, 2.0, 4.0]) * factor,
            name="EUR",
            line=dict(color="red", dash="dot"),
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=years[-1:], y=[4.0 * factor], name="EUR", mode="markers", marker=dict(color="black")
        ),
        row=1,
        col=1,
    )
    # stacked area: cumulative values of the layers [1, 1, 1] and [1, 2, 3]
    fig.add_trace(
        go.Scatter(
            x=years,
            y=np.array([1.0, 1.0, 1.0]) * factor,
            name="Construction",
            fill="tozeroy",
            line=dict(color="blue"),
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=np.array([2.0, 3.0, 4.0]) * factor,
            name="Machinery",
            fill="tonexty",
            line=dict(color="green"),
        ),
        row=1,
        col=2,
    )
    fig.update_layout(title_text="Stocks")
    fig.update_yaxes(title_text="Stock [t]")
    return fig


def _subplot_titles(fig: go.Figure) -> list[str]:
    return [annotation.text for annotation in fig.layout.annotations]


def _lines_figure(n_subplots: int, n_series: int, factor: float = 1.0) -> go.Figure:
    """``n_series`` lines, e.g. one per region, in each of ``n_subplots`` subplots."""
    titles = [f"Good=G{index}" for index in range(n_subplots)] if n_subplots > 1 else None
    fig = make_subplots(rows=1, cols=n_subplots, subplot_titles=titles)
    for column in range(1, n_subplots + 1):
        for series in range(n_series):
            fig.add_trace(
                go.Scatter(x=[2020, 2050], y=np.array([1.0, 2.0]) * factor, name=f"R{series}"),
                row=1,
                col=column,
            )
    return fig


def test_overlay_draws_the_reference_as_a_faded_ghost():
    reference, other = _standard_figure(), _standard_figure(factor=2.0)
    fig = overlay_figures([reference, other], ["base", "new"])

    # per subplot the reference goes first, so it lies behind and a stack stays together
    eur_reference, eur_other = fig.data[0:3], fig.data[3:6]
    area_reference, area_other = fig.data[6:8], fig.data[8:10]
    for trace in [*eur_reference, *area_reference]:
        assert trace.name.endswith(" · base")
    assert [trace.name for trace in eur_other] == ["EUR · new"] * 3
    # faded, wide and solid, whatever the line style of the other run on top
    for trace in eur_reference[:2]:
        assert trace.opacity == pytest.approx(0.3)
        assert trace.line.dash == "solid"
    assert [trace.line.dash for trace in eur_other[:2]] == ["solid", "dot"]
    assert eur_reference[0].line.width > eur_other[0].line.width
    # stacked areas: the reference stays filled, faded; the other run becomes outlines
    assert all(trace.fill for trace in area_reference)
    assert area_reference[0].fillcolor == "rgba(0, 0, 255, 0.3)"
    assert all(trace.fill is None for trace in area_other)
    assert [trace.line.color for trace in eur_other] == ["red", "red", None]
    assert fig.layout.title.text == "Stocks"
    assert _subplot_titles(fig) == ["EUR", "USA"]
    # the inputs are left untouched
    assert len(reference.data) == 5 and other.data[1].line.dash == "dot"


def test_overlay_legend_identifies_the_series_and_keys_the_runs():
    fig = overlay_figures([_standard_figure(), _standard_figure(factor=2.0)], ["base", "new"])

    entries = [trace for trace in fig.data if trace.showlegend]
    assert [trace.name for trace in entries] == ["base", "new", "EUR", "Construction", "Machinery"]
    # clicking a series toggles it in both runs; the run key cannot toggle anything
    assert {trace.legendgroup for trace in fig.data[:10]} == {"EUR", "Construction", "Machinery"}
    assert [trace.legend for trace in entries[:2]] == ["legend2", "legend2"]
    assert fig.layout.legend2.itemclick is False


def test_overlay_splits_crowded_subplots_into_one_per_series():
    fig = overlay_figures([_lines_figure(1, 6), _lines_figure(1, 6, factor=2.0)], ["base", "new"])

    assert _subplot_titles(fig) == [f"R{series}" for series in range(6)]
    # each subplot compares one series of both runs
    assert [trace.name for trace in fig.data[:2]] == ["R0 · base", "R0 · new"]
    assert fig.data[0].xaxis == fig.data[1].xaxis != fig.data[2].xaxis
    # the subplot titles tell the series apart, so the legend toggles the runs
    assert [trace.name for trace in fig.data if trace.showlegend] == ["base", "new"]
    assert {trace.legendgroup for trace in fig.data} == {"base", "new"}


def test_overlay_splits_a_small_grid_into_rows_of_series():
    fig = overlay_figures([_lines_figure(2, 6), _lines_figure(2, 6, factor=2.0)], ["base", "new"])

    # one column per original subplot, one row per series
    assert _subplot_titles(fig)[:4] == ["G0 · R0", "G1 · R0", "G0 · R1", "G1 · R1"]


def test_overlay_keeps_stacked_areas_together():
    fig = make_subplots(rows=1, cols=1)
    for layer in range(6):
        fig.add_trace(
            go.Scatter(
                x=[2020, 2050], y=[layer + 1.0, layer + 2.0], name=f"L{layer}", fill="tonexty"
            )
        )
    overlay = overlay_figures([fig, fig], ["base", "new"])
    assert {(trace.xaxis, trace.yaxis) for trace in overlay.data} == {("x", "y")}


def test_overlay_keeps_the_layout_if_splitting_takes_too_many_subplots():
    many = _lines_figure(10, 6)  # 60 series in total
    fig = overlay_figures([many, many], ["base", "new"])
    assert _subplot_titles(fig) == [f"G{index}" for index in range(10)]


def test_merging_copes_with_empty_figures():
    empty = go.Figure(layout=dict(title_text="Nothing"))
    assert overlay_figures([empty, empty], ["base", "new"]).layout.title.text == "Nothing"
    difference = difference_figure([empty, empty], ["base", "new"])
    assert difference is not None and len(difference.data) == 0


def test_overlay_gives_further_runs_a_line_style_of_their_own():
    figures = [_lines_figure(1, 2, factor=factor) for factor in (1.0, 2.0, 3.0)]
    fig = overlay_figures(figures, ["base", "new", "newer"])

    # the reference ghosts first, then each run
    assert [trace.name for trace in fig.data[:6]] == [
        f"{series} · {run}" for run in ("base", "new", "newer") for series in ("R0", "R1")
    ]
    assert [trace.line.dash for trace in fig.data[2:6]] == [None, None, "dash", "dash"]
    run_key = [trace for trace in fig.data if trace.showlegend and trace.legend == "legend2"]
    assert [(trace.name, trace.line.dash) for trace in run_key] == [
        ("base", None),
        ("new", None),
        ("newer", "dash"),
    ]


def test_overlay_puts_the_runs_bars_side_by_side(tidy):
    figures = frame_figures(tidy, x="Time", color="Good", chart_type=ChartType.BAR_STACKED)
    fig = overlay_figures(list(figures.values()), list(figures))

    assert fig.layout.barmode == "stack"
    bars = [trace for trace in fig.data if trace.type == "bar"]
    # one place per year and run, labelled with the run on the second level of the x axis
    assert [list(level) for level in bars[0].x] == [["2020", "2050"], ["SSP2", "SSP2"]]
    assert [list(level) for level in bars[2].x] == [["2020", "2050"], ["SSP1", "SSP1"]]
    assert [trace.opacity for trace in bars] == [0.3, 0.3, None, None]
    run_key = [trace for trace in fig.data if trace.showlegend and trace.legend == "legend2"]
    assert [trace.marker.symbol for trace in run_key] == ["square", "square"]


def test_overlay_keeps_stacked_bars_together():
    goods = [f"G{index}" for index in range(6)]
    df = pd.DataFrame(
        {"Run": "base", "Time": 2020, "Good": goods, "value": np.arange(6, dtype=float)}
    )
    figures = frame_figures(df, x="Time", color="Good", chart_type=ChartType.BAR_STACKED)
    figure = figures["base"]
    fig = overlay_figures([figure, figure], ["base", "new"])
    assert {(trace.xaxis, trace.yaxis) for trace in fig.data} == {("x", "y")}


def test_overlay_gives_further_runs_a_marker_symbol_of_their_own(tidy):
    runs = pd.concat([tidy, tidy.assign(Run="SSP5")], ignore_index=True)
    figures = frame_figures(runs, x="Time", chart_type=ChartType.SCATTER)
    fig = overlay_figures(list(figures.values()), list(figures))

    assert [trace.marker.symbol for trace in fig.data[:3]] == [None, None, "diamond"]
    run_key = [trace for trace in fig.data if trace.showlegend]
    assert [trace.marker.symbol for trace in run_key] == ["circle", "circle", "diamond"]
    assert run_key[0].marker.opacity == pytest.approx(0.3)


def test_overlay_of_a_single_run_draws_it_as_it_is():
    fig = overlay_figures([_lines_figure(1, 2)], ["base"])
    assert all(trace.opacity is None for trace in fig.data)
    assert [trace.name for trace in fig.data if trace.showlegend] == ["R0", "R1"]


def test_overlay_pairs_subplots_by_title():
    reference = _standard_figure()
    other = make_subplots(rows=1, cols=2, subplot_titles=["USA", "EUR"])
    for trace, column in zip(_standard_figure(factor=2.0).data, (2, 2, 2, 1, 1)):
        other.add_trace(trace, row=1, col=column)
    fig = overlay_figures([reference, other], ["base", "new"])

    eur_axes = {(trace.xaxis, trace.yaxis) for trace in fig.data if trace.name.startswith("EUR")}
    assert len(eur_axes) == 1


def test_aligned_requires_matching_traces():
    assert aligned(_standard_figure(), _standard_figure(factor=3.0))
    renamed = _standard_figure()
    renamed.data[0].name = "USA"
    assert not aligned(_standard_figure(), renamed)
    shorter = _standard_figure()
    shorter.data[0].y = shorter.data[0].y[:-1]
    assert not aligned(_standard_figure(), shorter)
    assert not aligned(_standard_figure(), go.Figure(go.Sankey()))


def test_difference_figure_is_relative_by_default():
    fig = difference_figure([_standard_figure(), _standard_figure(factor=2.0)], ["base", "new"])

    assert fig is not None
    assert list(fig.data[0].y) == pytest.approx([100.0, 100.0, 100.0])
    assert fig.layout.title.text == "Stocks"
    assert fig.layout.title.subtitle.text == "new minus base, in % of base"
    # axis titles only along the left edge, where they do not run into the neighbour
    assert fig.layout.yaxis.title.text == "difference [%]"
    assert fig.layout.yaxis2.title.text is None
    assert all(trace.fill is None for trace in fig.data)
    assert [trace.name for trace in fig.data if trace.showlegend] == [
        "EUR",
        "Construction",
        "Machinery",
    ]


def test_difference_figure_unstacks_areas_and_can_be_absolute():
    other = _standard_figure()
    # second layer grows from [1, 2, 3] to [2, 2, 3]: cumulative values [3, 3, 4]
    other.data[4].y = np.array([3.0, 3.0, 4.0])
    fig = difference_figure([_standard_figure(), other], ["base", "new"], relative=False)

    assert fig is not None
    assert list(fig.data[3].y) == pytest.approx([0.0, 0.0, 0.0])  # first layer unchanged
    assert list(fig.data[4].y) == pytest.approx([1.0, 0.0, 0.0])  # not [1, 0, 0] of cumulative
    assert fig.layout.title.subtitle.text == "new minus base"
    assert fig.layout.yaxis.title.text == "Δ Stock [t]"


def test_difference_figure_is_undefined_where_the_reference_is_zero():
    reference = _standard_figure()
    reference.data[0].y = np.array([0.0, 2.0, 4.0])
    fig = difference_figure([reference, _standard_figure(factor=2.0)], ["base", "new"])
    assert fig is not None
    assert np.isnan(fig.data[0].y[0])
    assert list(fig.data[0].y[1:]) == pytest.approx([100.0, 100.0])


def test_difference_figure_needs_aligned_traces():
    renamed = _standard_figure()
    renamed.data[0].name = "USA"
    assert difference_figure([_standard_figure(), renamed], ["base", "new"]) is None


def test_difference_figure_of_several_runs_keys_the_runs():
    figures = [_lines_figure(1, 1, factor=factor) for factor in (1.0, 2.0, 3.0)]
    fig = difference_figure(figures, ["base", "new", "newer"])

    assert fig is not None
    assert [list(trace.y) for trace in fig.data[:2]] == [[100.0, 100.0], [200.0, 200.0]]
    assert [trace.line.dash for trace in fig.data[:2]] == [None, "dash"]
    assert fig.layout.title.subtitle.text == "new, newer minus base, in % of base"
    # a single series needs no legend, so the legend keys (and toggles) the runs
    assert [trace.name for trace in fig.data if trace.showlegend] == ["new", "newer"]
    assert difference_figure(figures[:1], ["base"]) is None


def test_difference_figure_unstacks_bars_side_by_side(tidy):
    runs = pd.concat([tidy, tidy.assign(Run="SSP5")], ignore_index=True)
    figures = frame_figures(runs, x="Time", color="Good", chart_type=ChartType.BAR_STACKED)
    fig = difference_figure(list(figures.values()), list(figures), relative=False)

    assert fig is not None
    assert fig.layout.barmode == "group"
    construction, machinery = fig.data[:2]
    # SSP1 is ten times SSP2: construction grows by 9 * (1 + 4) and 9 * (16 + 64)
    assert list(construction.y) == pytest.approx([45.0, 720.0])
    assert (construction.offsetgroup, machinery.offsetgroup) == ("Construction", "Machinery")
    # with several runs compared, their bars stand side by side under their names
    assert list(construction.x[1]) == ["SSP1", "SSP1"]
    assert list(fig.data[2].x[1]) == ["SSP5", "SSP5"]


def test_merged_figures_are_rounded_to_six_significant_digits():
    reference, other = _standard_figure(), _standard_figure(factor=1.2345678912345)
    fig = overlay_figures([reference, other], ["base", "new"])
    added_line = fig.data[3]
    assert list(added_line.y) == [1.23457, 2.46914, 4.93827]
    assert list(added_line.x) == [2020, 2030, 2050]  # integers are left alone
    difference = difference_figure([reference, other], ["base", "new"])
    assert difference is not None
    assert list(difference.data[0].y) == [23.4568, 23.4568, 23.4568]
    # the inputs keep their precision
    assert other.data[0].y[0] == pytest.approx(1.2345678912345, rel=1e-12)


def test_is_sankey():
    assert is_sankey(go.Figure(go.Sankey()))
    assert not is_sankey(_standard_figure())


# ── change detection ───────────────────────────────────────────────────────────


def test_peak_change_is_signed_and_scaled_to_the_largest_reference():
    assert peak_change(np.array([1.0, 2.0, 4.0]), np.array([1.0, 2.0, 2.0])) == (-50.0, 2)
    assert peak_change(np.array([1.0, 2.0, 4.0]), np.array([1.0, 3.0, 4.0])) == (25.0, 1)
    change, _ = peak_change(np.zeros(3), np.zeros(3))
    assert np.isnan(change)
    assert peak_change(np.zeros(3), np.array([0.0, 0.0, 2.0])) == (np.inf, 2)


def test_is_changed_applies_the_tolerance():
    assert not is_changed(0.0)
    assert not is_changed(1e-8)  # a change of 1e-10 relative, below the tolerance of 1e-9
    assert not is_changed(np.nan)
    assert is_changed(1e-6)
    assert is_changed(-1e-6)
    assert is_changed(np.inf)


def test_format_change():
    assert format_change(200.0) == "+200 %"
    assert format_change(-32.123) == "−32.1 %"
    assert format_change(-32.123, signed=False) == "32.1 %"
    assert format_change(12345.6) == "+12,346 %"
    assert format_change(np.inf) == "new (reference is zero)"
    assert format_change(np.nan) == "unchanged"


def test_regional_changes_has_the_world_and_every_region(runs):
    changes = regional_changes(*runs)

    assert list(changes.columns) == [
        "Variable",
        REGION_COLUMN,
        CHANGE_COLUMN,
        YEAR_COLUMN,
        "SSP2",
        "SSP1",
    ]
    assert changes["Variable"].nunique() == 3  # flow, stock, stock inflow
    assert list(changes[REGION_COLUMN].unique()) == [WORLD, "EUR", "USA"]
    assert len(changes) == 9
    # SSP1 is ten times SSP2 everywhere; the values grow with time, so 2050 is the peak
    assert changes[CHANGE_COLUMN].to_list() == pytest.approx([900.0] * 9)
    assert set(changes[YEAR_COLUMN]) == {2050}


def test_regional_changes_carry_the_values_in_the_year_of_the_change():
    changes = regional_changes(_run("base"), _run("new", flow_factor=3.0))
    flow = changes[changes["Variable"] == "flow: fabrication => good_market"]
    # 2050 holds the second half of the values (16 + 32 + 64 + 128), 16 + 32 of them in EUR
    assert flow[[REGION_COLUMN, YEAR_COLUMN, "base", "new"]].to_numpy().tolist() == [
        [WORLD, 2050, 240.0, 720.0],
        ["EUR", 2050, 48.0, 144.0],
        ["USA", 2050, 192.0, 576.0],
    ]


def test_regional_changes_without_a_region_dimension():
    reference, other = _run("a"), _run("b", factor=2.0)
    for run, scale in ((reference, 1.0), (other, 2.0)):
        run.model.future_mfa.parameters["global"] = fd.FlodymArray(
            dims=fd.DimensionSet(dim_list=[T]), values=np.array([1.0, 2.0]) * scale, name="global"
        )
    changes = regional_changes(reference, other, groups=("parameter",))
    global_rows = changes[changes["Variable"] == "parameter: global"]
    assert list(global_rows[REGION_COLUMN]) == [WORLD]
    population_rows = changes[changes["Variable"] == "parameter: population"]
    assert list(population_rows[REGION_COLUMN]) == [WORLD, "EUR", "USA"]


def test_regional_changes_are_signed():
    changes = regional_changes(_run("a"), _run("b", flow_factor=0.5))
    by_variable = changes.groupby("Variable")[CHANGE_COLUMN].unique()
    assert by_variable["flow: fabrication => good_market"].tolist() == pytest.approx([-50.0])
    assert by_variable["stock: in_use"].tolist() == pytest.approx([0.0])


def test_verdict_identical_within_tolerance():
    assert summarize_changes(regional_changes(_run("a"), _run("b"))).identical
    noisy = summarize_changes(regional_changes(_run("a"), _run("b", factor=1 + 1e-12)))
    assert noisy.identical
    line = verdict_markdown(noisy, "cement")
    assert line.startswith("**cement**: numerically identical (3 variables agree")


def test_verdict_names_the_largest_change():
    change_verdict = summarize_changes(regional_changes(_run("a"), _run("b", flow_factor=3.0)))

    assert change_verdict == ChangeVerdict(
        n_variables=3,
        n_changed=1,
        largest_variable="flow: fabrication => good_market",
        largest_change=200.0,
        largest_region=WORLD,  # ties go to the world total, which comes first
        largest_year=2050,
    )
    assert verdict_markdown(change_verdict, "steel") == (
        "**steel**: 1 of 3 variables changed, largest `flow: fabrication => good_market` "
        "+200 % (World, 2050)"
    )


def test_verdict_counts_regional_changes_that_cancel_globally():
    reference, other = _run("a"), _run("b")
    flow = other.model.future_mfa.flows["fabrication => good_market"]
    # move material from USA to EUR in 2050 (axes: time, region, good)
    flow.values[1, 0, :] += 1.0
    flow.values[1, 1, :] -= 1.0
    change_verdict = summarize_changes(regional_changes(reference, other))
    assert change_verdict.n_changed == 1
    assert change_verdict.largest_region in ("EUR", "USA")


def test_figure_change_measures_the_largest_trace_change():
    assert figure_change(_standard_figure(), _standard_figure()) == 0.0
    assert figure_change(_standard_figure(), _standard_figure(factor=2.0)) == pytest.approx(100.0)
    other = _standard_figure()
    other.data[4].y = np.array([3.0, 3.0, 4.0])  # second layer [1, 2, 3] -> [2, 2, 3]
    assert figure_change(_standard_figure(), other) == pytest.approx(100 / 3)
    renamed = _standard_figure()
    renamed.data[0].name = "USA"
    assert figure_change(_standard_figure(), renamed) is None
    assert figure_change(go.Figure(), go.Figure()) == 0.0


def test_section_title_carries_the_change():
    assert section_title("Stocks", 0.0) == "Stocks"
    assert section_title("Stocks", 32.14) == "Stocks — max Δ 32.1 %"
    assert section_title("Stocks", np.inf) == "Stocks — values where the reference has none"
    assert section_title("Stocks", None) == "Stocks — traces differ"


def _changes_frame(n_variables: int) -> pd.DataFrame:
    rows = []
    for index in range(n_variables):
        for region, change in ((WORLD, float(index)), ("EUR", -float(index) * 2)):
            rows.append(
                {
                    "Variable": f"flow: v{index}",
                    REGION_COLUMN: region,
                    CHANGE_COLUMN: change,
                    YEAR_COLUMN: 2050,
                }
            )
    return pd.DataFrame(rows)


def test_change_heatmap_ranks_clips_and_scales():
    changes = _changes_frame(35)
    changes.loc[changes["Variable"] == "flow: v3", CHANGE_COLUMN] = np.inf
    fig = change_heatmap(changes)
    heatmap = fig.data[0]

    assert list(heatmap.y)[:2] == ["flow: v3", "flow: v34"]  # new values rank first
    assert len(heatmap.y) == 30
    assert list(heatmap.x) == [WORLD, "EUR"]
    assert (heatmap.zmin, heatmap.zmax) == (-50.0, 50.0)
    assert np.asarray(heatmap.z)[0, 0] == 50.0  # inf clipped to the scale
    assert np.asarray(heatmap.z)[1, 1] == -50.0  # -68 clipped
    assert fig.layout.height > change_heatmap(_changes_frame(5)).layout.height
    assert "new (reference is zero)" in heatmap.customdata[0][0]


def test_change_heatmap_needs_a_change():
    with pytest.raises(ValueError, match="no variable changed"):
        change_heatmap(_changes_frame(1))  # v0 has change 0 everywhere
