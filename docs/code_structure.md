# Code Structure

The basic structure of the source code is as follows:

* There is one folder for common routines and one folder per material model (plastics, steel, cement)
* For each material, responsibilities are divided to separate files as follows:
    - Definitions of the dimensionalities of flows, stocks, and parameters, as well as the connections of flows and processes.
    - Computing routines for the future MFA system
    - A similar such file for the historical system
    - Model management: Initialisation of the MFA systems, calls to their compute routines, and to visualisation and export routines
    - Visualisation routines

Besides the source code, the repository contains another folder for configuration files in YAML format, where users can adjust the settings for each run (such as which plots to create, or choosing between different modelling parameters).
