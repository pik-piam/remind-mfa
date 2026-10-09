import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # SSP3 trade with and without the trade factor

    SSP3 reduces future trade through the scenario parameter `trade_factor` (see
    `config/scenarios/SSP3.csv`). This notebook runs the selected model twice in SSP3:

    - **new**: with the scenario trade factor
    - **old**: with the trade factor set to 1 after parameter extrapolation, i.e. the behaviour
      before the trade factor was introduced

    and compares global and regional imports and exports of all trade markets.
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
    import logging

    import marimo as mo
    import pandas as pd
    import plotly.express as px

    from remind_mfa.common.common_model import CommonModel
    from remind_mfa.common.config_loader import load_config
    from remind_mfa.common.helpers import ModelNames, init_model

    logging.getLogger().setLevel(logging.ERROR)
    return CommonModel, ModelNames, init_model, load_config, mo, pd, px


@app.cell
def _(mo):
    # resolve against the notebook file, so the working directory does not matter
    repo_root = mo.notebook_dir().parent
    return (repo_root,)


@app.cell
def _(ModelNames, mo):
    model_picker = mo.ui.dropdown(
        options=[model.value for model in ModelNames], value="cement", label="Model"
    )
    model_picker
    return (model_picker,)


@app.cell
def _(CommonModel, ModelNames, init_model, load_config, mo, pd, repo_root):
    def run_ssp3(model_name: str, use_trade_factor: bool) -> CommonModel:
        """Run a model in the SSP3 scenario.

        Args:
            model_name: Name of the model to run.
            use_trade_factor: Whether to apply the scenario trade factor. If False, the factor
                is set to 1 after every parameter extrapolation.

        Returns:
            The model after running.
        """
        cfg = load_config(
            ["default", "ci"],
            ModelNames(model_name),
            config_dir=repo_root / "config",
            root_dir=repo_root,
        )
        cfg["model_switches"]["scenario"] = "SSP3"
        model = init_model(cfg=cfg)
        if not use_trade_factor:
            extrapolate_parameters = model.extrapolate_parameters

            def extrapolate_without_trade_factor() -> None:
                extrapolate_parameters()
                model.parameters["trade_factor"][...] = 1.0

            model.extrapolate_parameters = extrapolate_without_trade_factor
        model.run()
        return model

    @mo.cache
    def get_trade(model_name: str) -> pd.DataFrame:
        """Run old and new SSP3 and collect the future trade of all markets.

        Args:
            model_name: Name of the model to run.

        Returns:
            Long-format frame with columns `Case`, `Market`, `Flow`, `Time`, `Region`, `value`.
        """
        frames = []
        for case, use_trade_factor in [("new", True), ("old", False)]:
            model = run_ssp3(model_name, use_trade_factor)
            for market, trade in model.future_mfa.trade_set.markets.items():
                for flow in ("imports", "exports"):
                    values = getattr(trade, flow).sum_to(("t", "r")).to_df(index=False)
                    values.columns = ["Time", "Region", "value"]
                    frames.append(values.assign(Case=case, Market=market, Flow=flow))
        return pd.concat(frames, ignore_index=True)

    with mo.status.spinner(title="Running SSP3 with and without trade factor..."):
        trade = get_trade(model_picker.value)
    return (trade,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Global trade
    """)
    return


@app.cell
def _(px, trade):
    global_trade = trade.groupby(["Case", "Market", "Flow", "Time"], as_index=False)["value"].sum()
    px.line(
        global_trade,
        x="Time",
        y="value",
        color="Case",
        line_dash="Flow",
        facet_col="Market",
        title="Global trade",
    ).update_yaxes(matches=None, showticklabels=True)
    return (global_trade,)


@app.cell
def _(global_trade, px):
    ratio = global_trade.pivot_table(
        index=["Market", "Flow", "Time"], columns="Case", values="value"
    ).reset_index()
    ratio["new / old"] = ratio["new"] / ratio["old"]
    px.line(
        ratio,
        x="Time",
        y="new / old",
        color="Market",
        line_dash="Flow",
        title="Ratio of global trade, new / old",
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Regional trade
    """)
    return


@app.cell
def _(mo, trade):
    market_picker = mo.ui.dropdown(
        options=sorted(trade["Market"].unique()),
        value=sorted(trade["Market"].unique())[0],
        label="Market",
    )
    market_picker
    return (market_picker,)


@app.cell
def _(market_picker, px, trade):
    px.line(
        trade[trade["Market"] == market_picker.value],
        x="Time",
        y="value",
        color="Case",
        line_dash="Flow",
        facet_col="Region",
        facet_col_wrap=4,
        height=900,
        title=f"Regional {market_picker.value} trade",
    ).update_yaxes(matches=None, showticklabels=True)
    return


if __name__ == "__main__":
    app.run()
