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

```shell
python run_remind_mfa.py --config default --material steel
```

from the main directory. Configuration names resolve to TOML files below `config`, so
`default` selects `config/default.toml`. Repeat `--config` to stack configurations in
order, with later files overriding earlier files:

```shell
python run_remind_mfa.py --config default --config local --material all
```
See the
[configuration documentation](docs/config.md) for the file layout and merge rules.

You can also simply run `python run_remind_mfa.py` without arguments, in which case you will be prompted to select a configuration and a material.

Currently, all implemented models require data which is not part of the repository, such that running the models will yield an error.

The data required to run the models is planned to be made accessible in the near future.

## Acknowledgements

We gratefully acknowledge funding from the TRANSIENCE project, grant number 101137606, funded by the European Commission within the Horizon Europe Research and Innovation Programme, from the Kopernikus-Projekt Ariadne through the German Federal Ministry of Education and Research (grant no. 03SFK5A0-2), and from the PRISMA project funded by the European Commission within the Horizon Europe Research and Innovation Programme under grant agreement No. 101081604 (PRISMA).
