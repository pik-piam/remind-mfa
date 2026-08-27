# Scenarios Framework

This document explains how to define scenarios, configure them via CSV files, and use them in code.

---

## Overview

Each scenario is defined by:
1. A **CSV file** (`<scenario_name>.csv`) containing parameter overrides.
2. An entry in **`inheritance.csv`** defining the parent scenario (if any).

The `ScenarioReader` resolves the inheritance chain, reads all relevant CSV files, and applies the data points in order from the root ancestor to the selected scenario.

---

## Directory Structure

    config/scenarios/
    ├── inheritance.csv
    ├── BASE.csv
    ├── SSP2.csv
    ├── SSP1.csv
    └── ...

---

## inheritance.csv

Defines the parent–child relationships between scenarios.

| Column     | Description                                                                 |
|------------|-----------------------------------------------------------------------------|
| `scenario` | The name of the scenario (must match the CSV filename without extension).   |
| `parent`   | The name of the parent scenario. Leave empty if this is a root scenario.    |

**Example:**

    scenario,parent
    BASE,
    SSP1,BASE
    SSP2,BASE
    SSP1_CE,SSP1

- `BASE` has no parent — it is the root/baseline scenario holding the model and scenario defaults. It sets no `driver_scen`, so it is not run directly.
- `SSP1` inherits from `BASE`: all `BASE` data points are applied first, then `SSP1` overrides on top (including its own `driver_scen`).
- `SSP1_CE` inherits from `SSP1`, which in turn inherits from `BASE`, giving a three-level chain.

### How Inheritance Works

When a scenario is loaded (e.g. `SSP1`), the reader walks up the inheritance chain:

1. Find `SSP1` → parent is `BASE`.
2. Find `BASE` → no parent (root).
3. Apply in order: first `BASE.csv`, then `SSP1.csv`.

This means the child scenario only needs to specify parameters that **differ** from its parent. Any parameter not overridden retains the parent's value. Chains can be arbitrarily deep.

---

## Scenario CSV Files

Each scenario CSV file contains rows of parameter data points. The columns are:

| Column      | Required | Description |
|-------------|----------|-------------|
| `parameter` | ✅       | Name of the parameter to set. Must match a parameter definition (see below). |
| `value`     | ✅       | The numeric value to assign. For extrapolated parameters, this can also be the name of another parameter (see [Parameter Extrapolation](#parameter-extrapolation)). |
| `models`    | ❌       | Which material models this row applies to. Use `all` (default) or a comma-separated list of model names (e.g. `steel`, `plastics`, `cement`, `steel, plastics`). Rows not matching the current model are ignored. |
| `index`     | ❌       | Filter by dimension items. Provide a dict like `{Region: EUR}`. Multiple dimensions can be combined: `{Region: EUR, Function: Res}`. If omitted, the entire parameter array is set to `value`. A dimension value can be a list — `{Region: [EUR, USA]}` — to apply the same row to all listed items without repetition. Multiple lists are expanded via cross-product. |
| `extra`     | ❌       | Auxiliary values for this row. Provide a dict like `{uncertainty: 0.05}`. For plain parameters, each key sets an additional parameter named `<parameter>_<key>` (a definition for it must exist). For extrapolated parameters, the keys `year` and `type` control the extrapolation (see [Parameter Extrapolation](#parameter-extrapolation)). |

**Example:**

    parameter,models,value,extra,index,description
    recycling_rate,steel,0.9,"{year: 2035}","{Region: EUR}",
    recycling_rate,steel,0.85,"{year: 2045}","{Region: USA}",
    recycling_rate,steel,0.7,"{year: 2045}","{Region: [CHN, IND, OAS]}",
    growth_factor,all,1.2,,,

- Row 1: For `steel`, set `recycling_rate[Region=EUR]` to `0.9` and `recycling_rate_uncertainty[Region=EUR]` to `0.05`.
- Row 2: Same parameter, different region.
- Row 3: For `steel`, set `recycling_rate` and `recycling_rate_uncertainty` for three regions with a single row (expanded internally to one data point per region).
- Row 4: For all models, set the entire `growth_factor` parameter to `1.2`.

### Value Parsing

- The `value` column: numeric strings are parsed as `int` or `float`; other strings are returned as-is (e.g. parameter names for extrapolation endpoints).
- The `index` and `extra` columns contain dicts in the form `{key: value, key2: value2}`. Keys and bare-word string values do not need quotes; numeric values are parsed automatically. Lists are written as `[v1, v2, v3]`. Because dicts contain commas, the cell must be wrapped in double quotes in the CSV file (standard CSV quoting).
- An empty `index` or `extra` cell is treated as no index / no extras.

---

## Defining Parameters in Code

Scenario parameters are defined in two places:

- **Common parameters** shared across all material models are defined in `remind_mfa/common/common_definition.py` (as `common_scn_prm_def`).
- **Model-specific parameters** are defined in each material model's definition file, e.g. `remind_mfa/plastics/plastics_definition.py`, `remind_mfa/steel/steel_definition.py`, or `remind_mfa/cement/cement_definition.py` (as `custom_scn_prm_def` on the model class).

Both lists are merged automatically and passed to the `ScenarioReader`.

Parameters are defined using `RemindMFAParameterDefinition` (for array-valued parameters with dimensions), `PlainDataPointDefinition` (for scalar values), or `ExtrapolationDefinition` (for parameters that are extrapolated into the future based on scenario data).

### Array parameter (with dimensions)

    from remind_mfa.common.common_definition import RemindMFAParameterDefinition

    custom_scn_prm_def = [
        RemindMFAParameterDefinition(
            name="recycling_rate",
            dim_letters=["r"],  # e.g. Region dimension
        ),
    ]

This creates a `flodym.Parameter` with the shape of the specified dimensions, initialized to zero. Scenario data points then fill in values.

### Scalar parameter (plain value)

    from remind_mfa.common.common_definition import PlainDataPointDefinition

    custom_scn_prm_def = [
        PlainDataPointDefinition(name="carbon_tax"),
    ]

This creates a parameter initialized to `None`, set to a plain numeric value by the scenario.

### Extrapolated parameter (`ExtrapolationDefinition`)

    from remind_mfa.common.common_definition import ExtrapolationDefinition

    custom_scn_prm_def = [
        ExtrapolationDefinition(
            name="collection_rate",
            dim_letters=("r",),
        ),
    ]

This reads in whole arrays of data, which are converted into a flodym array and stored as a structured extrapolation instruction under `scenario_parameters[<name>]`. During parameter extrapolation, the instruction is applied to the model parameter of the same name. Let's walk through the settings:

1. You provide a `name`. If the `name` mirrors a name of a parameter that - at the time of extrapolation - already exists in your MFA parameters, the extrapolator knows you want to use it to extrapolate this parameter. This means you can even extrapolate parameters that are not part of the read-in. If the `name` doesn't match anything but you instead want to create a new parameter and extrapolate it directly, you can specify ...
2. `create_new`. This defaults to `False`, but it can be useful to initiate a new parameter here directly, which you can then use anywhere in your MFA. This is currently used to create `parameters["stock_factor"]`, which scales the stock after stock extrapolation. Since there is no historic data, the parameter is initialized with 1 (type `factor`) or 0 (type `target`) before extrapolation.
Then, the extrapolation is applied on this baseline, using the ...
3. `blending_function`. It determines the shape of the transition from the old parameter to the scenario endpoint, defaulting to a linear transition. All available functions are listed in `remind_mfa/common/data_blending.py`.
4. `split_dimension_letter` and `split_balancing_item` may be niche applications. With the first, you can provide a dimension letter along which a split is supposed to sum up to one. Then, the extrapolation renormalizes. E.g., if you increase your share of reinforced concrete buildings, it will proportionally decrease your share of other building structures, i.e., wood, steel and masonry. If you want the whole shift to reinforced concrete to happen through another coordinate, you can provide a balancing item. For instance, you could specify `M` (masonry) here, and all the growth in reinforced concrete buildings will be accompanied by a corresponding drop in masonry buildings.

If you just want a constant extrapolation (hold the last historic value constant), you can simply omit all entries except for `name`, see e.g. `ExtrapolationDefinition(name="material_shares_use_inflow")`.

The extrapolation type (`factor` or `target`) is not part of the definition — it is declared in the scenario CSV via `extra:type`, see below.

### Registering definitions

In your model class (subclass of `CommonModel`), define `custom_scn_prm_def`:

    class MyModel(CommonModel):
        custom_scn_prm_def = [
            RemindMFAParameterDefinition(name="recycling_rate", dim_letters=["r"]),
            RemindMFAParameterDefinition(name="recycling_rate_uncertainty", dim_letters=["r"]),
            PlainDataPointDefinition(name="carbon_tax"),
        ]

Note that if you use `{uncertainty: 0.05}` in the `extra` column for the parameter `recycling_rate`, a definition for `recycling_rate_uncertainty` **must** exist in the parameter definitions. The `extra` column does not create definitions automatically — it only sets values on already-defined parameters.

These model-specific definitions are merged with `common_scn_prm_def` from `remind_mfa/common/common_definition.py` and passed to the `ScenarioReader`.

---

## Parameter Extrapolation

The `ExtrapolationDefinition` in the model definition holds the modelling decisions (blending, split handling), while the scenario decisions are stored in the scenario CSVs. REMIND-MFA connects the two through the parameter name.

A CSV row for an extrapolated parameter provides the endpoint of a blend: the parameter transitions from its historic values towards the endpoint given in the `value` column. The `extra` column controls how:

| Key in `extra` | Description |
|----------------|-------------|
| `year`         | The year by which the endpoint is reached. Must lie after the last historic year (earlier years raise an error). A value without `year` has no effect (the entry keeps its baseline) and triggers a warning. |
| `type`         | Either `factor` or `target`. Factor means that the extrapolation method takes your parameter and multiplies it by the value given in the scenario, blending from 1 to that factor by `year`. Target means that the parameter blends from the last historic value to the scenario value. |

Example: `"{year: 2060, type: target}"` in the `extra` column.

Only one type per parameter is supported: declaring it on a single row (e.g. in the base scenario) is enough and also covers inherited rows, while mixed declarations raise an error. A row with `extra:year` but no type declared anywhere for that parameter raises an error as well.

For a constant extrapolation (hold the last historic value constant), you don't have to provide anything in the scenario CSV - a simple `ExtrapolationDefinition` is enough.

The `value` column of extrapolation parameter can not only handle numbers, but you can mix-and-match them with a parameter name in the form of a string. During extrapolation, data from that parameter will be used as extrapolation target or factor. You could e.g. prepare a world-average structure split parameter in mrmfa, read it in as a normal parameter and then provide its name in the scenario CSV such that the structure split is converged towards the world-average split. This can be combined with any settings in the `ExtrapolationDefinition`. The referenced parameter can even itself be a parameter that is extrapolated — in that case it is automatically extrapolated before it is applied. Circular references raise an error.

---

## Using Scenario Parameters in Code

After `read_scenario_parameters()` runs, `self.scenario_parameters` is a dictionary:

    # Access an array parameter (flodym.Parameter)
    recycling_rate = self.scenario_parameters["recycling_rate"]
    # Use like any flodym Parameter — supports indexing, slicing, math operations

    # Access a scalar parameter
    carbon_tax = self.scenario_parameters["carbon_tax"]  # float or None

These are typically consumed during `compute()` or in `modify_parameters()`.

Extrapolated parameters are the exception: after extrapolation has been run, they are ordinary model parameters, so you access them via `self.parameters[<name>]` instead.

---

## Selecting a Scenario at Runtime

The scenario name is set in the configuration file, e.g.:

    [base.model_switches]
    scenario = "SSP1"

This tells the `ScenarioReader` to load `SSP1.csv` (and its ancestors via `inheritance.csv`).

---

## Summary

1. **Add parameter definitions** in your model's `custom_scn_prm_def` list.
2. **Create a CSV file** named `<scenario>.csv` with rows specifying `parameter`, `value`, and optional `models`/`index:`/`extra:` columns.
3. **Register inheritance** in `inheritance.csv` if your scenario should inherit from another.
4. **Set the scenario name** in your TOML config.
5. **Access parameters** via `self.scenario_parameters[<name>]` in your model code.
