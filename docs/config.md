# Configuration

## General configuration

Model runs are configured by TOML files in the `config` folder. A configuration has a
complete shared `[base]` table and optional top-level `[plastics]`, `[steel]`, and
`[cement]` tables that override the base for that material.

Run one material with the default configuration using:

```shell
uv run remind_mfa --config default --model steel
```

Repeat `--config` to apply partial overlay files:

```shell
uv run remind_mfa --config default --config local --model all
```

In this case, all `base` sections are recursively merged in command-line order, as are all sections
for the selected material. The resulting material configuration is then applied over
the resulting base configuration. Consequently, material-specific values always win
over base values, even if a base value came from a later file.

## Batch runs

A configuration file may contain `[[batch_matrix]]` tables in addition to the usual `[base]`
and material tables. Each `[[batch_matrix]]` table defines a full Cartesian product of runs.
Its keys have the same structure as the merged configuration, i.e. without a `base` or material
level, and every value is a list of the values to run. The key `model` selects the materials.
For example, a file `config/ssp_regions.toml`:

```toml
[base]
    [base.export]
        prefix = "ssp_regions"

[[batch_matrix]]
model = ["steel", "cement", "plastics"]
model_switches.scenario = ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"]
input.region_mapping = ["h12"]

[[batch_matrix]]
model = ["steel", "cement", "plastics"]
model_switches.scenario = ["SSP2"]
input.region_mapping = ["iso249"]
```

The file is passed like any other layer, and the matrix values are applied on top of the merged
configuration of all layers:

```shell
uv run remind_mfa --config default --config ssp_regions
```

Rules:

- At most one of the given configuration files may contain `[[batch_matrix]]` tables.
- Values that are lists themselves are given as a list of lists, e.g.
  `visualization.sankey.plotter_args.exclude_processes = [["sysenv"], []]`.
- `--model` restricts the matrices to the given model. Matrices without a `model` key run the
  models given with `--model` (prompted for if missing).
- All runs are configured and validated before the first run starts.

The outputs of all runs of a batch are bundled into one folder,
`<export.path>/<prefix>_batch/<prefix>_<model>_<scenario>_<region_mapping>[_<suffix>]`.
The suffix contains the values of matrix keys other than model, scenario and region mapping that
differ between the runs, so that every run has its own folder.

## Settings

The following table lists the available settings with their types, default values, and descriptions:

{% include-markdown "plastics/config_schema.md" %}

## Scenario configuration
The config folder contains a "scenarios" folder with configuration files that define parameter settings for different scenarios: The implemented scenario variation framework enables simple variation of input parameters. For each material model (plastics, steel, cement), a set of scenario parameters is defined in *material*_definition.py, that can be adjusted through the scenario configuration files in YAML format. A scenario is defined as a set of input parameters that deviate from the parameters of the baseline or parent scenario. This means that scenarios can inherit from existing ones. For instance, the scenario "SSP1" inherits from its parent scenario "SSP2", i.e. all parameter values defined in SSP2 are adopted in SSP1 unless they are overwritten in the configuration file for SSP1.
