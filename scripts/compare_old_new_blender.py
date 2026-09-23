"""Compare in-use stock, consumption, and production between two model runs
(here: the 'old' 2nd-order blender on `main` vs. the 'new' critically damped
blender on `development/update-blender`), each pickled as a full CommonModel,
for cement, steel, and plastics.

For each material and quantity, produces one global (region-summed) figure
and one regional (subplot-per-region) figure, with old/new overlaid as two
lines.
"""

import pickle
from pathlib import Path

import flodym as fd
import flodym.export as fde

OLD_DIR = Path("data_out_compare/old")
NEW_DIR = Path("data_out_compare/new")
OUT_DIR = Path("data_out_compare/figures")

RUN_DIM = fd.Dimension(letter="X", name="Run", items=["old", "new"])

# One quantity-extraction function per material, each returning (t, r) FlodymArrays.
QUANTITY_BUILDERS = {
    "cement": lambda mfa: {
        "stock": mfa.stocks["in_use"].stock[{"k": "cement"}].sum_to(("t", "r")),
        "consumption": mfa.stocks["in_use"].inflow[{"k": "cement"}].sum_to(("t", "r")),
        "production": mfa.flows["prod_cement => market_cement"].sum_to(("t", "r")),
    },
    "steel": lambda mfa: {
        "stock": mfa.stocks["in_use"].stock.sum_to(("t", "r")),
        "consumption": mfa.stocks["in_use"].inflow.sum_to(("t", "r")),
        "production": (
            mfa.flows["bof_production => forming"] + mfa.flows["eaf_production => forming"]
        ).sum_to(("t", "r")),
    },
    "plastics": lambda mfa: {
        "stock": mfa.stocks["in_use"].stock.sum_to(("t", "r")),
        "consumption": mfa.stocks["in_use"].inflow.sum_to(("t", "r")),
        "production": (
            mfa.flows["polymerization => primary_market"]
            + mfa.flows["aux_recyclate_trade => primary_market"]
        ).sum_to(("t", "r")),
    },
}


def find_pickle(base_dir: Path, material: str) -> Path:
    matches = sorted(base_dir.glob(f"*_{material}_*/model.pickle"))
    if not matches:
        raise FileNotFoundError(f"No model.pickle found for material={material!r} under {base_dir}")
    return matches[-1]


def load_future_mfa(path: Path):
    with path.open("rb") as f:
        model = pickle.load(f)
    return model.future_mfa


def make_figure(array: fd.FlodymArray, material: str, name: str, regional: bool, out_dir: Path):
    subplot_dim = "r" if regional else None
    tag = "regional" if regional else "global"
    array_to_plot = array if regional else array.sum_over("r")

    plotter = fde.PlotlyArrayPlotter(
        array=array_to_plot,
        intra_line_dim="t",
        linecolor_dim="X",
        subplot_dim=subplot_dim,
        title=f"{material.capitalize()} {name} [t] ({tag}) — old vs. new blender",
        xlabel="Year",
        ylabel=f"{name} [t]",
    )
    fig = plotter.plot()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{material}_{name}_{tag}.html"
    fig.write_html(out_path, include_plotlyjs=True)
    print(f"Wrote {out_path}")


def main():
    for material, build_quantities in QUANTITY_BUILDERS.items():
        old_mfa = load_future_mfa(find_pickle(OLD_DIR, material))
        new_mfa = load_future_mfa(find_pickle(NEW_DIR, material))

        old_quantities = build_quantities(old_mfa)
        new_quantities = build_quantities(new_mfa)

        for name in ("stock", "consumption", "production"):
            stacked = fd.flodym_array_stack(
                [old_quantities[name], new_quantities[name]], dimension=RUN_DIM
            )
            make_figure(stacked, material, name, regional=False, out_dir=OUT_DIR)
            make_figure(stacked, material, name, regional=True, out_dir=OUT_DIR)


if __name__ == "__main__":
    main()
