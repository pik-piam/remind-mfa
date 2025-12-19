# Configuration

## General configuration
There is one general configuration file per material model (plastics, steel, cement) where users can adjust the settings for each run of the respective model, such as which plots to create, or choosing between different modelling parameters. The following table lists the settings that can be adjusted with their type, default values and description:

{% include-markdown "plastics/config_schema.md" %}

## Scenario configuration
The config folder contains a "scenarios" folder with configuration files that define parameter settings for different scenarios: The implemented scenario variation framework enables simple variation of input parameters. For each material model (plastics, steel, cement), a set of scenario parameters is defined in *material*_definition.py, that can be adjusted through the scenario configuration files in YAML format. A scenario is defined as a set of input parameters that deviate from the parameters of the baseline or parent scenario. This means that scenarios can inherit from existing ones. For instance, the scenario "SSP1" inherits from its parent scenario "SSP2", i.e. all parameter values defined in SSP2 are adopted in SSP1 unless they are overwritten in the configuration file for SSP1.