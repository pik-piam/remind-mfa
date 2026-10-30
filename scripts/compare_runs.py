import pickle
import flodym as fd
import flodym.export as fde
import pathlib
import questionary

# export.path of the runs; each run has its own folder holding a model.pickle
DIRECTORY = "data_out/transience"
FLOW_NAME = "manufactured_products_market => use"
IS_STOCK = False
# run folder names, relative to DIRECTORY
# RUNS = [
#     "2026-10-06--10-03-42_steel_SSP1_h12_Baseline_Steel_01_06_2026_default",
#     "2026-10-06--10-05-17_steel_SSP2_h12_Baseline_Steel_01_06_2026_default",
# ]
# LABELS = ["SSP1", "SSP2"]
RUNS = None
LABELS = None  # defaults to the run folder names
SUBPLOT_DIM_LETTER = "r"  # e.g. "r" for region, or None for no subplots

DIRECTORY = pathlib.Path(DIRECTORY)
PICKLE_NAME = "model.pickle"

if not RUNS:
    # Interactively choose from all run folders in the directory, including those bundled in a
    # <prefix>_series folder (export.bundle_export = true)
    available_files = sorted(
        {*DIRECTORY.glob(f"*/{PICKLE_NAME}"), *DIRECTORY.glob(f"*/*/{PICKLE_NAME}")}
    )

    if not available_files:
        raise FileNotFoundError(f"No run folders containing {PICKLE_NAME} found in: {DIRECTORY}")

    run_names = questionary.checkbox(
        "Select runs to compare:",
        choices=[str(file.parent.relative_to(DIRECTORY)) for file in available_files],
        validate=lambda selected: True if selected else "Select at least one run.",
    ).ask()

    if not run_names:
        raise ValueError("No runs selected. Aborting comparison.")

else:
    run_names = RUNS

run_file_paths = [DIRECTORY / run_name / PICKLE_NAME for run_name in run_names]
if not LABELS:
    LABELS = [pathlib.Path(run_name).name for run_name in run_names]

if len(LABELS) != len(run_names):
    raise ValueError("LABELS must have the same length as the selected runs")


new_dim = fd.Dimension(letter="X", name="Run", items=LABELS)

mfas = []
for pickle_path in run_file_paths:
    with pickle_path.open("rb") as file_handle:
        mfas.append(pickle.load(file_handle).future_mfa)

if IS_STOCK:
    arrays = [mfa.stocks[FLOW_NAME].stock for mfa in mfas]
else:
    arrays = [mfa.flows[FLOW_NAME] for mfa in mfas]
comparison_array = fd.flodym_array_stack(arrays, dimension=new_dim)

if SUBPLOT_DIM_LETTER:
    plotter = fde.PlotlyArrayPlotter(
        array=comparison_array.sum_to(("t", "X", SUBPLOT_DIM_LETTER)),
        title=f"Comparison of {FLOW_NAME} across runs",
        intra_line_dim="t",
        linecolor_dim="X",
        subplot_dim=SUBPLOT_DIM_LETTER,
    )
    fig = plotter.plot()
    fig.show()

plotter = fde.PlotlyArrayPlotter(
    array=comparison_array.sum_to(("t", "X")),
    title=f"Comparison of {FLOW_NAME} across runs",
    intra_line_dim="t",
    linecolor_dim="X",
)
fig = plotter.plot()
fig.show()
