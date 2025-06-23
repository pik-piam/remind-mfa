# REMIND-MFA

REMIND-MFA includes top-down prospective material flow analysis (MFA) models for the basic materials cement, plastics, and steel.
It is designed to provide material demands and flows for the integrated assessment model REMIND, and to provide global context for the scenario analysis in the [TRANSIENCE](https://www.transience.eu/) project.

REMIND-MFA has global coverage. Per default, it runs in 21 world regions. However, due to its flexible design and [madrat](https://github.com/pik-piam/madrat)-based data input, both regional and temporal resolution can be adapted easily.

## Installation

REMIND-MFA dependencies are managed with [pip](https://pypi.org/project/pip/).

To install, clone the repository and run

```
python -m pip install -r pyproject.toml
```

from the repository's main directory.

## Run

To run a model, run

```
python run_remind_mfa.py [path to config]
```

from the main directory, where `[path to config]` is the path to a configuration file, such as `config/steel.yml`.

You can change parameters for the run in these configuration files located in the `config` folder.

Currently, all implemented models require data which is not part of the repository, such that running the models will yield an error.

The data required to run the models is planned to be made accessible in the near future.

## Acknowledgements

The development of REMIND-MFA was conducted within the TRANSIENCE project, grant number 101137606, funded by the European Commission within the Horizon Europe Research and Innovation Programme.
