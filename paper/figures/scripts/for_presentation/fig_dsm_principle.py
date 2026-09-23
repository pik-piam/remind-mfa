# %%
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pathlib

ONLY_PDF = False

# Setup
start_year = 2000
n_years = 15
categories = [start_year + i for i in range(n_years)]

mean_lifetime = 8.0
std_lifetime = 3.0
ages = np.arange(n_years)

# Discrete normal PDF over 15 years (normalized).
pdf = np.exp(-0.5 * ((ages - mean_lifetime) / std_lifetime) ** 2)
pdf = pdf / pdf.sum()

# Survival function implied by the discrete PDF.
sf = 1.0 - np.concatenate(([0.0], np.cumsum(pdf[:-1])))

# 15-color muted palette with enough local contrast for adjacent years.
colors = [
    "#5E81AC",
    "#6A8FB3",
    "#7A9EBB",
    "#8BA8A3",
    "#789D88",
    "#6D9275",
    "#A3A07C",
    "#B0A07A",
    "#BE9F78",
    "#C79274",
    "#B98080",
    "#AA8AA0",
    "#9A92B8",
    "#8798C1",
    "#6F90B4",
]

# Gaussian inflow over 15 years: roughly 1 -> 2 -> 1.
max_pos = (n_years - 1) / 2
inflow_spread = 2.8
inflow = (
    0.2 + (ages / n_years) ** 1.0 + 1.0 * np.exp(-0.5 * ((ages - max_pos) / inflow_spread) ** 2)
)

n_categories = len(categories)
output_dir = pathlib.Path(__file__).with_name("plot_dsm_principle_png")
output_dir.mkdir(exist_ok=True)

marker_line_width = 0.5

if ONLY_PDF:
    i_maxmax = 1
else:
    i_maxmax = n_years
for i_max in range(1, i_maxmax + 1):

    # Create subplot layout (3 rows, shared x)
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
    )

    # --- Top panel ---
    # Each bar has height 1 and unique color (no stacking)
    # Add traces in reverse chronological order so legend is explicitly inverted.
    for i in range(n_years - 1, -1, -1):
        cat = categories[i]
        fig.add_trace(
            go.Bar(
                x=[cat],
                y=[inflow[i]] if i < i_max else [0],
                name=cat,
                marker_color=colors[i],
                marker_line_color="white",
                marker_line_width=marker_line_width,
                showlegend=True,
            ),
            row=1,
            col=1,
        )

    # --- Middle panel (stacked random data) ---
    # Let's say 3 stacked components
    for j in range(i_max):
        y = np.zeros(n_categories)
        for age, p in enumerate(pdf):
            if j + age < n_categories:
                y[j + age] = p * inflow[j]
        fig.add_trace(
            go.Bar(
                x=categories,
                y=y,
                marker_color=colors[j],
                marker_line_color="white",
                marker_line_width=marker_line_width,
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    # --- Bottom panel (stacked random data) ---
    for j in range(i_max):
        y = np.zeros(n_categories)
        for age, s in enumerate(sf):
            if j + age < n_categories:
                y[j + age] = s * inflow[j]
        fig.add_trace(
            go.Bar(
                x=categories,
                y=y,
                marker_color=colors[j],
                marker_line_color="white",
                marker_line_width=marker_line_width,
                showlegend=False,
            ),
            row=3,
            col=1,
        )

    if ONLY_PDF:
        ymax = [0.28, 0.28, 0.28]
    else:
        ymax = [1.8, 1.35, 12.3]
    # Make all bar plots stacked
    fig.update_layout(
        barmode="stack",
        height=500,
        width=400,
        margin=dict(l=55, r=8, t=8, b=22),
        # fixed x-axis range
        xaxis=dict(range=[start_year - 0.5, start_year + n_years - 0.5]),
        # give three subplots y axis titles
        yaxis1_title="Inflow (Mt)",
        yaxis2_title="Outflow (Mt)",
        yaxis3_title="Stock (Mt)",
        # set yaxis3 range to [0, 2]
        yaxis1=dict(range=[0, ymax[0]]),
        yaxis2=dict(range=[0, ymax[1]]),
        yaxis3=dict(range=[0, ymax[2]]),
        # legend title
        legend_title="Production Year",
        # hide legend
        showlegend=not ONLY_PDF,
    )
    fig.update_xaxes(showticklabels=True, row=1, col=1)
    fig.update_xaxes(showticklabels=True, row=2, col=1)
    fig.update_xaxes(showticklabels=True, row=3, col=1)

    if not ONLY_PDF:
        png_path = output_dir / f"plot_dsm_principle_{i_max:02d}.png"
    else:
        png_path = output_dir / f"plot_dsm_principle_pdf.png"
    fig.write_image(png_path, width=400, height=500, scale=2)

    fig.show()
# %%
