# REMIND-MFA Blicks

The figures of a REMIND-MFA run are [blicket](https://github.com/tobiasdiez/blicket) Blicks: a
Blick is a named view on a run, a function that turns the run into a long table and how to plot
that table. blicket builds the tables of a run, shows them in a web viewer, compares two builds
Blick by Blick and checks a run against its baseline.

## Inspecting runs

blicket is given one run folder, a series folder of run folders, such as the
`data_out/ci_series/` the `ci` layer writes for all models, or several run folders; the models
must be of one scenario and region mapping.

```console
$ uv run remind-mfa --config default --model steel     # run the steel model and start the Blick viewer afterwards
```

Blicks of a model the run lacks are
skipped, as are those whose data the run lacks (the carbonation module switched off, no
validation data).

If you have older runs, you can inspect them by pointing blicket to the corresponding run folder:

```console
$ uv run blicket data_out/<older run>
```


## Comparing runs

To compare two builds, use `uv run blicket diff <baseline build> <build>`. The comparison is done Blick by Blick, highlighting differences between the two builds. This is useful to see how changes in the models or input data affect the results.
