import marimo

__generated_with = "0.23.15"
app = marimo.App()


@app.cell
def _():
    import dotenv
    import marimo as mo
    from flodym.export import GraphvizProcessGraphPlotter

    from run_remind_mfa import init_model, read_model_config

    dotenv.load_dotenv()

    graphs = []
    for historic in [True, False]:
        graphs.append(mo.md(f"# MFA {'Historic' if historic else 'Future'}"))
        for model_name in ["steel", "cement", "plastics"]:
            model_config = read_model_config(f"config/{model_name}.yml")
            model = init_model(cfg=model_config)
            mfa = model.make_mfa(historic=historic)
            dot = GraphvizProcessGraphPlotter(mfa=mfa, rankdir="LR").plot()
            graphs.append(mo.md(f"## {model_name.capitalize()}"))
            graphs.append(dot)

    mo.vstack(graphs)
    return


if __name__ == "__main__":
    app.run()
