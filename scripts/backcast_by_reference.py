import pandas as pd
import numpy as np


def backcast_by_reference(
    x: pd.DataFrame,
    ref: pd.DataFrame,
    max_n: int = 5,
    do_forecast: bool = False,
    do_make_zero_na: bool = False,
    value_col: str = "value",
) -> pd.DataFrame:
    """
    Backcast x using ref as a reference series.

    Parameters
    ----------
    x   : long-format DataFrame with columns (Time, Region, ..., value)
          contains the data to be extended into the past
    ref : long-format DataFrame with columns (Time, Region, ..., value)
          reference series used to derive growth rates for backcasting.
          Extra dimensions in x (e.g. Material) are assumed to follow the
          same trajectory as ref — ref is simply duplicated for each combination.
    max_n            : max number of overlapping years used for weight calculation
    do_forecast      : if True, forecast into the future instead of backcasting
    do_make_zero_na  : replace zeros with NaN in output
    value_col        : name of the value column in both DataFrames

    Returns
    -------
    DataFrame in same long format as x, extended into ref years
    """
    # --- identify group columns (all except Time and value) ---
    group_cols_x   = [c for c in x.columns  if c not in ("Time", value_col)]
    group_cols_ref = [c for c in ref.columns if c not in ("Time", value_col)]

    shared_group_cols = [c for c in group_cols_x if c in group_cols_ref]
    extra_group_cols  = [c for c in group_cols_x if c not in group_cols_ref]
    id_cols = ["Region"] + [c for c in shared_group_cols if c != "Region"]

    x   = x.copy().sort_values(["Time"] + group_cols_x).reset_index(drop=True)
    ref = ref.copy().sort_values(["Time"] + group_cols_ref).reset_index(drop=True)

    x_years   = sorted(x["Time"].unique())
    ref_years = sorted(ref["Time"].unique())

    shared_years = sorted(set(x_years) & set(ref_years))
    if not shared_years:
        raise ValueError("x and ref must share at least one year for backcasting.")

    # --- adapt ref regions to x regions ---
    x_regions   = x["Region"].unique()
    ref_regions = ref["Region"].unique()

    ref_expanded_parts = []
    for region in x_regions:
        if region in ref_regions:
            part = ref[ref["Region"] == region].copy()
        else:
            part = ref[ref["Region"] == ref_regions[0]].copy()
            part["Region"] = region
            part[value_col] = np.nan
        ref_expanded_parts.append(part)
    ref = pd.concat(ref_expanded_parts, ignore_index=True)

    # --- cut unnecessary years ---
    if do_forecast:
        ref = ref[ref["Time"] >= min(x_years)]
    else:
        ref = ref[ref["Time"] <= max(x_years)]
    ref_years = sorted(ref["Time"].unique())

    # --- expand ref over extra group cols by simple duplication ---
    # each extra-col combination (e.g. Material) is assumed to follow
    # the same trajectory as ref — no shares needed
    if extra_group_cols:
        extra_combos = x[id_cols + extra_group_cols].drop_duplicates()
        ref = ref.merge(extra_combos, on=id_cols, how="left")

    # --- compute ratios on shared years (now ref and x have the same dims) ---
    x_shared   = x[x["Time"].isin(shared_years)].rename(columns={value_col: "x_val"})
    ref_shared = ref[ref["Time"].isin(shared_years)].rename(columns={value_col: "ref_val"})

    ratios = x_shared.merge(ref_shared, on=["Time"] + group_cols_x, how="outer")
    ratios["ratio"] = ratios["x_val"] / ratios["ref_val"]

    # --- compute backcast weights ---
    n_shared = len(shared_years)
    if do_forecast:
        base_weights = {y: i + 1 for i, y in enumerate(shared_years)}
    else:
        base_weights = {y: n_shared - i for i, y in enumerate(shared_years)}

    ratios["base_weight"] = ratios["Time"].map(base_weights).astype(float)
    ratios.loc[ratios["ratio"].isna() | np.isinf(ratios["ratio"]), "base_weight"] = n_shared + 1

    ratios["row_min"] = ratios.groupby(group_cols_x)["base_weight"].transform("min")
    ratios["weight"]  = ratios["base_weight"] - ratios["row_min"] + 1

    ratios.loc[ratios["ratio"].isna() | np.isinf(ratios["ratio"]), "weight"] = -1
    ratios["row_max"] = ratios.groupby(group_cols_x)["weight"].transform("max")
    offset = (max_n - ratios["row_max"]).clip(upper=0)
    ratios["weight"] = ratios["weight"] + offset
    ratios.loc[ratios["weight"] < 1, "weight"] = np.nan
    ratios.loc[ratios["ratio"].isna() | np.isinf(ratios["ratio"]), "weight"] = np.nan

    # normalize weights
    ratios["weight_sum"] = ratios.groupby(group_cols_x)["weight"].transform(
        lambda s: s.sum(min_count=1)
    )
    ratios["norm_weight"]    = ratios["weight"] / ratios["weight_sum"]
    ratios["weighted_ratio"] = ratios["ratio"]  * ratios["norm_weight"]

    final_ratio = (
        ratios.groupby(group_cols_x, as_index=False)["weighted_ratio"]
        .sum(min_count=1)
        .rename(columns={"weighted_ratio": "final_ratio"})
    )

    # --- scale reference by final ratio ---
    scaled_ref = ref.merge(final_ratio, on=group_cols_x, how="left")
    scaled_ref[value_col] = scaled_ref[value_col] * scaled_ref["final_ratio"]
    scaled_ref = scaled_ref.drop(columns=["final_ratio"])

    # --- combine x and scaled_ref, x takes priority ---
    all_years = sorted(set(x_years) | set(ref_years))
    full_grid = pd.DataFrame({"Time": all_years}).merge(
        x[group_cols_x].drop_duplicates(), how="cross"
    )

    final = full_grid.merge(x, on=["Time"] + group_cols_x, how="left")

    scaled_ref_renamed = scaled_ref.rename(columns={value_col: "ref_fill"})
    final = final.merge(
        scaled_ref_renamed[["Time"] + group_cols_x + ["ref_fill"]],
        on=["Time"] + group_cols_x,
        how="left",
    )
    final.loc[final[value_col].isna(), value_col] = final.loc[
        final[value_col].isna(), "ref_fill"
    ]
    final = final.drop(columns=["ref_fill"])

    if do_make_zero_na:
        final.loc[final[value_col] == 0, value_col] = np.nan

    return final.sort_values(["Time"] + group_cols_x).reset_index(drop=True)