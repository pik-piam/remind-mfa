import marimo

__generated_with = "0.24.0"
app = marimo.App()


@app.cell
def _():
    from remind_mfa.common.helpers import ModelNames
    import dotenv
    import marimo as mo
    from pathlib import Path
    from flodym.export import GraphvizProcessGraphPlotter

    from remind_mfa.common.helpers import init_model
    from remind_mfa.common.config_loader import load_config

    dotenv.load_dotenv()
    CONFIG_PATH = Path(__file__).parents[1] / "config" / "default.toml"

    graphs = []
    for historic in [True, False]:
        graphs.append(mo.md(f"# MFA {'Historic' if historic else 'Future'}"))
        for model_name in ModelNames:
            model_config = load_config([CONFIG_PATH], model_name)
            model = init_model(cfg=model_config)
            mfa = model.make_mfa(historic=historic)
            dot = GraphvizProcessGraphPlotter(mfa=mfa, rankdir="LR").plot()
            graphs.append(mo.md(f"## {model_name.capitalize()}"))
            graphs.append(dot)

    mo.vstack(graphs)
    return


if __name__ == "__main__":
    app.run()
