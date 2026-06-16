import sys
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from backcast_by_reference import backcast_by_reference
import argparse

MATERIALS = ['plastics', 'steel']
FLOWS_BY_MATERIAL = {
    'plastics': ['demand', 'stock_outflow', 'collected_eol', 'sorted_eol', 'recycled_eol'],
    'steel': ['demand', 'collected_eol', 'lost_eol', 'scrap'],
}
SCENARIOS = {
    'plastics': ['baseline', 'CE-PET_fd_plastics_S0', 'CE-PET_fd_plastics_S1', 'CE-PET_fd_plastics_S2'], 
    'steel': ['Baseline_Steel_01_06_2026', 
              'Downsizing_Conservative_Steel_01_06_2026', 'Downsizing_Highly_Ambitious_Steel_result_01_06_2026', 
              'Redesign_ Conservative_Steel', 'Redesign_ Highly_Ambitious_Steel', 
              'Remanufacturing_Conservative_Steel', 'Remanufacturing_Highly_Ambitious_Steel', 
              'AHSS & HSS_ Conservative_Steel', 'AHSS & HSS_ Highly_Ambitious_Steel',
              'Combined_Conservative_Steel', 'Combined_Highly_Ambitious_Steel']
}

ALL_SCENARIOS = [s for scenarios in SCENARIOS.values() for s in scenarios]

parser = argparse.ArgumentParser()
parser.add_argument('material', choices=MATERIALS, nargs='?', default=None,
                    help='Material to process (default: all materials)')
parser.add_argument('scenario', choices=ALL_SCENARIOS, nargs='?', default=None,
                    help='Scenario to process (default: all scenarios)')
args = parser.parse_args()


def _load_baseline_plastics(flow: str, mapping: pd.DataFrame) -> pd.DataFrame:
    """Load and aggregate baseline plastics data into (Time, Region, Material, Good, value)."""
    BASELINE_DIR = Path("data/plastics/input/transience/baseline")
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
    df["Region"] = "EU27+3"
    df["value"] = df["value"] * 1000

    polymer_map = mapping[mapping.original_dimension == "polymers"][["original_element", "target_element"]]
    df = df.merge(polymer_map, left_on="polymer", right_on="original_element", how="left").rename(
        columns={"target_element": "Material"}
    ).drop(columns="original_element")

    sector_map = mapping[mapping.original_dimension == "end_use_sectors_MainSectors"][
        ["original_element", "target_element"]
    ]
    df = df.merge(sector_map, left_on="sector", right_on="original_element", how="left").rename(
        columns={"target_element": "Good"}
    ).drop(columns="original_element")

    df = df.groupby(["Time", "Region", "Material", "Good"], as_index=False)["value"].sum()
    df.loc[df["value"] < 0.1, "value"] = 0.0
    return df


def run_combination(material: str, flow: str, scenario: str):
    OUTPUT_DIR = Path("../remind_mfa_data/transience") / scenario
    REF_DIR = Path("../remind_mfa_data/transience/reference")
    if material == 'plastics':
        DATA_DIR = Path("data/plastics/input/transience") / scenario
        MAPPING_FILE = Path("data/plastics/input/transience/EU_MFA_mapping_plastics.csv")
        if flow == 'demand':
            INPUT_FILE  = DATA_DIR / "plastics_market__end_use_stock.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_stock_inflow_EU-MFA.cs4r"
        elif flow == 'stock_outflow':
            INPUT_FILE  = DATA_DIR / "end_use_stock__waste_collection.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_stock_outflow_EU-MFA.cs4r"
        elif flow == 'collected_eol':
            INPUT_FILE  = DATA_DIR / "waste_collection__waste_sorting.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_collected_eol_EU-MFA.cs4r"
        elif flow == 'sorted_eol': # TODO think about trade of collected waste?
            if scenario == "baseline":
                INPUT_FILE  = DATA_DIR / "waste_sorting__sorted_waste_market.csv"
            else:
                INPUT_FILE  = DATA_DIR / "sorted_waste_market__recycling.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_sorted_eol_EU-MFA.cs4r"
        elif flow == 'recycled_eol':
            if scenario == "baseline":
                INPUT_FILE  = DATA_DIR / "recycling__recyclate_sysenv.csv"
            else:
                INPUT_FILE  = DATA_DIR / "recycling__recyclate_market.csv"
            OUTPUT_FILE = OUTPUT_DIR / "pl_recycled_eol_EU-MFA.cs4r"
        DIMENSION_DIR = Path("../remind_mfa_data/dimensions/plastics")
    elif material == 'steel':
        DATA_DIR = Path("data/steel/input/transience") / scenario
        MAPPING_FILE = Path("data/steel/input/transience/EU_MFA_mapping_steel.csv")
        if flow == 'demand':
            INPUT_FILE  = DATA_DIR / "steel_goods_market__end_use_stock_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_stock_inflow_EU-MFA.cs4r"
        elif flow == 'collected_eol':
            INPUT_FILE  = DATA_DIR / "end_use_stock__waste_management_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_collected_eol_EU-MFA.cs4r"
        elif flow == 'lost_eol':
            INPUT_FILE  = DATA_DIR / "end_use_stock__sysenv_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_lost_eol_EU-MFA.cs4r"
        elif flow == 'scrap':
            INPUT_FILE  = DATA_DIR / "waste_management__available_scrap_sysenv_combined.csv"
            OUTPUT_FILE = OUTPUT_DIR / "st_available_scrap_EU-MFA.cs4r"
        DIMENSION_DIR = Path("../remind_mfa_data/dimensions/steel")

    print(f"\n=== {material} / {flow} / {scenario} ===")

    # --- load and filter ---
    df1 = pd.read_csv(INPUT_FILE, sep=",")
    df1 = df1.rename(columns={"time": "Time", "region": "Region"})
    df1 = df1[df1.element == "All"].copy() # only consider total flows, no Cu contamination flow for steel
    if material == "plastics":
        if scenario == "baseline":
            # flows are available at subregion level with differentiated lifetimes;
            # use subregions for consistency
            eu_subregions = ["Germany", "West", "South", "North", "East"] 
            df1 = df1[df1.Region.isin(eu_subregions)].copy()
            if flow == "sorted_eol": # currently, only mechanical recycling to granulate is considered
                df1 = df1[df1.waste_category == "Mechanical recycling"].copy()
            if flow == "recycled_eol": # currently, only mechanical recycling to granulate is considered
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
        df1["Region"] = "EU27+3"
    elif material == "steel":
        df1 = df1[df1.Region == "EU27+1"].copy()
        df1.loc[:, "Region"] = "EUR"
    df1["value"] = df1["value"] * 1000          # kt -> t

    # --- load mapping ---
    mapping = pd.read_csv(MAPPING_FILE, sep=";")

    if material == "plastics":
        # --- map polymers -> Material ---
        polymer_map = mapping[mapping.original_dimension == "polymers"][
            ["original_element", "target_element"]
        ]
        df2 = df1.merge(
            polymer_map,
            left_on="polymer",
            right_on="original_element",
            how="left",
        ).rename(columns={"target_element": "Material"}).drop(columns="original_element")

        # --- map end-use sectors -> Good ---
        if scenario == "baseline":
            sector_map = mapping[mapping.original_dimension == "end_use_sectors_MainSectors"][
                ["original_element", "target_element"]
            ]
            df3 = df2.merge(
                sector_map,
                left_on="sector",
                right_on="original_element",
                how="left",
            ).rename(columns={"target_element": "Good"}).drop(columns="original_element")
        else:
            df3 = df2.copy()
            df3["Good"] = "Packaging"  # in non-baseline scenarios, only packaging sector is differentiated, so assign all flows to Packaging Good

        # --- report unmapped entries ---
        n_unmapped_mat  = df3["Material"].isna().sum()
        n_unmapped_good = df3["Good"].isna().sum()
        if n_unmapped_mat > 0:
            print(f"WARNING: {n_unmapped_mat} rows with unmapped polymer (Material=NaN):")
            print(df3[df3["Material"].isna()]["polymer"].unique())
        if n_unmapped_good > 0:
            print(f"WARNING: {n_unmapped_good} rows with unmapped sector (Good=NaN):")
            print(df3[df3["Good"].isna()]["sector"].unique())

        # --- aggregate ---
        df_EU_MFA = (
            df3.groupby(["Time", "Region", "Material", "Good"], as_index=False)["value"]
            .sum()
        )
        dimensions = "(EU-MFA_Time,Region,EU-MFA_Material,EU-MFA_Good,value)"

        # for collected_eol and stock_outflow, the value for PVC in packaging is at around 1e-30 in 2031 (because PVC in packaging is stopped in 2030 and the small amount is a result of the lifetime model)
        # this causes issues for parameter calculation in the MFA, so set values that are <100kg to zero
        df_EU_MFA.loc[df_EU_MFA["value"] < 0.1, "value"] = 0.0

        # non-baseline scenarios only have PET×Packaging data; supplement with baseline flows for all other combinations
        if scenario != "baseline":
            df_baseline = _load_baseline_plastics(flow, mapping)
            nonbaseline_combos = df_EU_MFA[["Material", "Good"]].drop_duplicates()
            df_baseline_others = df_baseline.merge(
                nonbaseline_combos, on=["Material", "Good"], how="left", indicator=True
            )
            df_baseline_others = df_baseline_others[df_baseline_others["_merge"] == "left_only"].drop(columns="_merge")
            df_EU_MFA = pd.concat([df_EU_MFA, df_baseline_others], ignore_index=True)

        # --- load reference (Historic Time, Region, Good, value) ---
        ref = pd.read_csv(
            REF_DIR / "pl_consumption.cs4r",
            comment="*", header=None,
            names=["Time", "Region", "Good", "value"],
        )
        
    elif material == "steel":
        if flow == "scrap":
            # --- aggregate ---
            df_EU_MFA = (
                df1.groupby(["Time", "Region"], as_index=False)["value"]
                .sum()
            )
            dimensions = "(EU-MFA_Time,Region,value)"
        else: 
            # --- map end-use sectors -> Good ---
            sector_map = mapping[mapping.original_dimension == "end_use_sectors"][
                ["original_element", "target_element"]
            ]
            df2 = df1.merge(
                sector_map,
                left_on="sector",
                right_on="original_element",
                how="left",
            ).rename(columns={"target_element": "Good"}).drop(columns="original_element")

            # --- report unmapped entries ---
            n_unmapped_good = df2["Good"].isna().sum()
            if n_unmapped_good > 0:
                print(f"WARNING: {n_unmapped_good} rows with unmapped sector (Good=NaN):")
                print(df2[df2["Good"].isna()]["sector"].unique())

            # --- aggregate ---
            df_EU_MFA = (
                df2.groupby(["Time", "Region", "Good"], as_index=False)["value"]
                .sum()
            )
            dimensions = "(EU-MFA_Time,Region,EU-MFA_Good,value)"

        # --- load reference (Historic Time, Region, Good, value) ---
        ref = pd.read_csv(
            REF_DIR / "st_production.cs4r",
            comment="*", header=None,
            names=["Time", "Region", "value"],
        )

    # --- backcast: extend df_EU_MFA into historic years using ref ---
    if material == "steel" or flow == "demand":
        df_backcasted = backcast_by_reference(
            x=df_EU_MFA,
            ref=ref,
            max_n=5,
        )
    else:
        # for plastics non-demand flows, we don't backcast by reference because eol flows start in different years for EU-MFA and this distorts the eol parameter calculation
        # we instead assume zero before the first value in df_EU_MFA
        # get all dimension columns except Time and value
        group_dims = [c for c in df_EU_MFA.columns if c not in ("Time", "value")]
        # create full grid of all combinations of Time and group_dims, using ref for Time values before the first year in df_EU_MFA
        EU_MFA_years   = sorted(df_EU_MFA["Time"].unique())
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

    # --- save ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        f.write(f"* description: {INPUT_FILE.name} mapped to REMIND MFA dimensions\n")
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
            for flow in FLOWS_BY_MATERIAL[material]:
                run_combination(material, flow, scenario)
