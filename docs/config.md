# Configuration

## General configuration

Model runs are configured by TOML files in the `config` folder. A configuration has a
complete shared `[base]` table and optional top-level `[plastics]`, `[steel]`, and
`[cement]` tables that override the base for that material.

Run one material with the default configuration using:

```shell
python run_remind_mfa.py --config default --material steel
```

Repeat `--config` to apply partial overlay files:

```shell
python run_remind_mfa.py --config default --config local --material all
```

In this case, all `base` sections are recursively merged in command-line order, as are all sections
for the selected material. The resulting material configuration is then applied over
the resulting base configuration. Consequently, material-specific values always win
over base values, even if a base value came from a later file.

The following table lists the available settings with their types, default values, and descriptions:

{% include-markdown "plastics/config_schema.md" %}

## Scenario configuration
The config folder contains a "scenarios" folder with configuration files that define parameter settings for different scenarios: The implemented scenario variation framework enables simple variation of input parameters. For each material model (plastics, steel, cement), a set of scenario parameters is defined in *material*_definition.py, that can be adjusted through the scenario configuration files in YAML format. A scenario is defined as a set of input parameters that deviate from the parameters of the baseline or parent scenario. This means that scenarios can inherit from existing ones. For instance, the scenario "SSP1" inherits from its parent scenario "SSP2", i.e. all parameter values defined in SSP2 are adopted in SSP1 unless they are overwritten in the configuration file for SSP1.
