# Scenarios Framework

A scenario parameter only affects the future. Anything that influences the historical years is a model assumption, set in the model code and documented with `add_assumption_doc`.

The scenario is selected in the TOML config:

    [base.model_switches]
    scenario = "SSP1"

---

## Inheritance

`inheritance.csv` assigns each scenario its parent (empty for a root scenario):

    scenario,parent
    BASE,
    SSP1,BASE
    SSP1_CE,SSP1

The `ScenarioReader` walks up the chain and applies the CSV files from the root to the selected scenario, so `SSP1_CE` applies `BASE.csv`, then `SSP1.csv`, then `SSP1_CE.csv`. A child scenario therefore only contains parameters that differ from its parent. `BASE` holds the model and scenario defaults; it sets no `driver_scen` and is not run directly.

Within each scenario file, lines are read from top to bottom and overwrite each other.
This allows, for example, to first set a parameter for all regions and then overwrite one region
with a different value.

---

## Scenario CSV Files

Each `<scenario>.csv` has one row per data point:

| Column        | Required | Description |
|---------------|----------|-------------|
| `parameter`   | ✅ | Name of a defined scenario parameter (see [Defining Parameters](#defining-parameters)). |
| `value`       | ✅ | Value to assign. Numbers are parsed as `int` or `float`, other strings are kept as-is (e.g. the scenario name of `driver_scen`, or a parameter name as extrapolation endpoint). |
| `models`      | ❌ | `all` (default) or a list of model names, e.g. `steel` or `"steel, plastics"`. Rows for other models are ignored. |
| `index`       | ❌ | Dimension items to set, e.g. `"{Region: EUR, Function: Res}"`. Keys are dimension names, not letters. A value can be a list, `"{Region: [EUR, USA]}"`; several lists are expanded via cross-product. If empty, the whole array is set. Not allowed for scalar parameters. |
| `extra`       | ❌ | Auxiliary values, e.g. `"{uncertainty: 0.05}"`. Each key sets a parameter named `<parameter>_<key>`, which must be defined separately. For extrapolated parameters, the keys `year` and `type` control the extrapolation instead (see [Parameter Extrapolation](#parameter-extrapolation)). |
| `description` | ❌ | Comment, not read by the model. |

Dicts in `index` and `extra` use YAML syntax: keys and string values need no quotes. Since they contain commas, the cell must be wrapped in double quotes. Empty lines and lines starting with `#` are ignored.

**Example:**

    parameter,models,value,extra,index,description
    recycling_rate,steel,0.6,"{uncertainty: 0.1}",
    recycling_rate,steel,0.7,"{Region: [CHA, IND, OAS]}",
    growth_factor,all,1.2,,,

Row 1 sets `recycling_rate` to `0.6` and `recycling_rate_uncertainty` to `0.1` for all regions in the steel model. Row 2 overwrites the values (but not the uncertainty) for three regions, and keeps it to the above values for the rest. Row 3 sets the whole `growth_factor` array to `1.2` for all models.

### Aggregate Regions

Region sets form a hierarchy: `iso249` → `eu21` → `h12`. A `Region` in `index` that is not in the current region set, but in one of its aggregations, is applied to all regions it consists of (logged as info). E.g. `{Region: EUR}` in an `eu21` run sets `DEU`, `FRA`, `UKI`, etc.; this also works within lists. Regions in neither set are skipped with a warning. The mappings are read from the `data_in/piam_mappings` submodule (`regional/regionmappingH12.csv`, `regional/regionmapping_21_EU11.csv`).

---

## Defining Parameters

Common parameters are defined in the list `scenario_parameters` in `remind_mfa/common/common_definition.py`, model-specific ones in the list `scenario_parameters` in `remind_mfa/<model>/<model>_definition.py`. The latter is assigned to `custom_scn_prm_def` on the model class; both lists are merged and passed to the `ScenarioReader`. Three definition types exist:

    RemindMFAParameterDefinition(name="recycling_rate", dim_letters=("r",))  # array, initialized to zero
    PlainDataPointDefinition(name="carbon_tax")                              # scalar, initialized to None
    ExtrapolationDefinition(name="collection_rate", dim_letters=("r",))      # extrapolated parameter

After reading, `self.scenario_parameters[<name>]` of the model and MFA system holds a `flodym.Parameter` (array) or a plain value (scalar), the use of which can be implemented in the different calculation routines. The `extra` column does not create definitions: `{uncertainty: 0.05}` on `recycling_rate` requires a definition of `recycling_rate_uncertainty`. Each definition should have a `description`; it appears in the [Parameter Overview](#parameter-overview) at the end of this file.

---

## Parameter Extrapolation

After the historical MFA run, each parameter with an `ExtrapolationDefinition` is extended to the full time dimension `t`. The model parameter of the same name (from input data or computed in the model) first gets a baseline: with dimension `h`, the last historical value is continued; with `t`, the existing future values are kept; without a time dimension, the values are held constant. Entries with scenario data then blend from this baseline to a scenario endpoint, all other entries keep the baseline. Historical values are never changed. Afterwards, the result is accessed via `self.parameters[<name>]`.

The definition in the code holds some modelling decisions, like the blending function (such as linear, or several s-shaped variants). The scenario CSV holds the scenario decisions: `value` gives the endpoint, `extra` controls the blend, e.g. `"{year: 2060, type: target}"`:

| Key    | Description |
|--------|-------------|
| `year` | Year by which the endpoint is reached. Must lie after the last historical year, else an error is raised. Values without `year` have no effect and trigger a warning. |
| `type` | `target`: blend from the last historical value to `value` (an existing future trajectory is ignored). `factor`: multiply the baseline by a factor that blends from 1 to `value`. |

Each parameter has a single type. Declaring it on one row (e.g. in `BASE`) covers all rows, including inherited ones. Mixed types, or `year` without any declared type, raise an error. Without any scenario rows, the parameter keeps its baseline, e.g. `polymer_shares_use_inflow`.

Instead of a number, `value` can name another parameter, whose values serve as endpoint at the same coordinates. E.g. a structure split can converge to a world-average split read from mrmfa. The referenced parameter must not have the dimension `h` or dimensions the extrapolated parameter lacks. If it is itself extrapolated, it is extrapolated first; circular references raise an error.

---

## Parameter Overview

The following sections are generated by the docs export from the scenario parameter definitions (see [Defining Parameters](#defining-parameters)) and list all parameters, including those of inactive model modules.

<!-- GENERATED SECTION COMMON. DO NOT EDIT BY HAND: THE DOCS EXPORT OVERWRITES IT. -->

### Common

- **`driver_scen`**\
  *Type: plain*\
  Name of the (SSP) scenario to use for all driver parameters with an `S` dimension
- **`saturation_level`**\
  *Type: plain*\
  Saturation level for material use per capita (unit depends on the material, e.g. t/capita)
- **`n_trend_years`**\
  *Type: array; Dimensions: r*\
  Number of most recent historical years used to determine the initial slope of the critically damped blend of in-use stock inflows
- **`flow_approaching_time`**\
  *Type: array; Dimensions: r*\
  Characteristic timescale in years of the critically damped blend of in-use stock inflows from historical trends to future values
- **`stock_factor`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Scaling factor on the extrapolated in-use stock per capita, per region.
- **`trade_factor`**\
  *Type: extrapolation (poly_mix); Dimensions: r*\
  Scaling factor on future trade, per region.
- **`lifetime_factor_nature`**\
  *Type: extrapolation (poly_mix); Dimensions: r, u*\
  Lifetime extension factor of new age-cohorts (nature).
- **`lifetime_factor_nurture`**\
  *Type: extrapolation (poly_mix); Dimensions: r, u*\
  Lifetime extension factor of all age-cohorts by year (nurture).

<!-- GENERATED SECTION PLASTICS. DO NOT EDIT BY HAND: THE DOCS EXPORT OVERWRITES IT. -->

### Plastics

- **`waste_imports`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Plastic waste imports, per region.
- **`waste_exports`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Plastic waste exports, per region.
- **`collection_rate`**\
  *Type: extrapolation (converge_quadratic); Dimensions: r*\
  Share of non-reused end-of-life plastics that is collected for sorting.
- **`landfill_rate`**\
  *Type: extrapolation (converge_quadratic); Dimensions: r*\
  Share of collected waste that is landfilled.
- **`mechanical_recycling_rate`**\
  *Type: extrapolation (converge_quadratic); Dimensions: r*\
  Share of collected waste that is mechanically recycled.
- **`chemical_recycling_rate`**\
  *Type: extrapolation (hermite); Dimensions: r*\
  Share of collected waste that is chemically recycled.
- **`bio_production_rate`**\
  *Type: extrapolation (hermite); Dimensions: r*\
  Share of primary HVC production from bio-based feedstock.
- **`daccu_production_rate`**\
  *Type: extrapolation (hermite); Dimensions: r*\
  Share of primary HVC production from DACCU feedstock.
- **`emission_capture_rate`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Share of carbon emissions from incineration and chemical recycling that is captured.
- **`polymer_shares_use_inflow`**\
  *Type: extrapolation (linear)*\
  Polymer shares of the in-use stock inflow; held at the last historical value.
- **`reuse_share`**\
  *Type: extrapolation (linear); Dimensions: r, u*\
  Share of end-of-life products that is reused, per region and good.

<!-- GENERATED SECTION STEEL. DO NOT EDIT BY HAND: THE DOCS EXPORT OVERWRITES IT. -->

### Steel

- **`max_scrap_share`**\
  *Type: array; Dimensions: r*\
  Maximum share of scrap in the metallic input to steel production
- **`reuse_share`**\
  *Type: extrapolation (linear); Dimensions: r, u*\
  Share of end-of-life products that is reused, per region and end use.

<!-- GENERATED SECTION CEMENT. DO NOT EDIT BY HAND: THE DOCS EXPORT OVERWRITES IT. -->

### Cement

- **`development_gdppc_low`**\
  *Type: plain*\
  GDP per capita (PPP) below which splits fully converge to their global means.
- **`development_gdppc_high`**\
  *Type: plain*\
  GDP per capita (PPP) above which regions keep their own splits.
- **`clinker_ratio`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Clinker-to-cement mass ratio, per region.
- **`cement_ratio`**\
  *Type: extrapolation (linear); Dimensions: r, m*\
  Mass share of cement in newly produced construction materials, per region and material.
- **`lifetime_mean`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Mean lifetime of cement stocks, per region.
- **`lifetime_std`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Standard deviation of the lifetime of cement stocks, per region.
- **`reuse_share`**\
  *Type: extrapolation (linear); Dimensions: r, m*\
  Share of end-of-life construction materials that is reused, per region and material.

### Cement (bottom-up module)

- **`unoccupied_residential_stock_share`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Share of residential stock that is not permanently occupied (vacant dwellings and second homes).
- **`residential_type_split`**\
  *Type: extrapolation (poly_mix); Dimensions: r, d*\
  Split of residential floor area into single-family and multi-family homes.
- **`structure_split`**\
  *Type: extrapolation (poly_mix); Dimensions: r, b, s*\
  Split of building end uses into structure types, per region.
- **`min_timber_share`**\
  *Type: array; Dimensions: r*\
  Minimum share of timber buildings the structure split converges to.
- **`concrete_building_mi`**\
  *Type: extrapolation (linear); Dimensions: r, b, s*\
  Material intensity of concrete (t/m2), per region, building end use and structure.
