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
    SSP2,
    SSP1,SSP2
    SSP5,SSP2

- `SSP2` has no parent — it is a root/baseline scenario.
- `SSP1` inherits from `SSP2`: all `SSP2` data points are applied first, then `SSP1` overrides on top.
- `SSP5` also inherits from `SSP2`.

### How Inheritance Works

When a scenario is loaded (e.g. `SSP1`), the reader walks up the inheritance chain:

1. Find `SSP1` → parent is `SSP2`.
2. Find `SSP2` → no parent (root).
3. Apply in order: first `SSP2.csv`, then `SSP1.csv`.

This means the child scenario only needs to specify parameters that **differ** from its parent. Any parameter not overridden retains the parent's value. Chains can be arbitrarily deep.

---

## Scenario CSV Files

Each scenario CSV file contains rows of parameter data points. The columns are:

| Column           | Required | Description |
|------------------|----------|-------------|
| `parameter`      | ✅       | Name of the parameter to set. Must match a parameter definition (see below). |
| `value`          | ✅       | The numeric value to assign. |
| `models`         | ❌       | Which material models this row applies to. Use `all` (default) or a comma-separated list of model names (e.g. `steel`, `plastics`, `cement`, `steel, plastics`). Rows not matching the current model are ignored. |
| `index:<dim>`    | ❌       | Filter by dimension item. E.g. `index:Region` with value `EUR` sets the parameter only for that region. Multiple index columns can be combined. If no index columns are present, the entire parameter array is set to `value`. |
| `extra:<suffix>` | ❌       | Set an additional related parameter named `<parameter>_<suffix>` to the given value in the same row. This requires a separate parameter definition for `<parameter>_<suffix>` to exist. Useful for parameters that come in groups (e.g. a parameter `recycling_rate` with `extra:uncertainty` will also set `recycling_rate_uncertainty`). |

**Example:**

    parameter,models,index:Region,value,extra:uncertainty
    recycling_rate,steel,EUR,0.9,0.05
    recycling_rate,steel,USA,0.85,0.04
    carbon_tax,all,,50,
    growth_factor,plastics,,1.2,

- Row 1: For the `steel` model, set `recycling_rate` at `Region=EUR` to `0.9`, and `recycling_rate_uncertainty` at `Region=EUR` to `0.05`.
- Row 2: Same parameter, different region.
- Row 3: For all models, set the entire `carbon_tax` parameter to `50`.
- Row 4: Only for `plastics`, set `growth_factor` to `1.2`.

### Value Parsing

- Numeric strings are parsed as `int` or `float`.
- Strings that look like Python literals (lists, dicts) are parsed via `ast.literal_eval`.
- Empty cells are treated as `None` and ignored for index/extra columns.

---

## Defining Parameters in Code

Scenario parameters are defined in two places:

- **Common parameters** shared across all material models are defined in `remind_mfa/common/common_definition.py` (as `common_scn_prm_def`).
- **Model-specific parameters** are defined in each material model's definition file, e.g. `remind_mfa/plastics/plastics_definition.py`, `remind_mfa/steel/steel_definition.py`, or `remind_mfa/cement/cement_definition.py` (as `custom_scn_prm_def` on the model class).

Both lists are merged automatically and passed to the `ScenarioReader`.

Parameters are defined using `RemindMFAParameterDefinition` (for array-valued parameters with dimensions) or `PlainDataPointDefinition` (for scalar values).

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

### Registering definitions

In your model class (subclass of `CommonModel`), define `custom_scn_prm_def`:

    class MyModel(CommonModel):
        custom_scn_prm_def = [
            RemindMFAParameterDefinition(name="recycling_rate", dim_letters=["r"]),
            RemindMFAParameterDefinition(name="recycling_rate_uncertainty", dim_letters=["r"]),
            PlainDataPointDefinition(name="carbon_tax"),
        ]

Note that if you use `extra:uncertainty` in a CSV row for the parameter `recycling_rate`, a definition for `recycling_rate_uncertainty` **must** exist in the parameter definitions. The `extra:` mechanism does not create definitions automatically — it only sets values on already-defined parameters.

These model-specific definitions are merged with `common_scn_prm_def` from `remind_mfa/common/common_definition.py` and passed to the `ScenarioReader`.

---

## Using Scenario Parameters in Code

After `read_scenario_parameters()` runs, `self.scenario_parameters` is a dictionary:

    # Access an array parameter (flodym.Parameter)
    recycling_rate = self.scenario_parameters["recycling_rate"]
    # Use like any flodym Parameter — supports indexing, slicing, math operations

    # Access a scalar parameter
    carbon_tax = self.scenario_parameters["carbon_tax"]  # float or None

These are typically consumed during `compute()` or in `modify_parameters()`.

---

## Selecting a Scenario at Runtime

The scenario name is set in the model configuration (YAML), e.g.:

    model_switches:
      scenario: SSP1

This tells the `ScenarioReader` to load `SSP1.csv` (and its ancestors via `inheritance.csv`).

---

## Summary

1. **Add parameter definitions** in your model's `custom_scn_prm_def` list.
2. **Create a CSV file** named `<scenario>.csv` with rows specifying `parameter`, `value`, and optional `models`/`index:`/`extra:` columns.
3. **Register inheritance** in `inheritance.csv` if your scenario should inherit from another.
4. **Set the scenario name** in your YAML config.
5. **Access parameters** via `self.scenario_parameters[<name>]` in your model code.
