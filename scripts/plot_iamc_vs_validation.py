"""Plot a material model's IAMC outputs against the curated validation data.

For every variable that appears in both the model IAMC output and the validation.mif file,
one PNG is produced: region panels (subplots), one colour per source (column "model" of the validation.mif),
one linestyle per scenario.

Usage::

    uv run python scripts/plot_iamc_vs_validation.py                      # plastics, defaults
    uv run python scripts/plot_iamc_vs_validation.py --regions EUR,World  # subset of regions

NOTE: This script is un-reviewed vibe-coding.
"""

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

REPO_ROOT = Path(__file__).resolve().parents[1]

# ID columns of the (wide) IAMC format; everything else is a year column.
ID_COLUMNS = ["model", "scenario", "region", "variable", "unit"]

# The model's own output is highlighted (black, thicker) to stand out from validation sources.
MODEL_PREFIX = "REMIND-MFA"


def _is_model_output(model: str) -> bool:
    return str(model).startswith(MODEL_PREFIX)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--material", default="plastics", help="Material model (default: plastics)."
    )
    parser.add_argument(
        "--iamc",
        default=None,
        help="Model IAMC .xlsx (default: data/<material>/output/export/iamc/output_iamc.xlsx).",
    )
    parser.add_argument(
        "--validation",
        default=str(REPO_ROOT.parent / "remind_mfa_data" / "validation" / "validation.mif"),
        help="Validation .mif file.",
    )
    parser.add_argument(
        "--outdir",
        default=None,
        help="Output folder (default: data/<material>/output/export/iamc/validation_plots).",
    )
    parser.add_argument("--regions", default=None, help="Comma-separated regions to keep.")
    parser.add_argument("--scenarios", default=None, help="Comma-separated scenarios to keep.")
    parser.add_argument("--variables", default=None, help="Comma-separated variables to keep.")
    parser.add_argument("--ncols", type=int, default=4, help="Subplot columns (default: 4).")
    parser.add_argument("--show", action="store_true", help="Also display the figures.")
    return parser.parse_args()


def _melt_to_long(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a wide IAMC DataFrame (lower-cased id columns) to tidy long format."""
    year_cols = [c for c in df.columns if c not in ID_COLUMNS]
    long = df.melt(id_vars=ID_COLUMNS, value_vars=year_cols, var_name="year", value_name="value")
    long["year"] = pd.to_numeric(long["year"], errors="coerce").astype("Int64")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["year", "value"])
    long["year"] = long["year"].astype(int)
    return long


def load_model_iamc(path: Path) -> pd.DataFrame:
    """Load the model IAMC Excel export into tidy long format."""
    df = pd.read_excel(path, sheet_name="data")
    df.columns = [str(c).lower() if str(c).lower() in ID_COLUMNS else str(c) for c in df.columns]
    return _melt_to_long(df)


def load_validation(path: Path) -> pd.DataFrame:
    """Load the validation .mif (semicolon-separated, trailing ';', 'N/A' missing) into long format."""
    df = pd.read_csv(path, sep=";", na_values=["N/A"])
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    df.columns = [str(c).lower() if str(c).lower() in ID_COLUMNS else str(c) for c in df.columns]
    return _melt_to_long(df)


def build_style_maps(df: pd.DataFrame) -> tuple[dict, dict]:
    """Map each model to a colour and each (model, scenario) to a linestyle.

    Colour distinguishes models; linestyle distinguishes scenarios *within* a model. Because
    scenarios barely overlap across models, linestyles are reset per model, so only as many
    distinct linestyles as the largest scenario count of any single model are ever needed.
    """
    models = sorted(df["model"].unique())
    palette = list(plt.get_cmap("tab10").colors)
    model_color = {m: palette[i % len(palette)] for i, m in enumerate(models)}
    # Highlight the model's own output in black so it stands out from the validation sources.
    for m in models:
        if _is_model_output(m):
            model_color[m] = "black"

    base_styles = ["-", "--", "-.", ":"]
    dash_styles = [(0, d) for d in [(3, 1, 1, 1), (5, 2), (1, 1), (5, 1, 1, 1, 1, 1), (2, 2, 6, 2)]]
    linestyles = base_styles + dash_styles
    combo_style = {}
    for model in models:
        scenarios = sorted(df[df["model"] == model]["scenario"].unique())
        for i, scenario in enumerate(scenarios):
            combo_style[(model, scenario)] = linestyles[i % len(linestyles)]
    return model_color, combo_style


def _sanitize(name: str) -> str:
    for ch in "|/\\ :":
        name = name.replace(ch, "_")
    while "__" in name:
        name = name.replace("__", "_")
    return name.strip("_")


def plot_variable(
    sub: pd.DataFrame,
    display_name: str,
    model_color: dict,
    combo_style: dict,
    ncols: int,
    outdir: Path,
    show: bool,
) -> None:
    """Produce one figure (region panels) for a single variable and save it as PNG."""
    regions = sorted(sub["region"].unique())
    if "World" in regions:
        regions = ["World"] + [r for r in regions if r != "World"]

    ncols = min(ncols, len(regions))
    nrows = math.ceil(len(regions) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.2 * nrows), sharex=True)
    axes = list(axes.flat) if hasattr(axes, "flat") else [axes]

    for ax, region in zip(axes, regions):
        region_df = sub[sub["region"] == region]
        for (model, scenario), grp in region_df.groupby(["model", "scenario"]):
            grp = grp.sort_values("year")
            ax.plot(
                grp["year"],
                grp["value"],
                color=model_color[model],
                linestyle=combo_style[(model, scenario)],
                linewidth=2.4 if _is_model_output(model) else 1.4,
                zorder=3 if _is_model_output(model) else 2,
            )
        ax.set_title(region)
        ax.grid(True, alpha=0.3)
    for ax in axes[len(regions) :]:
        ax.set_visible(False)

    unit = sub["unit"].dropna().unique()
    unit_str = unit[0] if len(unit) else ""
    fig.suptitle(f"{display_name}  [{unit_str}]", fontsize=13)

    # One proxy-artist legend per line: colour = model, linestyle = scenario, grouped by model.
    combos_here = sorted(set(map(tuple, sub[["model", "scenario"]].drop_duplicates().values)))
    combo_handles = [
        Line2D(
            [],
            [],
            color=model_color[model],
            linestyle=combo_style[(model, scenario)],
            lw=2.4 if _is_model_output(model) else 1.6,
            label=f"{model} | {scenario}",
        )
        for model, scenario in combos_here
    ]
    fig.legend(
        handles=combo_handles,
        title="Model | Scenario",
        loc="upper left",
        bbox_to_anchor=(1.0, 0.98),
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0, 0.82, 0.96))

    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"{_sanitize(display_name)}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"  saved {out_path.relative_to(REPO_ROOT)}")
    if show:
        plt.show()
    plt.close(fig)


def main() -> None:
    args = _parse_args()

    iamc_path = Path(
        args.iamc
        or REPO_ROOT / "data" / args.material / "output" / "export" / "iamc" / "output_iamc.xlsx"
    )
    outdir = Path(
        args.outdir
        or REPO_ROOT / "data" / args.material / "output" / "export" / "iamc" / "validation_plots"
    )

    model_df = load_model_iamc(iamc_path)
    validation_df = load_validation(Path(args.validation))

    # Overlapping variables, matched case-insensitively; keep model's original casing for display.
    model_keys = {v.lower(): v for v in model_df["variable"].unique()}
    validation_keys = set(validation_df["variable"].str.lower().unique())
    overlap_keys = sorted(set(model_keys) & validation_keys)

    combined = pd.concat([model_df, validation_df], ignore_index=True)
    combined["_vkey"] = combined["variable"].str.lower()

    if args.variables:
        wanted = {v.strip().lower() for v in args.variables.split(",")}
        overlap_keys = [k for k in overlap_keys if k in wanted]
    if args.regions:
        keep = {r.strip() for r in args.regions.split(",")}
        combined = combined[combined["region"].isin(keep)]
    if args.scenarios:
        keep = {s.strip() for s in args.scenarios.split(",")}
        combined = combined[combined["scenario"].isin(keep)]

    if not overlap_keys:
        print("No overlapping variables to plot.")
        return

    model_color, combo_style = build_style_maps(combined)

    print(f"Plotting {len(overlap_keys)} variable(s) to {outdir.relative_to(REPO_ROOT)}:")
    for key in overlap_keys:
        sub = combined[combined["_vkey"] == key]
        if sub.empty:
            continue
        plot_variable(sub, model_keys[key], model_color, combo_style, args.ncols, outdir, args.show)


if __name__ == "__main__":
    main()
