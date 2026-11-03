"""Map OPEN-GEM (TRANSIENCE partner CGE model) trade ratios onto REMIND-MFA dimensions and write
.cs4r files.

OPEN-GEM reports sectoral trade in monetary terms (b$ 2017). Since the sector scope does not match
the REMIND-MFA goods 1:1 and the material intensity of the economic value can change over time,
the monetary flows are not translated into tonnes. Instead, the model aligns the *change* of the
EU trade ratios to OPEN-GEM (see `OpenGemTradeAligner`). This script provides these ratios:

    manufactured products:  IMPORTS / DEMAND,  EXPORTS / DEMAND   (per REMIND-MFA end use)
    steel scrap:            IMPORTS / PROD,    EXPORTS / PROD

Scrap trade is driven by the collected (domestic) supply in REMIND-MFA, so its ratios use the
production of the OPEN-GEM recycling sector as the denominator. Plastics waste trade is a scenario
parameter in REMIND-MFA (phased out in the BASE scenario) and therefore not aligned. The OPEN-GEM
sectors are assigned to REMIND-MFA trade markets and goods by `sector_mapping_OPEN_GEM.xlsx`;
several sectors in one mapping row (e.g. 'IND12+13') are summed before taking the ratio.

Region handling
---------------
The OPEN-GEM `EU27` row holds extra-EU trade and EU demand/production. It is written to the
REMIND-MFA EU region (EUR, i.e. EU28). Since only relative changes of the ratios are used in the
model, the level difference between EU27 and EU28 drops out, but trends may differ slightly.

Time handling
-------------
OPEN-GEM reports 5-year steps (2017, 2025, ..., 2050). The ratios are interpolated linearly to
annual values on the model's Time dimension, held constant at the first reported value before and
at the last reported value after the reported period.

Scenarios
---------
The OPEN-GEM scenarios match the TRANSIENCE (EU-MFA) scenarios. SCENARIOS maps each TRANSIENCE
scenario to its sheet SECTOR_<OPEN-GEM scenario> in the OPEN-GEM report, and the files are written
next to the EU-MFA files of that scenario, so that `transience.transience_scenario` selects both.

Output: data_in/legacy/transience/<TRANSIENCE scenario>/
        {st,pl}_{imports,exports}_ratio_<market>_OPEN-GEM.cs4r

Usage:
    uv run --no-sync python scripts/map_OPEN-GEM_trade.py [--material steel] [--scenario X]
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

TRANSIENCE_INPUT = Path("data_in/legacy/transience_input")
DEFAULT_REPORT = TRANSIENCE_INPUT / "OPEN_GEM_REPORT_v20261016.xlsx"
DEFAULT_MAPPING = TRANSIENCE_INPUT / "sector_mapping_OPEN_GEM.xlsx"
OUTPUT_ROOT = Path("data_in/legacy/transience")
DIMENSION_ROOT = Path("data_in/dimensions")

OG_REGION = "EU27"
# region of the REMIND-MFA Region dimension the OPEN-GEM EU values are written to
# (same as EU_MFA_REGION in remind_mfa.common.common_definition; not imported to keep the script
# free of the model imports)
TARGET_EU_REGION = "EUR"

MATERIALS = ["steel", "plastics"]
# TRANSIENCE scenario -> OPEN-GEM scenario (sheet SECTOR_<OPEN-GEM scenario>), per material
SCENARIOS = {
    "steel": {"BASE_steel_combined": "BASE"},
    "plastics": {"BASE_plastics_combined": "BASE"},
}
PREFIX = {"steel": "st", "plastics": "pl"}
# (material, trade category in the mapping) -> (REMIND-MFA trade market, OPEN-GEM denominator)
MARKETS = {
    ("steel", "manufactured products"): ("manufactured_products", "DEMAND"),
    ("steel", "scrap"): ("scrap", "PROD"),
    ("plastics", "manufactured products"): ("manufactured_products", "DEMAND"),
    # plastics waste trade is a scenario parameter in REMIND-MFA and not aligned to OPEN-GEM
}


def split_og_sectors(cell: str) -> list[str]:
    """'IND12+13' -> ['IND12', 'IND13'];  'IND33' -> ['IND33']."""
    parts = [p.strip() for p in str(cell).split("+")]
    prefix = "".join(ch for ch in parts[0] if ch.isalpha())
    return [p if p[0].isalpha() else prefix + p for p in parts]


def read_mapping(path: Path) -> pd.DataFrame:
    """Mapping rows with columns trade, material, good (REMIND-MFA) and og_sectors (list)."""
    df = pd.read_excel(path, sheet_name=0).dropna(subset=["trade"])
    return pd.DataFrame(
        {
            "trade": df["trade"].str.strip(),
            "material": df["material"].str.strip(),
            "good": df["Sectors REMIND-MFA"].str.strip(),
            "og_sectors": df["Sectors OPEN-GEM"].map(split_og_sectors),
        }
    )


def read_open_gem(path: Path, scenario: str) -> pd.DataFrame:
    """EU27 rows of sheet SECTOR_<scenario>, indexed by (VAR, SECTOR), one column per year."""
    sheet = f"SECTOR_{scenario}"
    sheets = pd.ExcelFile(path).sheet_names
    if sheet not in sheets:
        raise ValueError(f"No sheet '{sheet}' in {path}. Available sheets: {sheets}")
    df = pd.read_excel(path, sheet_name=sheet, header=1)
    df = df.rename(columns={df.columns[1]: "VAR", df.columns[2]: "SECTOR", df.columns[3]: "REGION"})
    df = df[df["REGION"] == OG_REGION].dropna(subset=["VAR", "SECTOR"])
    year_cols = {}
    for col in df.columns[4:]:
        try:
            year_cols[col] = int(round(float(col)))
        except TypeError, ValueError:
            continue
    df = df.set_index(["VAR", "SECTOR"])[list(year_cols)].rename(columns=year_cols)
    return df.astype(float)


def og_sum(og: pd.DataFrame, var: str, sectors: list[str]) -> pd.Series:
    """OPEN-GEM variable summed over sectors -> Series indexed by year."""
    missing = [s for s in sectors if (var, s) not in og.index]
    if missing:
        raise KeyError(f"OPEN-GEM: no {var} values for {missing} in {OG_REGION}")
    return og.loc[[(var, s) for s in sectors]].sum()


def to_model_years(ratio: pd.Series, years: list[int]) -> np.ndarray:
    """Linear interpolation to the model years, constant outside the reported period."""
    return np.interp(years, ratio.index.to_numpy(), ratio.to_numpy())


def write_cs4r(path: Path, df: pd.DataFrame, description: str, dimensions: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(f"* description: {description}\n")
        f.write("* unit: 1\n")
        f.write(f"* note: dimensions: {dimensions}\n")
    df.to_csv(path, mode="a", index=False, header=False)
    print(f"Saved {len(df)} rows to {path}")


def run(
    material: str,
    scenario: str,
    og_scenario: str,
    og: pd.DataFrame,
    mapping: pd.DataFrame,
    report: Path,
):
    years = pd.read_csv(DIMENSION_ROOT / material / "time.csv", header=None)[0].tolist()
    for (mat, category), (market, denominator) in MARKETS.items():
        if mat != material:
            continue
        rows = mapping[(mapping["material"] == material) & (mapping["trade"] == category)]
        if rows.empty:
            raise ValueError(f"No mapping rows for {material} / {category}")
        per_good = category == "manufactured products"
        if not per_good and len(rows) > 1:
            raise ValueError(f"Expected one mapping row for {material} / {category}")
        for direction, numerator in (("imports", "IMPORTS"), ("exports", "EXPORTS")):
            frames = []
            for _, row in rows.iterrows():
                ratio = og_sum(og, numerator, row["og_sectors"]) / og_sum(
                    og, denominator, row["og_sectors"]
                )
                frame = pd.DataFrame(
                    {
                        "Time": years,
                        "Region": TARGET_EU_REGION,
                        "value": to_model_years(ratio, years),
                    }
                )
                if per_good:
                    frame.insert(2, "End Use", row["good"])
                frames.append(frame)
                print(
                    f"  {material} {market} {direction} ({row['good']}, "
                    f"{'+'.join(row['og_sectors'])}): {numerator}/{denominator} "
                    + ", ".join(f"{y}: {v:.4f}" for y, v in ratio.items())
                )
            df = pd.concat(frames, ignore_index=True)
            dimensions = "(Time,Region,End Use,value)" if per_good else "(Time,Region,value)"
            description = (
                f"OPEN-GEM {numerator}/{denominator} (b$ 2017) of the {OG_REGION} region from sheet "
                f"SECTOR_{og_scenario} of {report.name}, mapped to REMIND-MFA {market} trade by "
                f"{DEFAULT_MAPPING.name}; written to {TARGET_EU_REGION} (EU27 vs EU28 scope "
                f"difference not corrected, only relative changes are used); interpolated linearly "
                f"to annual values, constant outside the reported years"
            )
            path = (
                OUTPUT_ROOT
                / scenario
                / f"{PREFIX[material]}_{direction}_ratio_{market}_OPEN-GEM.cs4r"
            )
            write_cs4r(path, df, description, dimensions)


def parse_args():
    p = argparse.ArgumentParser(description="Map OPEN-GEM trade ratios to REMIND-MFA cs4r files.")
    p.add_argument("--material", choices=MATERIALS, default=None)
    p.add_argument(
        "--scenario",
        default=None,
        help="TRANSIENCE scenario (key of SCENARIOS); all scenarios of the material if not given",
    )
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    mapping = read_mapping(args.mapping)
    for material in [args.material] if args.material else MATERIALS:
        scenarios = SCENARIOS[material]
        if args.scenario is not None:
            if args.scenario not in scenarios:
                raise ValueError(
                    f"No OPEN-GEM scenario for {material} scenario '{args.scenario}'. "
                    f"Add it to SCENARIOS. Known: {list(scenarios)}"
                )
            scenarios = {args.scenario: scenarios[args.scenario]}
        for scenario, og_scenario in scenarios.items():
            print(f"\n=== {material} / {scenario} (OPEN-GEM {og_scenario}) ===")
            og = read_open_gem(args.report, og_scenario)
            run(material, scenario, og_scenario, og, mapping, args.report)
