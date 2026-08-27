# REMIND-MFA Apptainer container

Self-contained image for REMIND-MFA that contains the necessary R and Python environments to run both `mrmfa` and `remind-mfa`.

Moreover, the image bakes in the following data during build time:
- The code of `mrmfa` (the `apptainer/mrmfa` submodule) and `remind-mfa`.
- The `rev*_mfa.tgz` archives from the madrat repository, which contain the input data for `remind-mfa`, already extracted into `remind_mfa_data/input_data`.

Different versions of these can also be mounted via `bind` during runtime.

This enables two workflows:
- For releases (or snapshots for papers), the container contains the exact code used for the analysis, so that it can be reproduced later.
- For development, local checkouts of `mrmfa` and `remind-mfa` can be mounted into the container, allowing for iterative testing.


## Build

The container is built via meson:

```shell
cd apptainer
meson setup build
meson compile -C build  # produces: build/remind-mfa-<version>.sif
meson test -C build --verbose
```

By default,`mrmfa` comes from the `apptainer/mrmfa` submodule (`git submodule update --init apptainer/mrmfa`). To build a different version instead, e.g. to test local changes:

```shell
meson configure build -Dmrmfa_path=/path/to/mrmfa
```

Note: The build context (the `remind-mfa` working tree, the `mrmfa` sources and the `rev*_mfa.tgz` archives) is staged into the meson build directory with `rsync`, and the `%files` section of `remind-mfa.def` copies it from there. Staging and image build only run when their outputs are missing, so after changing the sources force a rebuild with `meson compile -C build --clean`.

## Running `remind-mfa`

To run `remind-mfa` in the container, using the built-in input data and writing results to a local folder:
```shell
mkdir -p results
apptainer run --bind ./results:/output build/remind-mfa-<version>.sif run --model steel
```

Results appear in `results/<model>/export`. Extra arguments are passed to
`remind_mfa.py` with the `default` and `mrindustry` config layers always
applied first. See `apptainer run <sif> help` for a list of available commands and options.


## Data pipeline

The `retrieve` command generates the madrat data with `mrmfa`. It is the container equivalent of
[preprocessing-mfa](https://github.com/pik-piam/preprocessing-mfa)'s `start.R`.

```shell
mkdir -p results/madrat_out
# On HPC:
apptainer run \
    --bind /p/projects/rd3mod/inputdata:/madrat:ro \
    --bind ./results/madrat_out:/madrat_out --env MADRAT_OUTPUTFOLDER=/madrat_out \
    build/remind-mfa-<version>.sif retrieve --rev 2.1.0
# On local machine:
apptainer run \
    --bind /path/to/madrat/inputdata:/madrat:ro \
    --bind ./results/madrat_out:/madrat_out --env MADRAT_OUTPUTFOLDER=/madrat_out \
    build/remind-mfa-<version>.sif retrieve --rev 2.1.0
```

The `pipeline` command does the same and then runs `remind-mfa` on the result.
Since the new input data has to be extracted into the image, it needs
`--writable-tmpfs`:

```shell
apptainer run --writable-tmpfs \
    --bind ./results:/output \
    --bind /p/projects/rd3mod/inputdata:/madrat:ro \
    --bind ./results/madrat_out:/madrat_out --env MADRAT_OUTPUTFOLDER=/madrat_out \
    build/remind-mfa-<version>.sif pipeline --rev 2.1.0
```
