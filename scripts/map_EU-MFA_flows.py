"""Map EU-MFA (TRANSIENCE partner model) flows onto REMIND-MFA dimensions and write .cs4r files.

Region handling
---------------
REMIND-MFA runs at h12 by default, where the EU region is EUR (= EU28). EU-MFA delivers steel for EU27+1
(= EU28), which only needs renaming to EUR, but plastics for EU27+3. The h12 and TRANSIENCE EU27+3
region mappings differ in exactly two countries, CHE and NOR, so EUR is a strict subset of EU27+3
and the conversion is a single population-weighted factor per year (see eu_region_scaling_factors).
REMIND-MFA can also run at EU27+3 resolution, if the ATLAS-Trade coupling is not used, in which case 
the plastics flows are written out unchanged.

The target region is TARGET_EU_REGION, imported from the model.
"""

import sys
import pandas as pd
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from backcast_by_reference import backcast_by_reference
from remind_mfa.common.common_data_reader import MadratParameterReader
from remind_mfa.common.common_definition import EU_MFA_REGION as TARGET_EU_REGION
import argparse

MATERIALS = ["plastics", "steel"]
# The two EU regions the EU-MFA data can be written out as: EUR (h12, EU28) and EU27+3.
EUR = "EUR"
EU27P3 = "EU27+3"
# The population weight is near-identical across SSPs (0.0012 spread in 2050), so SSP2 is safe.
DRIVER_SCENARIO = "SSP2"
# Extracted madrat archive: supplies both the backcasting references and the live population.
PARAMETERS_DIR = Path("data_in/parameters")
REFERENCE_DIR = Path("data_in/legacy/transience/reference")
# Regions that are identical in the h12 and TRANSIENCE EU27+3 mappings; used to detect a stale
# frozen population snapshot.
UNAFFECTED_REGIONS = ["CAZ", "CHA", "IND", "JPN", "LAM", "MEA", "OAS", "REF", "SSA", "USA"]
FLOWS_BY_MATERIAL = {
    "plastics": [
        "demand",
        "stock_outflow",
        "collected_eol",
        "sorted_eol",
        "recycled_eol",
        "traded_recyclate",
    ],
    "steel": ["demand", "collected_eol", "lost_eol", "scrap"],
}
# Some flows don't exist for every scenario. traded_recyclate is only produced
# by the CE-PET scenarios (S0/S1/S2), not by the plastics baseline, so it is
# skipped there.
SCENARIO_EXCLUDED_FLOWS = {
    "baseline": ["traded_recyclate"],
}
# Flows with no baseline counterpart: non-baseline scenarios are not supplemented
# with baseline data for the non-PET / non-Packaging combinations.
FLOWS_WITHOUT_BASELINE = {"traded_recyclate"}
SCENARIOS = {
    "plastics": [
        "baseline",
        "CE-PET_fd_plastics_S0",
        "CE-PET_fd_plastics_S1",
        "CE-PET_fd_plastics_S2",
    ],
    "steel": [
        "Baseline_Steel_01_06_2026",
        "Downsizing_Conservative_Steel_01_06_2026",
        "Downsizing_Highly_Ambitious_Steel_result_01_06_2026",
        "Redesign_ Conservative_Steel",
        "Redesign_ Highly_Ambitious_Steel",
        "Remanufacturing_Conservative_Steel",
        "Remanufacturing_Highly_Ambitious_Steel",
        "AHSS & HSS_ Conservative_Steel",
        "AHSS & HSS_ Highly_Ambitious_Steel",
        "Combined_Conservative_Steel",
        "Combined_Highly_Ambitious_Steel",
    ],
}

ALL_SCENARIOS = [s for scenarios in SCENARIOS.values() for s in scenarios]

parser = argparse.ArgumentParser()
parser.add_argument(
    "material",
    choices=MATERIALS,
    nargs="?",
    default=None,
    help="Material to process (default: all materials)",
)
parser.add_argument(
    "scenario",
    choices=ALL_SCENARIOS,
    nargs="?",
    default=None,
    help="Scenario to process (default: all scenarios)",
)
args = parser.parse_args()


def read_cs4r(path: Path) -> pd.DataFrame:
    """Read a .cs4r file, taking the column names from its 'dimensions:' header comment."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. The madrat input data must be extracted to "
            f"{PARAMETERS_DIR}/ before running this script: run scripts/fetch_from_hpc.py to "
            f"download the archive, or run the model once to extract it."
        )
    names, skiprows = MadratParameterReader.extract_cs4r_info(path)
    return pd.read_csv(path, names=names, skiprows=skiprows)


def assert_target_region_supported(material: str) -> None:
    """Check the model's EU region against what EU-MFA can deliver for this material.

    Plastics works for both: EU27+3 is what EU-MFA delivers, and EU28 (EUR) is a population-
    weighted conversion of it. Steel is EUR only -- EU-MFA delivers EU27+1 (= EU28).
    """
    supported = (EUR, EU27P3) if material == "plastics" else (EUR,)
    if TARGET_EU_REGION not in supported:
        raise ValueError(
            f"EU-MFA {material} cannot be mapped onto region '{TARGET_EU_REGION}'; supported: "
            f"{', '.join(supported)}. Set EU_MFA_REGION in remind_mfa/common/common_definition.py "
            f"and input.region_mapping in the config consistently."
        )


def load_production_reference(material_prefix: str) -> pd.DataFrame:
    """Load the production parameter used as the backcasting reference, from data_in/parameters.

    Read live from the extracted madrat archive so the current input data revision is always
    used. Asserts that the target EU region is present, because backcast_by_reference silently
    fills NaN for regions missing from the reference, which would hide a resolution mismatch.
    """
    path = PARAMETERS_DIR / f"{material_prefix}_production.cs4r"
    ref = read_cs4r(path)
    # the time column is named "Time" for plastics and "Historic Time" for steel
    ref = ref.rename(columns={ref.columns[0]: "Time"})
    if TARGET_EU_REGION not in set(ref["Region"]):
        raise ValueError(
            f"Backcasting reference {path} has no region '{TARGET_EU_REGION}'. It contains "
            f"{sorted(set(ref['Region']))}, so the extracted input data is at a different "
            f"regional aggregation than the model expects."
        )
    return ref


@lru_cache(maxsize=None)
def eu_region_scaling_factors(driver_scenario: str = DRIVER_SCENARIO) -> pd.Series | None:
    """Population-weighted factors converting EU-MFA plastics flows from EU27+3 to EU28.

    Returns None when the model's EU region is already EU27+3, which is what EU-MFA plastics is
    delivered for: no conversion is needed and the flows are written out unchanged.

    The h12 and TRANSIENCE EU27+3 region mappings differ in exactly two countries, CHE and NOR,
    so EUR is a strict subset of EU27+3 and the conversion is a single factor per year:

        factor(t) = population_h12[EUR](t) / population_2c0a4149[EU27+3](t)

    The EUR numerator is read live from the extracted madrat archive; the EU27+3 denominator comes
    from a frozen snapshot in the reference folder, because only one region mapping is ever
    extracted at a time. Returns a Series indexed by Time.
    """
    if TARGET_EU_REGION == EU27P3:
        return None

    live = read_cs4r(PARAMETERS_DIR / "pl_population.cs4r")
    frozen = read_cs4r(REFERENCE_DIR / "pl_population_2c0a4149.cs4r")

    def by_year(df: pd.DataFrame, region: str) -> pd.Series:
        selected = df[(df["Driver Scenario"] == driver_scenario) & (df["Region"] == region)]
        if selected.empty:
            raise ValueError(
                f"No population for region '{region}' and scenario '{driver_scenario}'. "
                f"Available regions: {sorted(set(df['Region']))}."
            )
        return selected.set_index("Time")["value"].sort_index()

    # Guard against a stale frozen snapshot: the regions that are identical in both mappings must
    # agree between the frozen and the live file. The tolerance absorbs the last-digit round-off
    # from writing the two .cs4r files, which is of order 1e-14 relative.
    for region in UNAFFECTED_REGIONS:
        frozen_pop, live_pop = by_year(frozen, region), by_year(live, region)
        deviation = (live_pop / frozen_pop - 1.0).abs().max()
        if deviation > 1e-9:
            raise ValueError(
                f"Population for '{region}' differs by up to {deviation:.2e} (relative) between "
                f"{REFERENCE_DIR / 'pl_population_2c0a4149.cs4r'} and "
                f"{PARAMETERS_DIR / 'pl_population.cs4r'}, but that region is identical in the "
                f"h12 and EU27+3 region mappings. The frozen 2c0a4149 snapshot is out of date; "
                f"re-copy it from a current 2c0a4149 input data archive."
            )

    factors = by_year(live, TARGET_EU_REGION) / by_year(frozen, EU27P3)
    # EU28 is a strict subset of EU27+3, differing only by CHE and NOR, so the factor is strictly
    # below 1. Anything else means the wrong pair of files was read.
    if not factors.between(0.9, 1.0, inclusive="left").all():
        raise ValueError(
            f"{EU27P3}->{TARGET_EU_REGION} population factors outside [0.9, 1.0): "
            f"min {factors.min():.5f}, max {factors.max():.5f}. Check that the two population "
            f"files are at h12 and 2c0a4149 resolution respectively."
        )
    return factors


def scale_to_target_eu_region(df: pd.DataFrame, factors: pd.Series | None) -> pd.DataFrame:
    """Relabel the EU region to the model's one, scaling by that year's weight if needed.

    A None factor means the model's EU region already matches what EU-MFA delivers, so the values
    pass through unchanged and only the region label is set.
    """
    if factors is None:
        return df.assign(Region=TARGET_EU_REGION)
    missing = set(df["Time"]) - set(factors.index)
    if missing:
        raise ValueError(
            f"No population weight for years {sorted(missing)}; the population parameter covers "
            f"{factors.index.min()}-{factors.index.max()}."
        )
    df = df.copy()
    df["value"] = df["value"] * df["Time"].map(factors)
    df["Region"] = TARGET_EU_REGION
    return df


def _load_baseline_plastics(flow: str, mapping: pd.DataFrame) -> pd.DataFrame:
    """Load and aggregate baseline plastics data into (Time, Region, Material, Good, value)."""
    BASELINE_DIR = Path("data_in/legacy/transience_input/plastics/baseline")
    eu_subregions = ["Germany", "West", "South", "North", "East"]

    if flow == "demand":
        input_file = BASELINE_DIR / "plastics_market__end_use_stock.csv"
    elif flow == "stock_outflow":
        input_file = BASELINE_DIR / "end_use_stock__waste_collection.csv"
    elif flow == "collected_eol":
        input_file = BASELINE_DIR / "waste_collection__waste_sorting.csv"
    elif flow == "sorted_eol":
        input_file = BASELINE_DIR / "waste_sorting__sorted_waste_market.csv"
    elif flow == "recycled_eol":
        input_file = BASELINE_DIR / "recycling__recyclate_sysenv.csv"

    df = pd.read_csv(input_file, sep=",")
    df = df.rename(columns={"time": "Time", "region": "Region"})
    df = df[df.element == "All"].copy()
    df = df[df.Region.isin(eu_subregions)].copy()
    if flow == "sorted_eol":
        df = df[df.waste_category == "Mechanical recycling"].copy()
    if flow == "recycled_eol":
        df = df[df.secondary_raw_material == "Granulate"].copy()
    df = scale_to_target_eu_region(df, eu_region_scaling_factors())
    df["value"] = df["value"] * 1000

    polymer_map = mapping[mapping.original_dimension == "polymers"][
        ["original_element", "target_element"]
    ]
    df = (
        df.merge(polymer_map, left_on="polymer", right_on="original_element", how="left")
        .rename(columns={"target_element": "Material"})
        .drop(columns="original_element")
    )

    sector_map = mapping[mapping.original_dimension == "end_use_sectors_MainSectors"][
        ["original_element", "target_element"]
    ]
    df = (
        df.merge(sector_map, left_on="sector", right_on="original_element", how="left")
        .rename(columns={"target_element": "Good"})
        .drop(columns="original_element")
    )

    df = df.groupby(["Time", "Region", "Material", "Good"], as_index=False)["value"].sum()
    df.loc[df["value"] < 0.1, "value"] = 0.0
    return df


def _load_baseline_output_plastics(flow: str) -> pd.DataFrame:
    """Load the already-processed baseline output flow to use as the backcasting
    reference for non-baseline scenarios.

    Unlike the raw baseline input, the baseline output covers the full historic
    period (1950-2060), so it provides a complete trajectory for extending the
    shorter non-baseline scenario series into the past.
    """
    BASELINE_OUT_DIR = Path("data_in/legacy/transience/baseline")
    flow_to_file = {
        "demand": "pl_stock_inflow_EU-MFA.cs4r",
        "stock_outflow": "pl_stock_outflow_EU-MFA.cs4r",
        "collected_eol": "pl_collected_eol_EU-MFA.cs4r",
        "sorted_eol": "pl_sorted_eol_EU-MFA.cs4r",
        "recycled_eol": "pl_recycled_eol_EU-MFA.cs4r",
    }
    path = BASELINE_OUT_DIR / flow_to_file[flow]
    if not path.exists():
        raise FileNotFoundError(
            f"Baseline output {path} not found. The 'baseline' scenario must be processed "
            f"before non-baseline scenarios, since it is used as the backcasting reference."
        )
    return pd.read_csv(
        path,
        comment="*",
        header=None,
        names=["Time", "Region", "Type", "Material", "Good", "value"],
    )


def run_combination(material: str, flow: str, scenario: str):
    # Fail before writing anything if EU-MFA cannot supply the model's EU region for this material.
    assert_target_region_supported(material)

    OUTPUT_DIR = Path("data_in/legacy/transience") / scenario
    if material == "plastics":
        DATA_DIR = Path("data_in/legacy/transience_input/plastics") / scenario
        MAPPING_FILE = Path("data_in/legacy/transience_input/plastics/EU_MFA_mapping_plastics.csv")
        if flow == "demand":
            INPUT_FILE = DATA_DIR / "plastics_market__end_use_stock.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_stock_inflow_EU-MFA.cs4r"
        elif flow == "stock_outflow":
            INPUT_FILE = DATA_DIR / "end_use_stock__waste_collection.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_stock_outflow_EU-MFA.cs4r"
        elif flow == "collected_eol":
            INPUT_FILE = DATA_DIR / "waste_collection__waste_sorting.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_collected_eol_EU-MFA.cs4r"
        elif flow == "sorted_eol":  # TODO think about trade of collected waste?
            if scenario == "baseline":
                INPUT_FILE = DATA_DIR / "waste_sorting__sorted_waste_market.csv"
            else:
                INPUT_FILE = DATA_DIR / "sorted_waste_market__recycling.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_sorted_eol_EU-MFA.cs4r"
        elif flow == "recycled_eol":
            if scenario == "baseline":
                INPUT_FILE = DATA_DIR / "recycling__recyclate_sysenv.csv"
            else:
                INPUT_FILE = DATA_DIR / "recycling__recyclate_market.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_recycled_eol_EU-MFA.cs4r"
        elif flow == "traded_recyclate":
            INPUT_FILE = DATA_DIR / "polymer_market__recyclate_sysenv.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_traded_recyclate_EU-MFA.cs4r"
        DIMENSION_DIR = Path("data_in/dimensions/plastics")
    elif material == "steel":
        DATA_DIR = Path("data_in/legacy/transience_input/steel") / scenario
        MAPPING_FILE = Path("data_in/legacy/transience_input/steel/EU_MFA_mapping_steel.csv")
        if flow == "demand":
            INPUT_FILE = DATA_DIR / "steel_goods_market__end_use_stock_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_stock_inflow_EU-MFA.cs4r"
        elif flow == "collected_eol":
            INPUT_FILE = DATA_DIR / "end_use_stock__waste_management_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_collected_eol_EU-MFA.cs4r"
        elif flow == "lost_eol":
            INPUT_FILE = DATA_DIR / "end_use_stock__sysenv_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_lost_eol_EU-MFA.cs4r"
        elif flow == "scrap":
            INPUT_FILE = DATA_DIR / "waste_management__available_scrap_sysenv_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_available_scrap_EU-MFA.cs4r"
        DIMENSION_DIR = Path("data_in/dimensions/steel")

    print(f"\n=== {material} / {flow} / {scenario} ===")

    # --- load and filter ---
    df1 = pd.read_csv(INPUT_FILE, sep=",")
    df1 = df1.rename(columns={"time": "Time", "region": "Region"})
    df1 = df1[
        df1.element == "All"
    ].copy()  # only consider total flows, no Cu contamination flow for steel
    if material == "plastics":
        if scenario == "baseline":
            # flows are available at subregion level with differentiated lifetimes;
            # use subregions for consistency
            eu_subregions = ["Germany", "West", "South", "North", "East"]
            df1 = df1[df1.Region.isin(eu_subregions)].copy()
            if (
                flow == "sorted_eol"
            ):  # currently, only mechanical recycling to granulate is considered
                df1 = df1[df1.waste_category == "Mechanical recycling"].copy()
            if (
                flow == "recycled_eol"
            ):  # currently, only mechanical recycling to granulate is considered
                df1 = df1[df1.secondary_raw_material == "Granulate"].copy()
        else:
            # Non-baseline scenarios have quarterly timesteps (Y.0, Y.25, Y.5, Y.75).
            # The final year (2050) has fewer quarters than full years, so summing would
            # under-count it. Scale each year's values by full_quarters / quarters_present
            # to annualize, then collapse to integer years.
            year = df1["Time"].astype(float).astype(int)
            quarters_per_year = df1.groupby(year)["Time"].transform("nunique")
            full_quarters = quarters_per_year.max()
            df1["value"] = df1["value"] * full_quarters / quarters_per_year
            df1["Time"] = year
            scenario_last_year = int(year.max())  # used later to cap the output
        # EU-MFA plastics covers EU27+3; convert it down to EU28 if that is what the model runs
        # at, otherwise write it out unchanged (see module docstring)
        factors = eu_region_scaling_factors()
        df1 = scale_to_target_eu_region(df1, factors)
        years = sorted(df1["Time"].unique())
        if factors is None:
            print(f"Model region is {EU27P3}; EU-MFA plastics used unchanged as {TARGET_EU_REGION}")
        else:
            print(
                f"Converted {EU27P3} -> {TARGET_EU_REGION} with population factors "
                f"{factors[years[0]]:.5f} ({years[0]}) to {factors[years[-1]]:.5f} ({years[-1]})"
            )
    elif material == "steel":
        # EU-MFA steel covers EU27+1, which is EU28, so this is a pure relabelling with no
        # conversion. Valid only because assert_target_region_supported has established that
        # TARGET_EU_REGION is EUR.
        df1 = df1[df1.Region == "EU27+1"].copy()
        df1.loc[:, "Region"] = TARGET_EU_REGION
    df1["value"] = df1["value"] * 1000  # kt -> t

    # --- load mapping ---
    mapping = pd.read_csv(MAPPING_FILE, sep=";")

    if material == "plastics":
        # --- map polymers -> Material ---
        polymer_map = mapping[mapping.original_dimension == "polymers"][
            ["original_element", "target_element"]
        ]
        df2 = (
            df1.merge(
                polymer_map,
                left_on="polymer",
                right_on="original_element",
                how="left",
            )
            .rename(columns={"target_element": "Material"})
            .drop(columns="original_element")
        )

        # --- map end-use sectors -> Good ---
        if scenario == "baseline":
            sector_map = mapping[mapping.original_dimension == "end_use_sectors_MainSectors"][
                ["original_element", "target_element"]
            ]
            df3 = (
                df2.merge(
                    sector_map,
                    left_on="sector",
                    right_on="original_element",
                    how="left",
                )
                .rename(columns={"target_element": "Good"})
                .drop(columns="original_element")
            )
        else:
            df3 = df2.copy()
            df3["Good"] = (
                "Packaging"  # in non-baseline scenarios, only packaging sector is differentiated, so assign all flows to Packaging Good
            )

        # --- report unmapped entries ---
        n_unmapped_mat = df3["Material"].isna().sum()
        n_unmapped_good = df3["Good"].isna().sum()
        if n_unmapped_mat > 0:
            print(f"WARNING: {n_unmapped_mat} rows with unmapped polymer (Material=NaN):")
            print(df3[df3["Material"].isna()]["polymer"].unique())
        if n_unmapped_good > 0:
            print(f"WARNING: {n_unmapped_good} rows with unmapped sector (Good=NaN):")
            print(df3[df3["Good"].isna()]["sector"].unique())

        # --- aggregate ---
        df_EU_MFA = df3.groupby(["Time", "Region", "Material", "Good"], as_index=False)[
            "value"
        ].sum()
        dimensions = "(EU-MFA_Time,Region,Type,EU-MFA_Material,EU-MFA_Good,value)"

        # for collected_eol and stock_outflow, the value for PVC in packaging is at around 1e-30 in 2031 (because PVC in packaging is stopped in 2030 and the small amount is a result of the lifetime model)
        # this causes issues for parameter calculation in the MFA, so set values that are <100kg to zero
        if flow != "traded_recyclate":
            df_EU_MFA.loc[df_EU_MFA["value"] < 0.1, "value"] = 0.0

        # non-baseline scenarios only have PET×Packaging data; supplement with baseline flows for all other combinations
        # (traded_recyclate has no baseline counterpart, so there is nothing to supplement)
        if scenario != "baseline" and flow not in FLOWS_WITHOUT_BASELINE:
            df_baseline = _load_baseline_plastics(flow, mapping)
            nonbaseline_combos = df_EU_MFA[["Material", "Good"]].drop_duplicates()
            df_baseline_others = df_baseline.merge(
                nonbaseline_combos, on=["Material", "Good"], how="left", indicator=True
            )
            df_baseline_others = df_baseline_others[
                df_baseline_others["_merge"] == "left_only"
            ].drop(columns="_merge")
            df_EU_MFA = pd.concat([df_EU_MFA, df_baseline_others], ignore_index=True)

        # --- load reference (Time, Region, Type, value) ---
        ref = load_production_reference("pl")
        # EU-MFA plastics flows are all Type="Plastics", so filter the reference to match
        ref = ref[ref.Type == "Plastics"].copy()

    elif material == "steel":
        if flow == "scrap":
            # --- aggregate ---
            df_EU_MFA = df1.groupby(["Time", "Region"], as_index=False)["value"].sum()
            dimensions = "(EU-MFA_Time,Region,value)"
        else:
            # --- map end-use sectors -> Good ---
            sector_map = mapping[mapping.original_dimension == "end_use_sectors"][
                ["original_element", "target_element"]
            ]
            df2 = (
                df1.merge(
                    sector_map,
                    left_on="sector",
                    right_on="original_element",
                    how="left",
                )
                .rename(columns={"target_element": "Good"})
                .drop(columns="original_element")
            )

            # --- report unmapped entries ---
            n_unmapped_good = df2["Good"].isna().sum()
            if n_unmapped_good > 0:
                print(f"WARNING: {n_unmapped_good} rows with unmapped sector (Good=NaN):")
                print(df2[df2["Good"].isna()]["sector"].unique())

            # --- aggregate ---
            df_EU_MFA = df2.groupby(["Time", "Region", "Good"], as_index=False)["value"].sum()
            dimensions = "(EU-MFA_Time,Region,EU-MFA_Good,value)"

        # --- load reference (Historic Time, Region, value) ---
        ref = load_production_reference("st")

    # --- backcast: extend df_EU_MFA into historic years using ref ---
    if material == "plastics" and scenario != "baseline" and flow not in FLOWS_WITHOUT_BASELINE:
        # Non-baseline scenarios only cover the scenario period (e.g. 2018-2050) and would
        # otherwise drop abruptly to zero before their start year. Use the already-processed
        # baseline flow (full 1950-2060 coverage) as the reference so every flow follows the
        # baseline trajectory into the past, scaled to match the scenario in the overlap years.
        baseline_ref = _load_baseline_output_plastics(flow)
        df_backcasted = backcast_by_reference(
            x=df_EU_MFA,
            ref=baseline_ref,
            max_n=5,
        )
    elif material == "steel" or flow == "demand":
        df_backcasted = backcast_by_reference(
            x=df_EU_MFA,
            ref=ref,
            max_n=5,
        )
    else:
        # for plastics baseline non-demand flows, we don't backcast by reference because eol flows start in different years for EU-MFA and this distorts the eol parameter calculation
        # we instead assume zero before the first value in df_EU_MFA
        # get all dimension columns except Time and value
        group_dims = [c for c in df_EU_MFA.columns if c not in ("Time", "value")]
        # create full grid of all combinations of Time and group_dims, using ref for Time values before the first year in df_EU_MFA
        EU_MFA_years = sorted(df_EU_MFA["Time"].unique())
        ref_years = sorted(ref["Time"].unique())
        all_years = sorted(set(EU_MFA_years) | set(ref_years))
        full_grid = pd.DataFrame({"Time": all_years}).merge(
            df_EU_MFA[group_dims].drop_duplicates(), how="cross"
        )
        df_backcasted = full_grid.merge(df_EU_MFA, on=["Time"] + group_dims, how="left")
        df_backcasted["value"] = df_backcasted["value"].fillna(0.0)

    # non-baseline plastics: keep only years covered by the scenario itself;
    # baseline-supplemented goods (to 2060) and reference years must not extend past it.
    if material == "plastics" and scenario != "baseline":
        df_backcasted = df_backcasted[df_backcasted["Time"] <= scenario_last_year].copy()

    # plastics flows carry a constant Type dimension ("Plastics") so they align with the
    # model's Type ("p") dimension; placed after Region to match the (Time, Region, Type,
    # Material, Good, value) column order used elsewhere in the plastics input data.
    if material == "plastics":
        df_backcasted["Type"] = "Plastics"
        df_backcasted = df_backcasted[["Time", "Region", "Type", "Material", "Good", "value"]]

    # --- save ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if material == "plastics":
        years = sorted(df_backcasted["Time"].unique())
        factors = eu_region_scaling_factors()
        if factors is None:
            region_note = f"EU-MFA region {EU27P3} kept as {TARGET_EU_REGION}, values unchanged"
        else:
            region_note = (
                f"converted from {EU27P3} to {TARGET_EU_REGION} by population factor "
                f"{factors[years[0]]:.5f} ({years[0]}) to {factors[years[-1]]:.5f} ({years[-1]})"
            )
    else:
        region_note = f"EU-MFA region EU27+1 relabelled to {TARGET_EU_REGION} (both are EU28)"
    with open(OUTPUT_FILE, "w") as f:
        f.write(
            f"* description: {INPUT_FILE.name} mapped to REMIND MFA dimensions; {region_note}\n"
        )
        f.write(f"* unit: t\n")
        f.write(f"* note: dimensions: {dimensions}\n")
    df_backcasted.to_csv(OUTPUT_FILE, mode="a", index=False, header=False)
    print(f"Saved {len(df_backcasted)} rows to {OUTPUT_FILE}")
    print(df_backcasted.head())

    # --- save dimension files, use demand flow as reference ---
    if flow == "demand":
        # save Time dimension
        time = df_backcasted["Time"].dropna().unique()
        with open(DIMENSION_DIR / "eu_mfa_time.csv", "w") as f:
            for t in time:
                f.write(f"{t}\n")
        # save Good dimension
        if flow != "scrap":  # scrap flow has no Good dimension
            goods = df_backcasted["Good"].dropna().unique()
            with open(DIMENSION_DIR / "eu_mfa_goods.csv", "w") as f:
                for g in goods:
                    f.write(f"{g}\n")
        if material == "plastics":
            # save Material dimension
            materials = df_backcasted["Material"].dropna().unique()
            with open(DIMENSION_DIR / "eu_mfa_materials.csv", "w") as f:
                for m in materials:
                    f.write(f"{m}\n")
        print(f"Saved dimensions to {DIMENSION_DIR}")


if __name__ == "__main__":
    materials = [args.material] if args.material else MATERIALS
    for material in materials:
        scenarios = [args.scenario] if args.scenario else SCENARIOS[material]
        for scenario in scenarios:
            excluded = SCENARIO_EXCLUDED_FLOWS.get(scenario, [])
            for flow in FLOWS_BY_MATERIAL[material]:
                if flow in excluded:
                    print(
                        f"Skipping {material} / {flow} / {scenario}: "
                        f"flow not available for this scenario"
                    )
                    continue
                run_combination(material, flow, scenario)
