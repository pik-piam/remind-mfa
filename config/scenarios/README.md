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
    recycling_rate,steel,0.7,"{uncertainty: 0.1}","{Region: [CHA, IND, OAS]}",
    growth_factor,all,1.2,,,

Row 1 sets `recycling_rate` to `0.7` and `recycling_rate_uncertainty` to `0.1` for three regions of the steel model. Row 2 sets the whole `growth_factor` array to `1.2` for all models.

### Aggregate Regions

Region sets form a hierarchy: `iso249` → `eu21` → `h12`. A `Region` in `index` that is not in the current region set, but in one of its aggregations, is applied to all regions it consists of (logged as info). E.g. `{Region: EUR}` in an `eu21` run sets `DEU`, `FRA`, `UKI`, etc.; this also works within lists. Regions in neither set are skipped with a warning. The mappings are read from the `data_in/piam_mappings` submodule (`regional/regionmappingH12.csv`, `regional/regionmapping_21_EU11.csv`).

---

## Defining Parameters

Common parameters are defined in the list `scenario_parameters` in `remind_mfa/common/common_definition.py`, model-specific ones in the list `scenario_parameters` in `remind_mfa/<model>/<model>_definition.py`. The latter is assigned to `custom_scn_prm_def` on the model class; both lists are merged and passed to the `ScenarioReader`. Three definition types exist:

    RemindMFAParameterDefinition(name="recycling_rate", dim_letters=("r",))  # array, initialized to zero
    PlainDataPointDefinition(name="carbon_tax")                              # scalar, initialized to None
    ExtrapolationDefinition(name="collection_rate", dim_letters=("r",))      # extrapolated parameter

After reading, `self.scenario_parameters[<name>]` of the model and MFA system holds a `flodym.Parameter` (array) or a plain value (scalar), the use of which can be implemented in the different calculation routines. The `extra` column does not create definitions: `{uncertainty: 0.05}` on `recycling_rate` requires a definition of `recycling_rate_uncertainty`.

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
