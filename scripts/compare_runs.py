import pickle
import flodym as fd
import flodym.export as fde
import pathlib
import questionary

DIRECTORY = "data/steel/output/export/pickle"
FLOW_NAME = "forming => ip_market"
IS_STOCK = False
RUNS = ["model_steel_SSP1_h12_2026-03-17--16-24-26", "model_steel_SSP2_h12_2026-03-17--16-25-51"]
# RUNS = None
LABELS = ["SSP1", "SSP2"]

DIRECTORY = pathlib.Path(DIRECTORY)

if not RUNS:
    # Interactively choose files from all model_*.pickle files in the directory
    available_files = sorted(DIRECTORY.glob("model_*.pickle"))

    if not available_files:
        raise FileNotFoundError(f"No model_*.pickle files found in: {DIRECTORY}")

    run_file_names = questionary.checkbox(
        "Select run files to compare:",
        choices=[file.name for file in available_files],
        validate=lambda selected: True if selected else "Select at least one file.",
    ).ask()

    if not run_file_names:
        raise ValueError("No files selected. Aborting comparison.")

else:
    run_file_names = [f"{run_name}.pickle" for run_name in RUNS]

run_file_paths = [DIRECTORY / file_name for file_name in run_file_names]
if not LABELS:
    LABELS = [pathlib.Path(f).stem for f in run_file_names]

if RUNS is not None and len(RUNS) != len(run_file_names):
    raise ValueError("run_names must have the same length as selected files")


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

plotter = fde.PlotlyArrayPlotter(
    array=comparison_array,
    title=f"Comparison of {FLOW_NAME} across runs",
    intra_line_dim="t",
    linecolor_dim="X",
    subplot_dim="r",
)
fig = plotter.plot()
fig.show()

plotter = fde.PlotlyArrayPlotter(
    array=comparison_array.sum_over("r",),
    title=f"Comparison of {FLOW_NAME} across runs",
    intra_line_dim="t",
    linecolor_dim="X",
)
fig = plotter.plot()
fig.show()
