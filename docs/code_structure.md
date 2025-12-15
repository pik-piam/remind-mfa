# Code Structure

## Source Code

The basic structure of the source code is as follows:

* There is one folder for common routines and one folder per material model (plastics, steel, cement)
* For each material, responsibilities are divided to separate files as follows:
    - Definitions of the dimensionalities of flows, stocks, and parameters, as well as the connections of flows and processes (*material*_definition.py)
    - Computing routines for the future MFA system (*material*_mfa_system_future.py)
    - A similar file for the historical system (*material*_mfa_system_historic.py)
    - Model management: Initialisation of the MFA systems, calls to their compute routines, and to visualisation and export routines (*material*_model.py)
    - Visualisation routines (*material*_export.py)

## Config Folder

Besides the source code, the repository contains another folder for configuration files in YAML format.   
There is one general configuration file per material model (plastics, steel, cement) where users can adjust the settings for each run of the respective model, such as which plots to create, or choosing between different modelling parameters. The following table lists the settings that can be adjusted with their type, default values and description:

{% include-markdown "plastics/config_schema.md" %}

In addition, the config folder contains a "scenarios" folder with configuration files that define parameter settings for different scenarios: The implemented scenario variation framework enables simple variation of input parameters. For each material model (plastics, steel, cement), a set of scenario parameters is defined in *material*_definition.py, that can be adjusted through the scenario configuration files in YAML format. A scenario is defined as a set of input parameters that deviate from the parameters of the baseline or parent scenario. This means that scenarios can inherit from existing ones. For instance, the scenario "SSP1" inherits from its parent scenario "SSP2", i.e. all parameter values defined in SSP2 are adopted in SSP1 unless they are overwritten in the configuration file for SSP1. 


## Data Folder

The data folder is used to store the input and output data for each model.   
The input data is not part of the repository, but is available open source on Zenodo as detailed [here](input_data.md). For each model, the input data consists of dimension files and parameter datasets. These have to be stored in the subfolders of the input folder named "dimensions" and "datasets", respectively, in order to run the model.  
The output data folder stores all model exports and visulizations.
