import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # ATLAS trade: history, projection and interpolation

    In the second MFA run of the ATLAS coupling (`config/atlas_run2.toml`), future trade of the
    primary market is read from the ATLAS output instead of being extrapolated. ATLAS projects in
    5-year steps, so the MFA interpolates linearly in between, starting from the last historic year
    (`set_trade_from_data` in `remind_mfa/common/trade.py`).

    This notebook shows, per region:

    - the **historic trade**, i.e. the historic trade parameter, balanced as in the historic MFA,
    - the **ATLAS projection**, as written by `atlas.py copy-trade`,
    - the **interpolated trade** that the MFA uses in the future, computed with the same function.

    The future MFA may adjust the historic trade further before use (e.g. capping net imports at
    the domestic demand), so its historic values can differ slightly.

    Run `atlas.py future` and `atlas.py copy-trade` first. The input data folder is taken from the
    configuration; a different one can be passed with `-- --input-data-path <path>`.
    """)
    return


@app.cell
def _(mo):
    mo.md("This notebook is completely AI generated, with very little human checking!").callout(
        kind="danger", title="AI Disclaimer"
    )
    return


@app.cell
def _():
    from pathlib import Path

    import flodym as fd
    import marimo as mo
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    from remind_mfa.atlas_coupling import PROJECT_ROOT, get_model_spec
    from remind_mfa.common.common_data_reader import MadratParameterReader
    from remind_mfa.common.config_loader import load_config
    from remind_mfa.common.helpers import ModelNames, get_model_class
    from remind_mfa.common.trade import Trade, set_trade_from_data

    return (
        MadratParameterReader,
        ModelNames,
        PROJECT_ROOT,
        Path,
        Trade,
        fd,
        get_model_class,
        get_model_spec,
        go,
        load_config,
        make_subplots,
        mo,
        pd,
        set_trade_from_data,
    )


@app.cell
def _(ModelNames, mo):
    model_picker = mo.ui.dropdown(
        options={"steel": ModelNames.STEEL, "plastics": ModelNames.PLASTICS},
        value="steel",
        label="Model",
    )
    flow_picker = mo.ui.radio(
        options=["imports", "exports"], value="imports", label="Flow", inline=True
    )
    balance_switch = mo.ui.switch(
        value=False, label="Balance global imports and exports, as the MFA does"
    )
    start_year_slider = mo.ui.slider(
        start=1900, stop=2020, step=5, value=2000, label="Show from", show_value=True
    )
    mo.hstack(
        [model_picker, flow_picker, balance_switch, start_year_slider], justify="start", gap=2
    )
    return balance_switch, flow_picker, model_picker, start_year_slider


@app.cell
def _(PROJECT_ROOT, Path, get_model_class, get_model_spec, load_config, mo, model_picker):
    model = model_picker.value
    spec = get_model_spec(model)
    cfg = get_model_class(model).ConfigCls.model_validate(
        load_config(["default", "atlas_run2"], model)
    )
    input_data_path = (
        Path(mo.cli_args()["input-data-path"]).resolve()
        if "input-data-path" in mo.cli_args()
        else PROJECT_ROOT / cfg.input.input_data_path
    )
    parameters_path = input_data_path / "parameters"
    dimensions_path = input_data_path / "dimensions" / model.value

    # names of the historic trade parameters of the primary market, without prefix and flow
    HISTORIC_MARKET = {"steel": "steel", "plastics": "primary_his"}

    def parameter_path(name: str, flow: str) -> Path:
        return parameters_path / f"{spec.parameter_prefix}_{name}_{flow}.cs4r"

    historic_paths = {
        flow: parameter_path(HISTORIC_MARKET[model.value], flow) for flow in ("imports", "exports")
    }
    atlas_paths = {
        flow: parameter_path(f"trade_{spec.trade_market}", flow) for flow in ("imports", "exports")
    }
    return atlas_paths, cfg, dimensions_path, historic_paths, model, spec


@app.cell
def _(MadratParameterReader, Path, atlas_paths, historic_paths, mo, pd):
    missing = [
        path for path in [*historic_paths.values(), *atlas_paths.values()] if not path.exists()
    ]
    mo.stop(
        bool(missing),
        mo.md(
            "Missing input files:\n\n"
            + "\n".join(f"- `{path}`" for path in missing)
            + "\n\nHistoric parameters are extracted by any MFA run, the ATLAS projection is "
            "written by `uv run atlas.py copy-trade --model <model>`."
        ).callout(kind="warn"),
    )

    def read_cs4r(path: Path) -> pd.DataFrame:
        """Read a .cs4r parameter file with the column names given in its header, as the MFA does."""
        header, skiprows = MadratParameterReader.extract_cs4r_info(path)
        return pd.read_csv(path, names=header, skiprows=skiprows)

    historic_data = {flow: read_cs4r(path) for flow, path in historic_paths.items()}
    atlas_data = {flow: read_cs4r(path) for flow, path in atlas_paths.items()}
    return atlas_data, historic_data


@app.cell
def _(dimensions_path, fd, historic_data):
    def read_years(filename: str) -> list[int]:
        return [int(year) for year in (dimensions_path / filename).read_text().split()]

    # dimension letters as in the MFA definitions
    LETTERS = {"Region": "r", "Type": "p", "Material": "m"}
    category_dims = [
        fd.Dimension(
            name=name, letter=letter, items=sorted(historic_data["imports"][name].unique())
        )
        for name, letter in LETTERS.items()
        if name in historic_data["imports"].columns
    ]
    historic_dims = fd.DimensionSet(
        dim_list=[
            fd.Dimension(name="Historic Time", letter="h", items=read_years("historic_years.csv")),
            *category_dims,
        ]
    )
    future_dims = fd.DimensionSet(
        dim_list=[
            fd.Dimension(name="Time", letter="t", items=read_years("time_in_years.csv")),
            *category_dims,
        ]
    )
    return future_dims, historic_dims


@app.cell
def _(
    Trade,
    atlas_data,
    balance_switch,
    cfg,
    fd,
    future_dims,
    historic_data,
    historic_dims,
    set_trade_from_data,
    spec,
):
    def to_trade(data: dict, dims: fd.DimensionSet) -> Trade:
        # missing rows are read as zero, like in the MFA
        return Trade(
            **{
                flow: fd.FlodymArray.from_df(dims, data[flow], allow_missing_values=True)
                for flow in ("imports", "exports")
            }
        )

    historic_trade = to_trade(historic_data, historic_dims)
    historic_trade.balance(to="maximum")  # as in the historic MFA
    atlas_trade = to_trade(atlas_data, future_dims)
    future_trade = Trade(
        imports=fd.FlodymArray(dims=future_dims), exports=fd.FlodymArray(dims=future_dims)
    )
    set_trade_from_data(
        future_trade,
        atlas_trade.imports,
        atlas_trade.exports,
        historic_trade,
        balance_to=cfg.trade.balance if balance_switch.value else None,
        market_name=spec.trade_market,
    )
    return future_trade, historic_trade


@app.cell
def _(atlas_data, fd, flow_picker, future_trade, historic_dims, historic_trade, pd):
    def by_region(array: fd.FlodymArray, time_letter: str) -> pd.DataFrame:
        """Values of the given array per year and region, in Mt."""
        df = array.sum_to((time_letter, "r")).to_df().reset_index()
        df.columns = ["Year", "Region", "value"]
        return df.assign(value=df["value"] / 1e6)

    flow = flow_picker.value
    last_historic_year = max(historic_dims["h"].items)
    historic_series = by_region(getattr(historic_trade, flow), "h")
    # only the years actually contained in the ATLAS output
    atlas_series = (
        atlas_data[flow]
        .groupby(["Time", "Region"], as_index=False)["value"]
        .sum()
        .rename(columns={"Time": "Year"})
        .assign(value=lambda df: df["value"] / 1e6)
    )
    interpolated_series = by_region(getattr(future_trade, flow), "t").query(
        "Year >= @last_historic_year"
    )
    return atlas_series, flow, historic_series, interpolated_series, last_historic_year


@app.cell
def _(atlas_series, flow, interpolated_series, last_historic_year, mo, model):
    atlas_years = sorted(atlas_series["Year"].unique())
    interpolated_years = sorted(
        set(interpolated_series["Year"]) - set(atlas_years) - {last_historic_year}
    )
    mo.md(f"""
    **{model.value}, {flow}:** historic data ends in {last_historic_year}. ATLAS covers the years
    {", ".join(map(str, atlas_years))}; the MFA interpolates the other
    {len(interpolated_years)} future years.
    """)
    return


@app.cell
def _(
    atlas_series,
    flow,
    go,
    historic_series,
    interpolated_series,
    make_subplots,
    model,
    start_year_slider,
):
    # categorical slots 1-3 of the dataviz reference palette
    SERIES = {
        "Historic": dict(data=historic_series, color="#2a78d6", mode="lines", dash="solid"),
        "Interpolated (MFA)": dict(
            data=interpolated_series, color="#1baf7a", mode="lines", dash="dash"
        ),
        "ATLAS": dict(data=atlas_series, color="#eb6834", mode="markers", dash=None),
    }
    regions = sorted(historic_series["Region"].unique())
    n_columns = 4
    n_rows = -(-len(regions) // n_columns)
    figure = make_subplots(
        rows=n_rows,
        cols=n_columns,
        subplot_titles=regions,
        shared_xaxes=True,
        vertical_spacing=0.08,
        horizontal_spacing=0.06,
    )
    for index, region in enumerate(regions):
        for name, series in SERIES.items():
            region_data = series["data"].query("Region == @region")
            figure.add_trace(
                go.Scatter(
                    x=region_data["Year"],
                    y=region_data["value"],
                    name=name,
                    legendgroup=name,
                    showlegend=index == 0,
                    mode=series["mode"],
                    line=dict(color=series["color"], width=2, dash=series["dash"]),
                    marker=dict(color=series["color"], size=8),
                    hovertemplate=f"{name}<br>%{{x}}: %{{y:.2f}} Mt<extra>{region}</extra>",
                ),
                row=index // n_columns + 1,
                col=index % n_columns + 1,
            )
    figure.update_xaxes(range=[start_year_slider.value, interpolated_series["Year"].max() + 1])
    figure.update_yaxes(rangemode="tozero")
    figure.update_layout(
        title=f"{model.value.capitalize()} {flow} per region (Mt)",
        height=260 * n_rows,
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0),
        hovermode="closest",
        margin=dict(t=110),
    )
    figure
    return


@app.cell
def _(atlas_series, interpolated_series, mo):
    future_table = (
        atlas_series.rename(columns={"value": "ATLAS"})
        .merge(
            interpolated_series.rename(columns={"value": "Interpolated (MFA)"}),
            on=["Year", "Region"],
            how="right",
        )
        .sort_values(["Region", "Year"])
        .round(3)
    )
    mo.ui.table(future_table, label="Future trade per region (Mt)")
    return


if __name__ == "__main__":
    app.run()
