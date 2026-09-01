# REMIND-MFA

REMIND-MFA includes top-down prospective material flow analysis (MFA) models for the basic materials cement, plastics, and steel.
It is designed to provide material demands and flows for the integrated assessment model REMIND, and to provide global context for the scenario analysis in the [TRANSIENCE](https://www.transience.eu/) project.

REMIND-MFA has global coverage. Per default, it runs in 21 world regions. However, due to its flexible design and [madrat](https://github.com/pik-piam/madrat)-based data input, both regional and temporal resolution can be adapted easily.

## Installation

REMIND-MFA dependencies are managed with [uv](https://docs.astral.sh/uv/).

To install, clone the repository and run

```
uv sync
```

from the repository's main directory.
This installs the project together with some development dependencies.
For a minimal installation, you can run `uv sync --no-dev` instead.

For development, it may be convenient to check out the `flodym` repository in the same parent directory as `remind-mfa` and uncomment the `tool.uv.sources` section in `pyproject.toml` to point to the local `flodym` repository.
This will install `flodym` in editable mode, allowing you to use and test local changes to `flodym`.

If you prefer `pip`, you can still use it as a fallback:

```
python -m pip install .
```

## Run

To run a model, run

```shell
uv run run_remind_mfa.py --config default --material steel
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

If you have access to the PIK cluster, you can obtain the data as follows:
- Clone the data repository into the same parent directory as `remind-mfa`:
```bash
git clone https://gitlab.pik-potsdam.de/simson_data/remind_mfa_data.git
```
- Set the environment variable `MADRAT_OUTPUTFOLDER` to a folder where the madrat output data should be stored (it can be a relative path), e.g., `export MADRAT_OUTPUTFOLDER=madrat_output`. Alternatively, you can set the environment variable in a `.env` file in the main directory of the repository.
- If you're not running remind-mfa on the cluster, then copy the madrat output data to the local madrat folder by running
```bash
uv run scripts/fetch_from_hpc.py mfa-archive --config default <hpc>
```
where `<hpc>` is the ssh address/alias of the PIK cluster, e.g., `<Your PIK user name>@hpc.pik-potsdam.de`.
Alternatively, you can also use `uv run scripts/fetch_from_hpc.py mrmfa-sources <hpc>` to copy the input data for `mrmfa` from the cluster to your local machine, and then run `mrmfa` locally to generate the madrat output data.


## Questions / Problems

In case of questions / problems please open an issue at [pik-piam/industry_issues](https://github.com/pik-piam/industry_issues/issues).

## Acknowledgements

We gratefully acknowledge funding from the TRANSIENCE project, grant number 101137606, funded by the European Commission within the Horizon Europe Research and Innovation Programme, from the Kopernikus-Projekt Ariadne through the German Federal Ministry of Education and Research (grant no. 03SFK5A0-2), and from the PRISMA project funded by the European Commission within the Horizon Europe Research and Innovation Programme under grant agreement No. 101081604 (PRISMA).
