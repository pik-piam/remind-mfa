"""
Visualization of logistic function parameter effects using Plotly.

Three panels show the effect of varying:
1. Saturation level (L)
2. Growth rate (k)
3. Horizontal offset (x0)
"""

import numpy as np
import plotly.subplots
import plotly.graph_objects as go
import pathlib


def create_logistic_parameter_plot():
    """
    Create a three-panel Plotly figure showing logistic function parameters.

    Returns
    -------
    plotly.graph_objects.Figure
        The figure object
    """
    # Create base x and y arrays (calculated once)
    x_base = np.linspace(-6, 6, 500)
    x_lower = [x_base, 2*x_base, x_base-2]
    x_upper = [x_base, 0.5*x_base, x_base+2]
    L_base = 1.0
    k_base = 1.0
    x0_base = 0.0

    # Calculate base y values
    y_base = L_base / (1.0 + np.exp(-k_base * (x_base - x0_base)))
    y_lower = [0.8 * y_base, y_base, y_base]
    y_upper = [1.2 * y_base, y_base, y_base]

    # Create subplots with 1 row and 3 columns
    fig = plotly.subplots.make_subplots(
        rows=1, cols=3,
        subplot_titles=("Saturation Level", "Growth Rate", "Horizontal Offset"),
        horizontal_spacing=0.02,
    )

    for i in range(3):
        fig.add_trace(
            go.Scatter(
                x=x_base,
                y=y_base,
                mode="lines",
                line=dict(color="black", width=2, dash="solid"),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=1, col=i+1,
        )
        fig.add_trace(
            go.Scatter(
                x=x_lower[i],
                y=y_lower[i],
                mode="lines",
                line=dict(color="black", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=1, col=i+1,
        )
        fig.add_trace(
            go.Scatter(
                x=x_upper[i],
                y=y_upper[i],
                mode="lines",
                line=dict(color="black", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=1, col=i+1,
        )

    # Update x and y axes for all subplots
    fig.update_xaxes(
        showgrid=False,
        showline=False,
        zeroline=False,
        visible=False,
        range=[-8, 8],
        row=1,
    )
    fig.update_yaxes(
        showgrid=False,
        showline=False,
        zeroline=False,
        visible=False,
        range=[-0.1, 1.3],
        row=1,
    )

    # Update layout
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        width=650,
        height=150,
        margin=dict(l=5, r=5, t=35, b=5),
        hovermode=False,
    )

    return fig


if __name__ == "__main__":
    fig = create_logistic_parameter_plot()
    fig.show()
    path = pathlib.Path(__file__).with_name("logistic_parameter_effects.png")
    fig.write_image(
        path,
        width=fig.layout.width,
        height=fig.layout.height,
        scale=2,
    )
