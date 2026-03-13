import pickle
import flodym as fd
import flodym.export as fde
import pathlib
import questionary
import os

DIRECTORY = None
FLOW_NAME = None
IS_STOCK = False
RUN_NAMES = None

# Interactively choose files from all model_*.pickle files in the directory
available_files = sorted(DIRECTORY.glob("model_*.pickle"))

if not available_files:
    raise FileNotFoundError(f"No model_*.pickle files found in: {DIRECTORY}")

selected_file_names = questionary.checkbox(
    "Select run files to compare:",
    choices=[file.name for file in available_files],
    validate=lambda selected: True if selected else "Select at least one file.",
).ask()

if not selected_file_names:
    raise ValueError("No files selected. Aborting comparison.")

items = RUN_NAMES if RUN_NAMES is not None else [pathlib.Path(f).stem for f in selected_file_names]

pickle_files = [os.path.join(DIRECTORY, file_name) for file_name in selected_file_names]

if RUN_NAMES is not None and len(RUN_NAMES) != len(selected_file_names):
    raise ValueError("run_names must have the same length as selected files")


new_dim = fd.Dimension(letter="X", name="Run", items=items)

mfas = [pickle.load(open(pickle_file, "rb")).future_mfa for pickle_file in pickle_files]
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