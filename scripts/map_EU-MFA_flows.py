import sys
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from backcast_by_reference import backcast_by_reference

DATA_DIR = Path("data/plastics/input")
OUTPUT_DIR = Path("../remind_mfa_data/h12/plastics/input_data")
INPUT_FILE   = DATA_DIR / "plastics_market__end_use_stock.csv"
MAPPING_FILE = DATA_DIR / "EU_MFA_mapping_plastics.csv"
OUTPUT_FILE  = OUTPUT_DIR / "pl_stock_inflow_EU-MFA.cs4r"

def main():
    # --- load and filter ---
    df1 = pd.read_csv(INPUT_FILE, sep=",")
    df1["value"] = df1["value"] * 1000          # kt -> t
    df1 = df1.rename(columns={"time": "Time", "region": "Region"})
    df1 = df1[df1.Region == "EU27+3"].copy()    # TODO: think about region matching, EUR is actually EU28
    df1.loc[:, "Region"] = "EUR"

    # --- load mapping ---
    mapping = pd.read_csv(MAPPING_FILE, sep=";")

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
    sector_map = mapping[mapping.original_dimension == "end_use_sectors_MainSectors"][
        ["original_element", "target_element"]
    ]
    df3 = df2.merge(
        sector_map,
        left_on="sector",
        right_on="original_element",
        how="left",
    ).rename(columns={"target_element": "Good"}).drop(columns="original_element")

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

    # --- load reference (Historic Time, Region, Good, value) ---
    ref = pd.read_csv(
        OUTPUT_DIR / "pl_consumption.cs4r",
        comment="*", header=None,
        names=["Time", "Region", "Good", "value"],
    )

    # --- backcast: extend df_EU_MFA into historic years using ref ---
    df_backcasted = backcast_by_reference(
        x=df_EU_MFA,        # (Time, Region, Material, Good, value)
        ref=ref,            # (Time, Region, Good, value)
        max_n=5,
    )

    # --- save ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        f.write(f"* description: {INPUT_FILE.name} mapped to REMIND MFA dimensions\n")
        f.write(f"* unit: t\n")
        f.write(f"* note: dimensions: (Time,Region,Material,Good,value)\n")
    df_backcasted.to_csv(OUTPUT_FILE, mode="a", index=False, header=False)
    print(f"Saved {len(df_backcasted)} rows to {OUTPUT_FILE}")
    print(df_backcasted.head())

if __name__ == "__main__":
    main()


