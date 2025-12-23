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

Besides the source code, the repository contains another folder for configuration files in YAML format. The configuration options are described [here](config.md).

## Data Folder

The data folder is used to store the input and output data for each model.
The input data is not part of the repository, but is available open source on Zenodo as detailed [here](input_data.md).  
The output data folder stores all model exports and visulizations.
